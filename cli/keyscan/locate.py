"""定位 PC 版 QQ NT 的数据根目录与各账号的数据库目录。

覆盖 Windows 与 Linux, 两者布局不同:
  Windows 数据根目录  读 UserDataInfo.ini 的 UserDataSavePath, 其下为 "Tencent Files"
  Windows 账号库      <root>/<uin>/nt_qq/nt_db, 目录名即 uin, 无需 login.db 即可枚举
  Linux 数据根目录    ~/.config/QQ; sudo 下回退到 $SUDO_USER 或 /home/* 的 QQ 目录
  Linux 账号库        <root>/nt_qq_<hash>/nt_db, hash = md5(md5(uid)+"nt_kernel")
                      目录名是哈希, 反推不出 uin/uid, 必须先解密 login.db 列账号

调用方按操作系统选择: Windows 用 windows_accounts 与 windows_login_db; Linux 用
linux_login_db_candidates 读账号, 再用 account_db_dir (配合读到的 uid) 定位。detect_data_root
按当前操作系统给出默认的数据根目录, 返回 None 时由调用方要求显式指定 -r。
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import NamedTuple

__all__ = ["PcAccount", "account_db_dir", "detect_data_root", "linux_login_db_candidates", "windows_accounts", "windows_login_db"]


class PcAccount(NamedTuple):
    """一个 PC 账号的定位结果, 供进程扫描使用。

    uin 为 QQ 号; uid 在 Windows 由目录名枚举时为空串, 解密 login.db 后可补全, Linux 下
    必填 (账号目录名是 uid 派生的哈希); qq_path 为账号 nt_qq 目录, db_dir 为其 nt_db 目录。
    """

    uin: str
    uid: str
    qq_path: str
    db_dir: str


def detect_data_root(*, verbose: bool = False) -> Path | None:
    """按当前操作系统返回 QQ 数据根目录的默认猜测; 无法确定时返回 None。

    Linux 下 sudo 运行须回退到其他家目录时, 仅 verbose 为真才向 stderr 提示已跨入该目录。
    """
    if sys.platform == "win32":
        return _windows_data_root()
    return _linux_data_root(verbose=verbose)


def _windows_data_root() -> Path | None:
    """从 UserDataInfo.ini 读 UserDataSavePath, 返回其下的 Tencent Files; 读取失败返回 None。"""
    ini = Path(r"C:\Users\Public\Documents\Tencent\QQ\UserDataInfo.ini")
    try:
        text = ini.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_section = line.lower() == "[userdataset]"
            continue
        if not in_section or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().lower() != "userdatasavepath":
            continue
        value = value.strip()
        if not value:
            continue
        path = Path(value)
        # UserDataSavePath 可能已指向 Tencent Files, 也可能停在上一层
        if path.name.lower() == "tencent files":
            return path
        return path / "Tencent Files"
    return None


def _linux_data_root(*, verbose: bool = False) -> Path | None:
    """返回含 login.db 的 ~/.config/QQ, 兼容 sudo 运行。

    sudo 下 HOME 为 /root, 其 .config/QQ 通常不存在或没有 login.db。故不信任裸目录, 要求它
    确实存有 login.db; 当前 HOME 的不合格时, 依次回退到 $SUDO_USER 的家目录与 /home/* 中首个
    合格的 QQ 目录, verbose 下向 stderr 提示已跨入其他账号的目录。都不合格时返回当前 HOME 的猜测,
    由调用方报告 login.db 缺失。
    """
    direct = Path.home() / ".config" / "QQ"
    if _has_login_db(direct):
        return direct
    fallback = _sudo_user_config_qq() or _scan_home_config_qq()
    if fallback is not None:
        if verbose:
            print(f"get_keys: 当前 HOME 下的 .config/QQ 无 login.db (可能是 sudo 运行), 改用 {fallback}", file=sys.stderr)
        return fallback
    return direct


def _has_login_db(root: Path) -> bool:
    """root 是否为已填充的 QQ 数据根目录, 即任一已知布局下存有 login.db。"""
    return any(path.is_file() for path in linux_login_db_candidates(root))


def _sudo_user_config_qq() -> Path | None:
    """$SUDO_USER 家目录下含 login.db 的 .config/QQ; 未经 sudo 或为 root 时返回 None。"""
    user = os.environ.get("SUDO_USER")
    if not user or user == "root":
        return None
    candidate = Path("/home") / user / ".config" / "QQ"
    return candidate if _has_login_db(candidate) else None


def _scan_home_config_qq() -> Path | None:
    """扫描 /home/*/.config/QQ, 返回首个含 login.db 的目录。"""
    try:
        homes = sorted(Path("/home").iterdir())
    except OSError:
        return None
    for home in homes:
        candidate = home / ".config" / "QQ"
        if _has_login_db(candidate):
            return candidate
    return None


def windows_login_db(root: Path) -> Path:
    """Windows 全局 login.db 路径: <root>/nt_qq/global/nt_db/login.db。"""
    return root / "nt_qq" / "global" / "nt_db" / "login.db"


def linux_login_db_candidates(root: Path) -> list[Path]:
    """Linux 全局 login.db 的候选路径, 优先者在前。

    常见布局为 <root>/global/nt_db/login.db; 部分安装像 Windows 一样嵌在 nt_qq/ 下。两处都返回,
    由调用方逐个读取并合并账号, 冲突时以前者为准。
    """
    return [root / "global" / "nt_db" / "login.db", root / "nt_qq" / "global" / "nt_db" / "login.db"]


def windows_accounts(root: Path) -> list[PcAccount]:
    """枚举 <root>/<uin>/nt_qq/nt_db 存在的账号, 按 uin 排序; 目录名即 uin, 不需要 login.db。

    只接受纯数字的目录名 (uin), 跳过 nt_qq 等非账号目录; root 不可读时返回空列表。
    uid 留空串 (目录枚举无从得知, 解密 login.db 后方可补全)。
    """
    accounts = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        db_dir = entry / "nt_qq" / "nt_db"
        if db_dir.is_dir():
            accounts.append(PcAccount(uin=entry.name, uid="", qq_path=str(entry / "nt_qq"), db_dir=str(db_dir)))
    return accounts


def account_db_dir(root: Path, uid: str) -> Path:
    """Linux 账号 nt_db 目录: <root>/nt_qq_<md5(md5(uid)+"nt_kernel")>/nt_db。"""
    inner = hashlib.md5(uid.encode()).hexdigest()
    outer = hashlib.md5((inner + "nt_kernel").encode()).hexdigest()
    return root / f"nt_qq_{outer}" / "nt_db"
