"""定位 PC 版 QQ NT 的数据根目录与各账号的数据库目录。

覆盖 Windows 与 Linux, 两者布局不同:
  Windows 数据根目录  读 UserDataInfo.ini 的 UserDataSavePath, 其下为 "Tencent Files"
  Windows 账号库      <root>/<uin>/nt_qq/nt_db, 目录名即 uin, 无需 login.db 即可枚举
  Linux 数据根目录    ~/.config/QQ, flatpak 安装为 ~/.var/app/com.qq.QQ/config/QQ, 两者结构相同;
                      sudo 下回退到 $SUDO_USER 或 /home/* 的家目录
  Linux 账号库        <root>/nt_qq_<hash>/nt_db, hash = md5(md5(uid)+"nt_kernel")
                      目录名是哈希, 反推不出 uin/uid, 必须先解密 login.db 列账号

布局只取决于数据来自哪个系统的 QQ, 与运行本程序的系统无关。调用方按数据布局选择: Windows
布局用 windows_accounts 与 windows_login_db; Linux 布局用 linux_login_db_candidates 读账号,
再用 account_db_dir (配合读到的 uid) 定位。detect_layout 按账号目录的形态识别布局;
default_data_roots 列出某种布局在本机默认位置上的数据根目录, 没有或不止一个时由调用方要求
显式指定 -r。
"""

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

__all__ = ["PcAccount", "account_db_dir", "default_data_roots", "detect_layout", "linux_login_db_candidates", "windows_accounts", "windows_login_db"]

_LINUX_ACCOUNT_DIR = re.compile(r"nt_qq_[0-9a-f]{32}")


class PcAccount(NamedTuple):
    """一个 PC 账号的定位结果, 供进程扫描使用。

    uin 为 QQ 号; uid 在 Windows 由目录名枚举时为空串, 解密 login.db 后可补全, Linux 下
    必填 (账号目录名是 uid 派生的哈希); qq_path 为账号 nt_qq 目录, db_dir 为其 nt_db 目录。
    """

    uin: str
    uid: str
    qq_path: str
    db_dir: str


def detect_layout(root: Path) -> str | None:
    """按 root 下账号目录的形态识别布局: 有 <uin>/nt_qq/nt_db 为 windows, 有 nt_qq_<哈希>/nt_db 为 linux。

    两种都没有或 root 不可读时返回 None。
    """
    try:
        names = [entry.name for entry in root.iterdir()]
    except OSError:
        return None
    if any(name.isdigit() and (root / name / "nt_qq" / "nt_db").is_dir() for name in names):
        return "windows"
    if any(_LINUX_ACCOUNT_DIR.fullmatch(name) and (root / name / "nt_db").is_dir() for name in names):
        return "linux"
    return None


def default_data_roots(layout: str, *, verbose: bool = False) -> list[Path]:
    """返回 layout 布局 (windows / linux) 在本机默认位置上的 QQ 数据根目录。

    本机不是对应的系统, 或默认位置上没有数据时返回空列表。Windows 至多一个; Linux 的原生安装与
    flatpak 安装都有数据时返回两个。
    Linux 下 sudo 运行须回退到其他家目录时, 仅 verbose 为真才向 stderr 提示已跨入该目录。
    """
    if layout == "windows":
        root = _windows_data_root() if sys.platform == "win32" else None
        return [root] if root is not None else []
    return _linux_data_roots(verbose=verbose) if sys.platform != "win32" else []


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


# 家目录下的数据根目录: 原生安装与 flatpak 安装
_LINUX_ROOTS = (".config/QQ", ".var/app/com.qq.QQ/config/QQ")


def _linux_data_roots(*, verbose: bool = False) -> list[Path]:
    """返回家目录下含 login.db 的数据根目录, 兼容 sudo 运行。

    sudo 下 HOME 为 /root, 其下通常没有 QQ 数据。故不信任裸目录, 要求它确实存有 login.db;
    当前 HOME 下没有时, 依次回退到 $SUDO_USER 的家目录与 /home/* 中首个有数据的家目录,
    verbose 下向 stderr 提示已跨入其他账号的目录。
    """
    for home in _candidate_homes():
        roots = [home / relative for relative in _LINUX_ROOTS if _has_login_db(home / relative)]
        if roots:
            if verbose and home != Path.home():
                print(f"get_keys: 当前 HOME 下没有 QQ 数据 (可能是 sudo 运行), 改用 {home}", file=sys.stderr)
            return roots
    return []


def _candidate_homes() -> list[Path]:
    """依次为当前 HOME、$SUDO_USER 的家目录 (未经 sudo 或为 root 时略过) 与 /home 下的各目录。"""
    homes = [Path.home()]
    user = os.environ.get("SUDO_USER")
    if user and user != "root":
        homes.append(Path("/home") / user)
    try:
        homes += sorted(Path("/home").iterdir())
    except OSError:
        pass
    return homes


def _has_login_db(root: Path) -> bool:
    """root 是否为已填充的 QQ 数据根目录, 即任一已知布局下存有 login.db。"""
    return any(path.is_file() for path in linux_login_db_candidates(root))


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
