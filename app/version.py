"""程序版本: git clone 时由 git 现场计算，源码包读取打包时写入的 .git_archival.txt。

版本号只来自 git tag，发布时打 tag 即可；两者都不可用时显示未知版本。
"""

import subprocess
from pathlib import Path

__all__ = ["version"]

_ROOT = Path(__file__).resolve().parents[1]
_ARCHIVAL = _ROOT / ".git_archival.txt"


def version() -> str:
    """返回 描述名 (提交日期)，如 v0.1.1-5-g639968f (2026-10-25)；调用时才读取，导入时不执行子进程。"""
    return _from_git() or _from_archival() or "未知版本"


def _from_git() -> str | None:
    # 没有 git、不在仓库内或 git 拒绝读取 (如 dubious ownership) 时返回 None
    describe = _git("describe", "--tags", "--always", "--dirty")
    date = _git("log", "-1", "--format=%cs")
    if describe is None or date is None:
        return None
    return f"{describe} ({date})"


def _from_archival() -> str | None:
    """读取 git archive 替换后的字段；clone 下的文件仍是 $Format 占位符，视为不可用"""
    try:
        lines = _ARCHIVAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    fields = dict(line.split(": ", 1) for line in lines if ": " in line)
    node, date, describe = fields.get("node", ""), fields.get("node-date", ""), fields.get("describe-name", "")
    if not node or node.startswith("$Format") or date.startswith("$Format"):
        return None
    # 无 tag 时 describe-name 为空，与 git describe --always 一致退到短 hash
    return f"{describe or node[:7]} ({date})"


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(_ROOT), *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    output = result.stdout.strip()
    return output if result.returncode == 0 and output else None
