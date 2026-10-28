"""账号与密钥的前置校验: key、db 与数据库补全共用同一套检查顺序与提示。"""

import sys

from app.scripts import qq_data_accessible, require_qq_data
from app.utils import prefer_binaries, require_binaries, warn_log

__all__ = ["prepare_access", "valid_keys"]


def prepare_access(root_dir: str | None, user: str | None, *, decrypting: bool) -> bool:
    """依次检查 QQ 数据目录与解密依赖，返回是否需要经 sudo 执行；必需依赖不满足时退出，缺少 openssl 时只提示。"""
    require_qq_data(root_dir, user)
    if decrypting:
        require_binaries("数据库解密", ["sqlcipher"])
        prefer_binaries("TIP: 解密超过 1 GiB 的数据库时", ["openssl"])
    return not qq_data_accessible(root_dir, user)


def valid_keys(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """仅检查账号记录非空，不验证密钥能否解密数据库。"""
    if not records:
        warn_log("未找到可用的账号")
        sys.exit(1)
    return records
