"""从进程内存字节中收集 NTQQ raw_key 候选，纯数据函数，不读进程也不验证密钥。

QQ 把 SQLCipher 的 HMAC 算法标记 `\\x09HMAC_SHA1` 留在密钥旁边，以此为锚点定位
raw_key。Native 构建 (Windows/macOS) 把密钥放在编解码结构里紧挨标记，锚点邻近搜索
即可命中; Electron 构建 (Linux QQ) 把密钥作为 V8 字符串放在 JS 堆上，常离任一锚点
很远，但编解码上下文会聚成密集簇，密钥在簇中心附近，故再从最密簇中心向外收集。

候选的验证 (verify.detect_algo) 与排序后逐个尝试由调用方完成; 本模块只负责产出候选与排序。
collect_region 处理单个区域字节，调用方按区域循环并合并计数; strong_region 是 --strong
模式下对单区域的全窗口遍历。
"""

__all__ = ["character_class_count", "collect_region", "key_ok", "rank", "strong_region"]

_ANCHOR = b"\x09HMAC_SHA1"
_ALIGN = 16
_RADIUS = 0x200
_KEY_LEN = 16
_CLUSTER_GAP = 0x4000
_MIN_CLUSTER_ANCHORS = 4
_CLUSTER_MAX_OUT = 0x20000
_CLUSTER_KEYS_PER = 256


def key_ok(window: bytes) -> bool:
    """16 字节窗口是否像密钥: 全为可打印非空格字符, 且不全为字母数字 (纯文本排除)。"""
    if len(window) != _KEY_LEN:
        return False
    if not all(0x21 <= byte < 0x7F for byte in window):
        return False
    return not all(0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A for byte in window)


def character_class_count(key: bytes) -> int:
    """key 覆盖的字符类别数: 数字、大写、小写、符号各计一, 用于候选排序。"""
    digit = any(0x30 <= byte <= 0x39 for byte in key)
    upper = any(0x41 <= byte <= 0x5A for byte in key)
    lower = any(0x61 <= byte <= 0x7A for byte in key)
    symbol = any(not (0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A) for byte in key)
    return digit + upper + lower + symbol


def rank(counts: dict[bytes, int]) -> list[bytes]:
    """按字符类别数降序、出现次数降序、字节序升序排列候选; counts 为候选到出现次数的映射。"""
    return sorted(counts, key=lambda key: (-character_class_count(key), -counts[key], key))


def _find_anchors(data: bytes) -> list[int]:
    """返回每个锚点对齐槽位: 命中位置 p 处 `\\x09` 为长度前缀, 槽位 p-1 须 16 字节对齐。"""
    anchors = []
    pos = data.find(_ANCHOR)
    while pos >= 0:
        slot = pos - 1
        if slot >= 0 and slot % _ALIGN == 0:
            anchors.append(slot)
        pos = data.find(_ANCHOR, pos + 1)
    return anchors


def _nearest_key(data: bytes, anchor: int) -> bytes | None:
    """从 anchor 对齐处向两侧以 _ALIGN 步长搜到 _RADIUS, 返回最近的合格密钥窗口。"""
    n = len(data)
    base = (anchor // _ALIGN) * _ALIGN
    step = 0
    while step <= _RADIUS:
        for cand in (base - step, base + step if step else -1):
            if 0 <= cand and cand + _KEY_LEN <= n and key_ok(data[cand:cand + _KEY_LEN]):
                return bytes(data[cand:cand + _KEY_LEN])
        step += _ALIGN
    return None


def _cluster_keys(data: bytes, anchors: list[int]) -> list[bytes]:
    """从锚点最密的簇中心向外收集至多 _CLUSTER_KEYS_PER 个候选, 恢复 Electron 布局的密钥。

    锚点按间隔超过 _CLUSTER_GAP 切分成簇, 少于 _MIN_CLUSTER_ANCHORS 的簇视为噪声丢弃。
    """
    if not anchors:
        return []
    clusters = []
    start = 0
    for i in range(1, len(anchors)):
        if anchors[i] - anchors[i - 1] > _CLUSTER_GAP:
            clusters.append(anchors[start:i])
            start = i
    clusters.append(anchors[start:])

    valid = [cluster for cluster in clusters if len(cluster) >= _MIN_CLUSTER_ANCHORS]
    if not valid:
        return []
    best = max(valid, key=len)
    center = ((best[0] + best[-1]) // 2 // _ALIGN) * _ALIGN

    n = len(data)
    found: list[bytes] = []
    seen: set[bytes] = set()
    step = 0
    while step <= _CLUSTER_MAX_OUT and len(found) < _CLUSTER_KEYS_PER:
        for cand in (center - step, center + step if step else -1):
            if cand < 0 or cand + _KEY_LEN > n:
                continue
            if key_ok(data[cand:cand + _KEY_LEN]):
                key = bytes(data[cand:cand + _KEY_LEN])
                if key not in seen:
                    seen.add(key)
                    found.append(key)
        step += _ALIGN
    return found


def collect_region(data: bytes) -> list[bytes]:
    """普通模式: 收集单个区域内锚点邻近与最密簇中心的候选密钥, 无锚点时返回空列表。"""
    anchors = _find_anchors(data)
    if not anchors:
        return []
    found = []
    for anchor in anchors:
        key = _nearest_key(data, anchor)
        if key is not None:
            found.append(key)
    found.extend(_cluster_keys(data, anchors))
    return found


def strong_region(data: bytes, seen: set[bytes], verify):
    """--strong 模式: 遍历单区域每个对齐窗口, 未见过的候选即刻用 verify 验证, 命中即返回。

    从首个锚点处起扫并回绕, 使邻近窗口优先验证, 同时覆盖整个区域。verify(key) 返回真
    即视为命中。seen 跨区域去重, 由调用方以普通模式候选预置; 本函数会把测过的键加入 seen。
    """
    n = len(data)
    if n < _KEY_LEN:
        return None
    anchors = _find_anchors(data)
    start = (anchors[0] // _ALIGN) * _ALIGN if anchors else 0
    offsets = list(range(start, n - _KEY_LEN + 1, _ALIGN)) + list(range(0, start, _ALIGN))
    for off in offsets:
        window = data[off:off + _KEY_LEN]
        if not key_ok(window):
            continue
        key = bytes(window)
        if key in seen:
            continue
        seen.add(key)
        if verify(key):
            return key
    return None
