"""密钥缓存: 此前取得的密钥记录, 供取密钥时先行验证采用, 不必每次扫描进程内存。

文件是 get_keys.py 输出的 JSON 记录数组, 可以只含其中的部分字段; 本模块只读取记录的
platform、uin 与各 keys 条目的 key, 其余字段忽略, 因此 get_keys.py 的完整输出也可以直接作为缓存。
raw_key 随设备而不同, 同一平台的同一 uin 可有多条记录, 由调用方逐个验证。
本模块只读文件; 缓存放在哪里、何时写入由调用 get_keys.py 的一方决定。
"""

import json
from pathlib import Path

__all__ = ["read_cached_keys"]


def read_cached_keys(path: Path, *, platform: str) -> dict[str, list[bytes]]:
    """返回缓存中 platform 平台的 uin -> 密钥列表, 后写入的记录在前; key 为 null 的条目跳过。

    文件读不了、不是 JSON 或记录结构不符时抛 OSError。
    """
    # json.loads 按 BOM 识别 UTF-8 与 UTF-16; Windows PowerShell 的重定向会写出带 BOM 的 UTF-16
    try:
        records = json.loads(path.read_bytes())
    except ValueError as exc:
        raise OSError(f"密钥缓存不是 JSON 文本, 应为 get_keys.py 输出的记录数组: {path}") from exc
    if not isinstance(records, list):
        raise OSError(f"密钥缓存的顶层不是数组, 应为 get_keys.py 输出的记录数组: {path}")

    keys: dict[str, list[bytes]] = {}
    for number, record in reversed(list(enumerate(records, 1))):
        if not _record_valid(record):
            raise OSError(f"密钥缓存第 {number} 条记录结构无效, 须有文本 platform、uin 与 keys 数组, 各条目的 key 为文本或 null: {path}")
        if record["platform"] != platform:
            continue
        found = [entry["key"].encode() for entry in record["keys"] if entry["key"] is not None]
        if found:
            keys.setdefault(record["uin"], []).extend(found)
    return keys


def _record_valid(record: object) -> bool:
    """record 是否具备本模块读取的字段: 文本 platform 与 uin, keys 为条目数组且各条目的 key 为文本或 None。"""
    if not isinstance(record, dict):
        return False
    if not isinstance(record.get("platform"), str) or not isinstance(record.get("uin"), str):
        return False
    entries = record.get("keys")
    if not isinstance(entries, list):
        return False
    return all(isinstance(entry, dict) and "key" in entry and isinstance(entry["key"], str | None) for entry in entries)
