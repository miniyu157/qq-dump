"""get_keys 记录的替身数据，供调度层的测试代替真实的取密钥结果。

字段与 cli/get_keys.py 的输出一致；contract/test_app_scripts.py 把这里的字段集合与真实输出比对，
两者不一致时那条用例失败，替身不会悄悄偏离真实数据。
"""

__all__ = ["ENTRY_FIELDS", "RECORD_FIELDS", "key_entry", "record"]

RECORD_FIELDS = ("platform", "qq_path", "user", "uin", "uid", "uid_hash", "path_hash", "db_dir", "keys")
ENTRY_FIELDS = ("name", "pattern", "key", "hmac_algorithm", "key_note", "files")


def key_entry(key: str | None, *, reason: str | None = None, name: str = "nt", pattern: str = "*.db", hmac_algorithm: str = "HMAC_SHA1", files: tuple[tuple[str, int], ...] = ()) -> dict[str, object]:
    """keys 中的一项；key 为 None 表示未取得密钥，reason 写入 key_note 说明原因。"""
    note = {"reason": reason} if reason is not None else {}
    return {"name": name, "pattern": pattern, "key": key, "hmac_algorithm": hmac_algorithm, "key_note": note, "files": [{"name": file, "size": size} for file, size in files]}


def record(platform: str, uin: str, *entries: dict[str, object], user: str | None = None, uid: str = "", db_dir: str = "/data/nt_db") -> dict[str, object]:
    """一条账号记录；user 缺省为平台名 (windows 与 linux 的记录如此)，android 须给出用户 ID。"""
    return {"platform": platform, "qq_path": "/data", "user": user or platform, "uin": uin, "uid": uid, "uid_hash": "", "path_hash": "", "db_dir": db_dir, "keys": list(entries)}
