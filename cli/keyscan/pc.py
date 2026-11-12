"""PC (Windows/Linux) 账号取密钥的统一入口, 供 cli/get_keys.py 调用。

密钥有两个来源, 都用账号的 settings.db 验证后才采用: 调用方给出的此前取得的密钥 (密钥缓存) 优先,
其余账号再扫描进程内存。按进程逐个扫描内存, 每扫完一个进程就用各账号的 settings.db 验证它的候选, 命中即为该
账号的 raw_key, 同时确定持有它的进程; 所有待取账号都命中后立即停止, 不再扫剩余进程。
进程后端识别到 wrapper.node 主进程时只交出主进程, 识别不到才交出全部 QQ 进程。多账号
同时登录时各自落在不同进程里, 由验证结果区分, 不需要文件锁反查。

PC 只需一个 raw_key 解该账号的全部 *.db (gpro 独立密钥是 Android 专属), 故每条记录只
产出一条 nt 规则。read_keys_pc 返回的记录字段与 get_keys.py 的 Android 分支一致; platform 与 user
均为数据布局名 (windows / linux), uid_hash/path_hash 不适用, 留空串。未取得密钥的账号仍列出,
key 为 None, key_note.reason 说明原因 (no settings.db / no key / key mismatch / permission denied /
not found)。

账号枚举与密钥验证只读数据目录, 与运行系统无关; 扫描进程内存须在运行该 QQ 的系统上进行,
由调用方决定是否传入进程后端。读进程内存的权限要求因操作系统而异: Windows 同用户下通常
可直接读取, Linux 受 ptrace_scope 限制, 一般须 root。会向 stderr 输出日志。
"""

import sys
from pathlib import Path

from cli.keyscan import scan, verify
from cli.keyscan.verify import Algo

__all__ = ["read_keys_pc"]

# 单个内存区域的读取上限, 防止异常大区域耗尽内存
_MAX_REGION = 512 * 1024 * 1024


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _process_candidates(reader) -> list[bytes] | None:
    """读取单个进程的全部可读区域, 返回按 scan.rank 排序的候选; 一个字节都读不到时返回 None。

    Linux 下同用户进程的 maps 可读、ProcessReader 能打开, 但受 ptrace_scope 限制时
    process_vm_readv 全部失败; 以「全部区域读不到」识别这种权限拒绝, 与打不开同等对待。
    """
    counts: dict[bytes, int] = {}
    read_any = False
    for base, size in reader.regions():
        data = reader.read(base, min(size, _MAX_REGION))
        if not data:
            continue
        read_any = True
        for key in scan.collect_region(data):
            counts[key] = counts.get(key, 0) + 1
    return scan.rank(counts) if read_any else None


class _Pending:
    """一个待取密钥的账号及其验证基准; matched 为命中结果, 命中后不再参与后续进程的验证。"""

    def __init__(self, account, who: str, settings_bytes: bytes, files: list[Path]) -> None:
        self.account = account
        self.who = who
        self.settings_bytes = settings_bytes
        self.files = files
        # 命中的 (密钥, 算法, 进程号); 密钥来自密钥缓存时进程号为 None
        self.matched: tuple[bytes, Algo, int | None] | None = None
        self.mismatched = False

    def try_match(self, pid: int | None, candidates: list[bytes]) -> bool:
        """用本账号 settings.db 逐个验证 candidates, 命中则记录并返回 True。"""
        for key in candidates:
            algo = verify.detect_algo(self.settings_bytes, key)
            if algo is not None:
                self.matched = (key, algo, pid)
                return True
        return False


