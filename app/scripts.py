"""cli/ 脚本的调用层: 构造命令行，按需经 sudo 以独立进程执行。

cli/ 的每个脚本对应一个函数，命令行参数只在本模块出现。
as_root 由调用方根据 qq_data_accessible 决定。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from app.ansi import err
from app.errors import AppError
from app.utils import info_log, require_binaries, warn_log

__all__ = ["decrypt", "get_keys", "print_keys", "qq_data_accessible", "require_qq_data", "scan_accounts"]

_CLI_DIR = Path(__file__).resolve().parents[1] / "cli"


def require_qq_data(root_dir: str | None, user: str | None) -> None:
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
        _qq_data_error(target)


def qq_data_accessible(root_dir: str | None, user: str | None) -> bool:
    """当前身份能否直接读取 QQ 数据目录。"""
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

    return bool(qq_dirs) and all(_can_read(path) for path in qq_dirs)


def scan_accounts(root_dir: str | None, *, as_root: bool) -> list[dict[str, object]]:
    """调用 scan_accounts.py，返回全部账号记录。"""
    command = _script("scan_accounts.py")
    if root_dir is not None:
        command += ["-r", root_dir]
    return _run_json(command, "正在扫描账号...", as_root=as_root)


def get_keys(user: str | None, qq: str | None, root_dir: str | None, *, as_root: bool) -> list[dict[str, object]]:
    """调用 get_keys.py，返回匹配账号的密钥记录。"""
    return _run_json(_get_keys_argv(user, qq, root_dir), "正在获取密钥...", as_root=as_root)


def print_keys(user: str | None, qq: str | None, root_dir: str | None, *, as_root: bool) -> int:
    """调用 get_keys.py，输出直接写到 stdout，返回其退出码。"""
    return _run(_get_keys_argv(user, qq, root_dir), as_root=as_root).returncode


def decrypt(record: dict[str, object], output_dir: str, name_format: str, files: list[str], *, as_root: bool) -> bool:
    """调用 decrypt_db.py 解密 record 账号的 files，files 为空时解密全部；返回是否成功。"""
    command = [*_script("decrypt_db.py"), "-d", record["db_dir"], "-k", record["key"]]
    if record["gpro_key"]:
        command += ["-g", record["gpro_key"]]
    command += ["-o", output_dir, "-f", name_format, *files]
    label = f"正在解密账号 {record['user']} - {record['uin']} 的 {err.HL}{' '.join(files) or '全部数据库文件'}{err.RESET}"
    return _run(command, as_root=as_root, label=label).returncode == 0


def _qq_data_error(target: Path) -> NoReturn:
    """输出 QQ 数据目录缺失的错误与根目录提示，并退出。"""
    print(file=sys.stderr)
    warn_log(f"QQ 数据目录不存在: {target}")
    info_log(f"或许可以使用 {err.HL}--root-dir{err.RESET} 手动设置根目录")
    sys.exit(1)


def _can_read(qq_dir: Path) -> bool:
    """判断 QQ 目录下的账号目录是否可读。"""
    try:
        with os.scandir(qq_dir / "files" / "uid"):
            return True
    except FileNotFoundError:
        return os.access(qq_dir, os.R_OK | os.X_OK)
    except OSError:
        return False


def _script(name: str) -> list[str]:
    return [sys.executable, str(_CLI_DIR / name)]


def _get_keys_argv(user: str | None, qq: str | None, root_dir: str | None) -> list[str]:
    """只追加已指定的过滤条件。"""
    command = _script("get_keys.py")
    if user is not None:
        command += ["-u", user]
    if qq is not None:
        command += ["-a", qq]
    if root_dir is not None:
        command += ["-r", root_dir]
    return command


def _run(command: list[str], *, as_root: bool, label: str | None = None, capture_stdout: bool = False) -> subprocess.CompletedProcess[str]:
    """as_root 为真时检查 sudo 依赖并通过 sudo 执行。"""
    if as_root:
        require_binaries("提升权限", ["sudo"])
    if label is not None:
        print(label, file=sys.stderr)
    stdout = subprocess.PIPE if capture_stdout else None
    argv = ["sudo", *command] if as_root else command
    return subprocess.run(argv, stdout=stdout, text=True, check=False)


def _run_json(command: list[str], label: str, *, as_root: bool) -> list[dict[str, object]]:
    """解析 stdout 的 JSON 数组；command 为 [解释器, 脚本, ...]。"""
    result = _run(command, as_root=as_root, label=label, capture_stdout=True)
    if result.returncode != 0:
        raise AppError(f"{Path(command[1]).name} 失败 ({result.returncode})")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AppError(f"{Path(command[1]).name} 输出无效: {exc}") from exc
