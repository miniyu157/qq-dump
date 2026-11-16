"""账号与密钥的前置步骤，并封装取密钥时的密钥缓存与提权流程。

调用顺序: locate_data_root 确定数据根目录与其平台；prepare_access 做前置校验并给出 as_root；
read_keys 在其上调用 get_keys，把密钥缓存交给它验证采用，扫描 QQ 进程内存因权限失败时交互提权重跑，
新取得的密钥记入密钥缓存。
key、db 与数据库补全共用这一顺序，任一步不通过时退出进程。
"""

import os
import sys
from pathlib import Path

from app.ansi import err
from app.dependencies import OPENSSL, SQLCIPHER
from app.errors import AppError, ScriptFailed
from app.key_cache import DEFAULT_KEY_CACHE, remember_keys
from app.scripts import get_keys, locate_data
from app.utils import cancel_log, info_log, prefer_binaries, require_binaries, warn_log
from lib.tui.choose import ChoiceCancelled, choose

__all__ = ["locate_data_root", "prepare_access", "read_keys", "valid_keys"]

_ADJUST_HINT = f"可以用 {err.HL}--root-dir{err.RESET}、环境变量或 .env 中的 {err.HL}QQDUMP_ROOT_DIR{err.RESET} 指定数据根目录"
_CHANGE_HINT = f"可以用 {err.HL}--root-dir{err.RESET} 或 {err.HL}QQDUMP_ROOT_DIR{err.RESET} 改用其他数据根目录；QQDUMP_ROOT_DIR 来自 .env 时可以用 {err.HL}-E{err.RESET} 忽略"
_CHOOSE_HINT = f"可以用 {err.HL}--root-dir{err.RESET} 或 {err.HL}QQDUMP_ROOT_DIR{err.RESET} 直接指定其中之一"


def locate_data_root(root_dir: str | None) -> tuple[str, str]:
    """确定数据根目录与其平台，返回 (platform, root_dir)，供 prepare_access 与 read_keys 使用。

    root_dir 为 None 时取本机全部默认位置上有数据的目录，有多个时显示选择菜单。
    没有候选、候选的结构识别不出、取消选择或输入无效时退出进程。会读取 stdin，向 stderr 输出提示。
    """
    try:
        locations = locate_data(root_dir)
    except AppError as exc:
        if not isinstance(exc, ScriptFailed):
            warn_log(str(exc))
        info_log(_CHANGE_HINT)
        sys.exit(1)
    if not locations:
        warn_log("没有找到 QQ 数据根目录")
        info_log(_ADJUST_HINT)
        sys.exit(1)
    if len(locations) == 1:
        return locations[0]

    title = f"{err.BOLD}{err.INFO}找到多个 QQ 数据根目录，请选择:{err.RESET}"
    labels = [f"{location.platform}  {location.root}" for location in locations]
    try:
        choice = choose(labels, title=title)
    except ChoiceCancelled:
        cancel_log("未选择数据根目录")
        info_log(_CHOOSE_HINT)
        sys.exit(1)
    except EOFError:
        warn_log("stdin 没有输入，无法选择数据根目录")
        info_log(_CHOOSE_HINT)
        sys.exit(1)
    except ValueError as exc:
        warn_log(str(exc))
        sys.exit(1)
    return locations[choice]


def prepare_access(root_dir: str, user: str | None, *, platform: str, decrypting: bool) -> bool:
    """检查解密依赖并返回取密钥是否需要经 sudo；必需依赖不满足时退出，缺少 openssl 时只提示。

    platform 与 root_dir 须先由 locate_data_root 确定。
    platform 为 android 时另检查数据根目录下的 QQ 私有目录，确不存在时退出，不可读时返回 True 表示需提权；
    为 windows 或 linux 时不检查数据目录 (不可访问时由 get_keys.py 直接报错)，恒返回 False，内存扫描失败后
    再由 read_keys 交互提权。
    """
    android = platform == "android"
    if android:
        _require_qq_data(root_dir, user)
    if decrypting:
        require_binaries("数据库解密", [SQLCIPHER])
        prefer_binaries("TIP: 解密超过 1 GiB 的数据库时", [OPENSSL])
    return not _qq_data_accessible(root_dir, user) if android else False