def _nt_key_entry(raw_key: bytes | None, algo: Algo | None, files: list[Path], note: dict[str, str]) -> dict[str, object]:
    """构造与 Android nt 规则同构的 keys 条目: pattern="*.db", 单一 raw_key 解该账号全部库。"""
    return {
        "name": "nt",
        "pattern": "*.db",
        "key": raw_key.decode("ascii") if raw_key is not None else None,
        "hmac_algorithm": verify.hmac_algorithm(algo) if algo is not None else "HMAC_SHA1",
        "key_note": note,
        "files": [{"name": path.name, "size": path.stat().st_size} for path in files],
    }


def _account_record(account, layout: str, keys: list[dict[str, object]]) -> dict[str, object]:
    """组装与 Android 分支同字段的账号记录; platform 与 user 为数据布局名, uid_hash/path_hash 留空。"""
    return {
        "platform": layout,
        "qq_path": account.qq_path,
        "user": layout,
        "uin": account.uin,
        "uid": account.uid,
        "uid_hash": "",
        "path_hash": "",
        "db_dir": account.db_dir,
        "keys": keys,
    }


def _db_files(db_dir: Path) -> list[Path]:
    """返回 db_dir 下按名排序的全部 *.db 文件; 目录不可读时返回空列表。"""
    try:
        return sorted(path for path in db_dir.glob("*.db") if path.is_file())
    except OSError:
        return []


def _prepare(account, who: str, *, verbose: bool) -> _Pending | dict[str, object]:
    """读账号 settings.db 作为验证基准; 成功返回 _Pending, 缺失时直接返回 no settings.db 条目。"""
    db_dir = Path(account.db_dir)
    files = _db_files(db_dir)
    try:
        settings_bytes = (db_dir / "settings.db").read_bytes()
    except OSError:
        if verbose:
            _log(f"get_keys: 账号 {who} 缺少 settings.db, 无法验证, 未取得密钥")
        return _nt_key_entry(None, None, files, {"reason": "no settings.db"})
    return _Pending(account, who, settings_bytes, files)


def _match_cached(pending: list[_Pending], cached: dict[str, list[bytes]]) -> None:
    """用密钥缓存中的密钥验证各账号, 只试 uin 相同的密钥; 缓存里有却都不匹配时标记 mismatched。"""
    for account in pending:
        candidates = cached.get(account.account.uin, [])
        if not candidates:
            continue
        if account.try_match(None, candidates):
            _, algo, _ = account.matched
            _log(f"get_keys: 账号 {account.who} 采用密钥缓存中的 raw_key (page={algo.page} kdf={algo.kdf})")
        else:
            account.mismatched = True
            _log(f"get_keys: 密钥缓存中账号 {account.who} 的 {len(candidates)} 个密钥均不匹配这份数据; raw_key 随设备而不同, 须在这份数据所在的设备上取得")


def _scan_until_matched(backend, pending: list[_Pending], *, verbose: bool) -> int:
    """逐进程扫描并即时验证待取账号, 全部命中即止; 返回无权读取的进程数。

    打不开或一个字节都读不到的进程 (权限不足) 计入返回的 denied 计数。
    """
    pids = backend.find_qq_pids()
    denied = 0
    remaining = list(pending)
    if verbose and not pids:
        _log("get_keys: 未发现 QQ 进程; 请先登录 QQ")
    for pid, name in pids:
        if not remaining:
            break
        try:
            reader = backend.ProcessReader(pid)
        except OSError:
            denied += 1
            continue
        try:
            candidates = _process_candidates(reader)
        finally:
            reader.close()
        if candidates is None:
            denied += 1
            continue
        if verbose and candidates:
            _log(f"get_keys: pid {pid} [{name}] 收集到 {len(candidates)} 个候选")
        hit = [account for account in remaining if account.try_match(pid, candidates)]
        # 取得密钥是选账号的关键信息, 默认即提示, 避免用户选到无密钥的账号
        for account in hit:
            _, algo, _ = account.matched
            _log(f"get_keys: 账号 {account.who} 在 pid {pid} 取得 raw_key (page={algo.page} kdf={algo.kdf})")
        remaining = [account for account in remaining if account.matched is None]
    return denied


