"""账号与密钥的前置校验: key、db 与数据库补全共用同一套检查顺序与提示。"""

import sys

from app.scripts import qq_data_accessible, require_qq_data
from app.utils import require_binaries, warn_log

__all__ = ["prepare_access", "valid_keys"]


def prepare_access(root_dir: str | None, user: str | None, *, decrypting: bool) -> bool:
    """依次检查 QQ 数据目录与解密依赖，返回是否需要经 sudo 执行；不满足时退出。"""
    require_qq_data(root_dir, user)
    if decrypting:
        require_binaries("数据库解密", ["sqlcipher"])
    return not qq_data_accessible(root_dir, user)


def valid_keys(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """原样返回 get_keys 的记录；为空时退出。

    get_keys.py 已跳过无法计算密钥的账号并逐条警告，此处无法区分「没有账号」与「全部被跳过」。
    """
    if not records:
        warn_log("未找到可用的账号")
        sys.exit(1)
    return records