def read_keys(user: str | None, qq: str | None, root_dir: str, *, platform: str, key_cache: str | None, as_root: bool) -> list[dict[str, object]]:
    """取密钥记录，参数含义同 get_keys；须先以同一 platform 与 root_dir 经 prepare_access 得到 as_root 再调用。

    key_cache 为密钥缓存文件路径，None 时用默认位置 (仓库下 .cache/keys.json)。windows 与 linux 平台先采用
    缓存中通过验证的密钥，其余账号扫描 QQ 进程内存，新取得的密钥记入缓存并提示；写缓存失败只警告。
    android 平台的密钥由数据算出，不读写缓存。
    Linux 下若因无权读取 QQ 进程内存而未取得密钥，交互询问后以 sudo 重跑 get_keys；
    非交互终端或用户拒绝时返回原结果 (含 null 密钥)。会读取 stdin，向 stderr 输出提示，会写密钥缓存文件。
    """
    # android 的密钥每次由数据库文件头算出，缓存对它没有用处
    if platform == "android":
        return get_keys(user, qq, root_dir, key_cache=None, as_root=as_root)

    cache = Path(key_cache).expanduser() if key_cache is not None else DEFAULT_KEY_CACHE
    records = _scan_keys(user, qq, root_dir, platform=platform, key_cache=str(cache) if cache.is_file() else None, as_root=as_root)
    _remember(cache, records)
    return records


def _scan_keys(user: str | None, qq: str | None, root_dir: str, *, platform: str, key_cache: str | None, as_root: bool) -> list[dict[str, object]]:
    """调用 get_keys；Linux 下因无权读取 QQ 进程内存而未取得密钥时，询问并得到同意后以 sudo 重跑。"""
    records = get_keys(user, qq, root_dir, key_cache=key_cache, as_root=as_root)
    if as_root or sys.platform == "win32" or not _scan_permission_denied(records):
        return records
    if not _confirm_sudo_rescan():
        return records
    return get_keys(user, qq, root_dir, key_cache=key_cache, as_root=True)


def _remember(cache: Path, records: list[dict[str, object]]) -> None:
    """把新取得的密钥记入缓存并提示；写入失败只警告，本次取得的密钥照常使用。"""
    try:
        added = remember_keys(cache, records)
    except OSError as exc:
        warn_log(f"密钥缓存写入失败: {exc}")
        return
    if added:
        accounts = "、".join(f"{record['user']}.{record['uin']}" for record in added)
        info_log(f"账号 {accounts} 的密钥已存入密钥缓存: {err.HL}{cache}{err.RESET}")


def _scan_permission_denied(records: list[dict[str, object]]) -> bool:
    """records 中是否有账号因无权读取进程内存而未取得密钥 (仅 windows 与 linux 平台会产生此原因)。"""
    return any(
        key.get("key") is None and key.get("key_note", {}).get("reason") == "permission denied"
        for record in records
        for key in record["keys"]
    )


def _confirm_sudo_rescan() -> bool:
    """交互询问是否以 sudo 重跑 get_keys；非交互终端直接返回 False。会读取 stdin。"""
    warn_log("扫描 QQ 进程内存需要 root 权限，当前无权读取")
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        info_log(f"请以 root 身份重试，例如在命令前加 {err.HL}sudo{err.RESET}")
        return False
    try:
        return choose(["使用 sudo 重试", "跳过"], title=f"{err.BOLD}{err.INFO}是否提权重试?{err.RESET}") == 0
    except (ChoiceCancelled, EOFError):
        return False


def valid_keys(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """仅检查密钥记录非空，不验证密钥能否解密数据库。"""
    if not records:
        warn_log("未找到可用的密钥记录")
        sys.exit(1)
    return records


def _require_qq_data(root_dir: str, user: str | None) -> None:
    """QQ 应用数据目录确定不存在时中止；无法读取时不拦截。"""
    users = Path(root_dir).expanduser() / "data" / "user"

    if user is not None:
        candidates = [users / user / "com.tencent.mobileqq"]
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
    if unknown:
        return

    if user is None:
        warn_log(f"{users} 下没有任何用户的 QQ 私有目录 (<用户>/com.tencent.mobileqq)")
        info_log(_CHANGE_HINT)
        sys.exit(1)
    warn_log(f"用户 {user} 下没有 QQ 私有目录: {candidates[0]}")
    holders = _qq_users(users)
    if holders:
        info_log(f"有 QQ 私有目录的用户: {'、'.join(holders)}，可以用 {err.HL}-u{err.RESET} 改选")
    elif holders == []:
        info_log(_CHANGE_HINT)
    sys.exit(1)


def _qq_users(users: Path) -> list[str] | None:
    """data/user 下有 QQ 私有目录的用户；有目录无法读取、结果不确定时返回 None。"""
    names = []
    try:
        for path in users.iterdir():
            try:
                (path / "com.tencent.mobileqq").stat()
            except (FileNotFoundError, NotADirectoryError):
                continue
            names.append(path.name)
    except OSError:
        return None
    return sorted(names)


def _qq_data_accessible(root_dir: str, user: str | None) -> bool:
    """当前身份能否直接读取 QQ 数据目录；忽略确定不存在的目录。"""
    # Windows 没有 os.geteuid，也没有可免检查的 root 身份
    if sys.platform != "win32" and os.geteuid() == 0:
        return True

    users = Path(root_dir).expanduser() / "data" / "user"
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
