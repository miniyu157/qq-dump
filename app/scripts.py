"""cli/ 脚本的调用层: 构造命令行，按需经 sudo 以独立进程执行。

cli/ 的每个脚本对应一个函数，子进程命令行在本模块构造。
as_root 由调用方决定。
"""

import json
import subprocess
import sys
from pathlib import Path

from app.ansi import err
from app.dependencies import SUDO
from app.errors import AppError
from app.utils import danger_log, require_binaries

__all__ = ["decrypt", "get_keys", "set_sudo_notice", "set_verbose"]

# 由入口按 --sudo-notice 设置，_run 提权前据此决定是否输出提示
_sudo_notice = False

# 由入口按 --verbose 设置，_script 据此为每个 cli/ 脚本追加 -v
_verbose = False

_CLI_DIR = Path(__file__).resolve().parents[1] / "cli"


def get_keys(user: str | None, qq: str | None, root_dir: str | None, *, as_root: bool) -> list[dict[str, object]]:
    """每个匹配的账号返回一条记录，含 user、uid、uin、db_dir 与 keys；user、qq、root_dir 为 None 时不作为过滤条件传入。

    keys 按匹配优先级列出各类数据库的文件名模式、密钥与 HMAC 算法，数据库目录中没有对应文件的类别不列出。
    缺少 rand 时仍计算 nt 密钥；有对应文件但无法取得的密钥为 None。
    """
    command = _script("get_keys.py")
    if user is not None:
        command += ["-u", user]
    if qq is not None:
        command += ["-a", qq]
    if root_dir is not None:
        command += ["-r", root_dir]
    return _run_json(command, as_root=as_root)


def decrypt(record: dict[str, object], output_dir: str, name_format: str, files: list[str], *, skip_empty: bool = False, copy_plain: bool, as_root: bool) -> bool:
    """files 为空时处理全部 .db；skip_empty 跳过小于 5120 字节的源文件；copy_plain 把明文库复制到输出目录，否则提示后跳过。

    返回子进程是否以 0 退出；跳过空库与明文库不计失败，不保证每个文件均有输出。
    """
    command = [*_script("decrypt_db.py"), "-d", record["db_dir"]]
    for entry in record["keys"]:
        # 未取得的密钥留空，匹配的文件报告缺少密钥，不再尝试后面的规则
        command += ["-k", f"{entry['pattern']}={entry['key'] or ''}:{entry['hmac_algorithm']}"]
    if skip_empty:
        command.append("--skip-empty")
    if copy_plain:
        command.append("--copy-plain")
    command += ["-o", output_dir, "-f", name_format, *files]
    label = f"正在解密账号 {record['user']}.{record['uin']} 的 {err.HL}{' '.join(files) or '全部数据库文件'}{err.RESET}"
    return _run(command, as_root=as_root, label=label).returncode == 0


def _script(name: str) -> list[str]:
    command = [sys.executable, str(_CLI_DIR / name)]
    return [*command, "-v"] if _verbose else command


def set_sudo_notice(enabled: bool) -> None:
    """设置提权执行前是否输出「使用 sudo 运行」提示"""
    global _sudo_notice
    _sudo_notice = enabled


def set_verbose(enabled: bool) -> None:
    """设置调用 cli/ 脚本时是否传入 -v"""
    global _verbose
    _verbose = enabled


def _run(command: list[str], *, as_root: bool, label: str | None = None, capture_stdout: bool = False) -> subprocess.CompletedProcess[str]:
    """as_root 为真时检查 sudo 依赖并通过 sudo 执行。"""
    if as_root:
        require_binaries("提升权限", [SUDO])
        if _sudo_notice:
            # 只显示脚本名: 完整命令行含 -k 密钥
            danger_log(f"使用 sudo 运行: ({Path(command[1]).name})")
    if label is not None:
        print(label, file=sys.stderr)
    stdout = subprocess.PIPE if capture_stdout else None
    argv = ["sudo", *command] if as_root else command
    return subprocess.run(argv, stdout=stdout, text=True, check=False)


def _run_json(command: list[str], *, as_root: bool) -> list[dict[str, object]]:
    """解析 stdout 的 JSON 数组；command 为 [解释器, 脚本, ...]。"""
    result = _run(command, as_root=as_root, capture_stdout=True)
    if result.returncode != 0:
        raise AppError(f"{Path(command[1]).name} 失败 ({result.returncode})")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AppError(f"{Path(command[1]).name} 输出无效: {exc}") from exc