def _pending_entry(pending: _Pending, denied: int, *, scanned: bool, verbose: bool) -> dict[str, object]:
    """把一个 _Pending 的结果转为 keys 条目; 未命中时区分未扫描、权限不足与未找到。"""
    who = pending.who
    if pending.matched is not None:
        raw_key, algo, pid = pending.matched
        source = {"source": "key cache"} if pid is None else {"pid": str(pid)}
        return _nt_key_entry(raw_key, algo, pending.files, {**source, "kdf": algo.kdf})
    # 与未找到一样关系到能否选用该账号, 默认即提示
    if not scanned:
        if pending.mismatched:
            return _nt_key_entry(None, None, pending.files, {"reason": "key mismatch"})
        _log(f"get_keys: 账号 {who} 未取得 raw_key; 本机不是这份数据所属的系统, 无法扫描 QQ 进程内存, 请用 -k 指定在数据所在的设备上取得的密钥缓存")
        return _nt_key_entry(None, None, pending.files, {"reason": "no key"})
    # 只有确有进程拒绝打开时才归因权限; 是否提权不作判定依据 (Windows 非管理员常可直接读取),
    # Linux 读他人进程通常须 root, 打不开的进程会计入 denied, 由此报出权限不足
    if denied:
        if verbose:
            _log(f"get_keys: 账号 {who} 未取得 raw_key; {denied} 个 QQ 进程无权读取, Linux 下请以 root 身份重试")
        return _nt_key_entry(None, None, pending.files, {"reason": "permission denied"})
    # 未找到同样关系到能否选用该账号, 默认即提示
    _log(f"get_keys: 账号 {who} 未在任何 QQ 进程中找到通过验证的 raw_key (可能未登录)")
    return _nt_key_entry(None, None, pending.files, {"reason": "not found"})


def read_keys_pc(qq: str | None, accounts: list, *, layout: str, cached: dict[str, list[bytes]], backend, verbose: bool) -> list[dict[str, object]]:
    """取 accounts 中各账号的 raw_key, 返回与 Android 分支同构的记录列表。

    accounts 每项须有 uin、uid (Windows 布局下可为空串)、qq_path、db_dir 字段 (locate.PcAccount);
    layout 为这些账号的数据布局 (windows / linux), 写入记录的 platform 与 user 字段。
    cached 为密钥缓存中该布局的密钥 (uin -> 密钥列表, 见 key_cache.read_cached_keys), 验证通过的直接采用,
    不再为该账号扫描内存; 没有时传空字典。
    backend 为进程后端模块 (process_windows / process_linux), 须有 find_qq_pids 与 ProcessReader;
    为 None 表示本机不是这份数据所属的系统, 不扫描内存, 仍未取得密钥的账号记为 no key, 缓存中的
    密钥都不匹配时记为 key mismatch。
    qq 非 None 时只保留 uin 或 uid 等于它的账号; 没有匹配账号时不扫描内存。
    缺少 settings.db 的账号无法验证, 直接记为 no settings.db。
    """
    selected = [account for account in accounts if qq is None or qq in (account.uin, account.uid)]
    if not selected:
        return []

    # 按账号准备验证基准; 缺少 settings.db 的直接定稿, 其余先试缓存的密钥, 再扫描
    prepared = [(account, _prepare(account, f"{layout}.{account.uin}", verbose=verbose)) for account in selected]
    pending = [result for _, result in prepared if isinstance(result, _Pending)]

    _match_cached(pending, cached)
    remaining = [account for account in pending if account.matched is None]
    scanned = backend is not None
    denied = _scan_until_matched(backend, remaining, verbose=verbose) if scanned and remaining else 0

    records = []
    for account, result in prepared:
        entry = result if isinstance(result, dict) else _pending_entry(result, denied, scanned=scanned, verbose=verbose)
        records.append(_account_record(account, layout, [entry]))
    return records
