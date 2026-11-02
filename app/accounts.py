"""账号与密钥的前置校验: key、db 与数据库补全共用同一套检查顺序与提示。"""

import os
import sys
from pathlib import Path

from app.ansi import err
from app.utils import info_log, prefer_binaries, require_binaries, warn_log

__all__ = ["prepare_access", "valid_keys"]


def prepare_access(root_dir: str | None, user: str | None, *, decrypting: bool) -> bool:
    """依次检查 QQ 数据目录与解密依赖，返回是否需要经 sudo 执行；必需依赖不满足时退出，缺少 openssl 时只提示。"""
    _require_qq_data(root_dir, user)
    if decrypting:
        require_binaries("数据库解密", ["sqlcipher"])
        prefer_binaries("TIP: 解密超过 1 GiB 的数据库时", ["openssl"])
    return not _qq_data_accessible(root_dir, user)


def valid_keys(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """仅检查密钥记录非空，不验证密钥能否解密数据库。"""
    if not records:
        warn_log("未找到可用的密钥记录")
        sys.exit(1)
    return records


def _require_qq_data(root_dir: str | None, user: str | None) -> None:
    """QQ 应用数据目录确定不存在时中止；无法读取时不拦截。"""
    users = Path(root_dir or "/").expanduser() / "data" / "user"
    target = users / (user or "*") / "com.tencent.mobileqq"

    if user is not None:
        candidates = [target]
    else:
        try:
            candidates = [path / "com.tencent.mobileqq" for path in users.iterdir()]
        except (FileNotFoundError, NotADirectoryError):
            candidates = []
        except OSError:
            return

    unknown = False
    for candidate in candidates:
        try:
            candidate.stat()
            return
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            unknown = True
    if not unknown:
        warn_log(f"尝试访问 QQ 私有目录，但它不存在: {target}")
        info_log(f"或许可以使用 {err.HL}--root-dir{err.RESET}、环境变量或 .env 中的 {err.HL}QQDUMP_ROOT_DIR{err.RESET} 设置根目录")
        sys.exit(1)


def _qq_data_accessible(root_dir: str | None, user: str | None) -> bool:
    """当前身份能否直接读取 QQ 数据目录；忽略确定不存在的目录。"""
    if os.geteuid() == 0:
        return True

    users = Path(root_dir or "/").expanduser() / "data" / "user"
    if user is not None:
        qq_dirs = [users / user / "com.tencent.mobileqq"]
    else:
        try:
            qq_dirs = [path / "com.tencent.mobileqq" for path in users.iterdir()]
        except OSError:
            return False

    found = False
    for qq_dir in qq_dirs:
        try:
            qq_dir.stat()
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return False
        found = True
        if not _can_read(qq_dir):
            return False
    return found


def _can_read(qq_dir: Path) -> bool:
    """判断 QQ 目录下的账号目录是否可读。"""
    try:
        with os.scandir(qq_dir / "files" / "uid"):
            return True
    except FileNotFoundError:
        return os.access(qq_dir, os.R_OK | os.X_OK)
    except OSError:
        return False
