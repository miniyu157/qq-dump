"""密钥缓存的位置与写入: 记下取得过的密钥，之后取密钥时交给 get_keys.py 读回验证，不必每次扫描 QQ 进程内存。

缓存文件是 get_keys 返回的记录数组，记入时去掉随运行变化的 files 与 key_note。读取由 cli/get_keys.py 完成，
它只认记录的 platform、uin 与各条目的 key，并用数据库验证后才采用，因此缓存里留有过时或其他设备的密钥也无妨。
缓存只增不删: 同一账号在不同设备上的密钥各占一条，互不覆盖。
"""

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

__all__ = ["DEFAULT_KEY_CACHE", "remember_keys"]

DEFAULT_KEY_CACHE = Path(__file__).resolve().parents[1] / ".cache" / "keys.json"

# 随运行变化的条目字段: 文件列表与取得方式，读回时由 get_keys.py 重新得出
_VOLATILE = ("files", "key_note")


def remember_keys(cache: Path, records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """把 records 中尚未记入的密钥追加到缓存文件 cache，返回新记入的记录；没有新密钥时不写文件。

    records 为 get_keys 返回的记录。未取得密钥的条目不记入，记入的条目去掉 files 与 key_note。
    平台、uin 与各条目的 name、key 都相同的记录视为已记入，不重复追加，已有的记录原样保留。
    按需创建 cache 所在的目录；文件读写失败，或现有内容不是记录数组时抛 OSError。
    """
    stored = _load(cache)
    known = {_identity(record) for record in stored}
    added = []
    for record in records:
        entries = [{name: value for name, value in entry.items() if name not in _VOLATILE} for entry in record["keys"] if entry["key"] is not None]
        candidate = {**record, "keys": entries}
        if not entries or _identity(candidate) in known:
            continue
        known.add(_identity(candidate))
        added.append(candidate)
    if added:
        _store(cache, [*stored, *added])
    return added


def _identity(record: Mapping[str, object]) -> tuple[object, ...]:
    """区分两条记录是否为同一份密钥: 平台、uin 与各条目的 name、key；未取得密钥的条目不计。"""
    keys = tuple((entry.get("name"), entry.get("key")) for entry in record.get("keys", []) if entry.get("key") is not None)
    return record.get("platform"), record.get("uin"), keys


def _load(cache: Path) -> list[dict[str, object]]:
    """读出缓存中的记录；文件不存在时为空列表，内容不是记录数组时抛 OSError。"""
    try:
        data = cache.read_bytes()
    except FileNotFoundError:
        return []
    # json.loads 按 BOM 识别 UTF-8 与 UTF-16，用户以 key 的输出重定向得到的文件也能读
    try:
        records = json.loads(data)
    except ValueError as exc:
        raise OSError(f"密钥缓存不是 JSON 文本: {cache}") from exc
    if not isinstance(records, list) or not all(isinstance(record, dict) and isinstance(record.get("keys", []), list) for record in records):
        raise OSError(f"密钥缓存不是记录数组: {cache}")
    return records


def _store(cache: Path, records: list[dict[str, object]]) -> None:
    """先写同目录的临时文件再替换，中途失败不破坏原有缓存；POSIX 下临时文件只有属主可读写，替换后亦然。"""
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=cache.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            json.dump(records, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp_path, cache)
    finally:
        temp_path.unlink(missing_ok=True)
