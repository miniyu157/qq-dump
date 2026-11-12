"""运行时依赖表：pip 包名与导入名、二进制名与 Termux 包名，以及用途说明。

只提供数据，不检查也不输出；检查与补全见 app.utils 与 app.installers。
"""

from typing import NamedTuple

__all__ = ["BINARIES", "CHAFA", "GIT", "MODULES", "OPENSSL", "PILLOW", "RICH", "SQLCIPHER", "SUDO", "TOMLKIT", "XDG_OPEN", "Binary", "Module"]


class Module(NamedTuple):
    """Python 依赖：package 为 pip 包名，module 为导入名，termux 为 Termux 的 pkg 包名，没有时为 None。"""

    package: str
    module: str
    purpose: str
    termux: str | None


class Binary(NamedTuple):
    """二进制依赖：name 为 PATH 中的可执行文件名，termux 为提供它的 Termux 包名，没有时为 None。"""

    name: str
    purpose: str
    termux: str | None


PILLOW = Module("pillow", "PIL", "运行 avatar 渲染头像时需要", "python-pillow")
RICH = Module("rich", "rich", "仅 Table2d 研究套件需要", None)
TOMLKIT = Module("tomlkit", "tomlkit", "运行 Tealina28/QQNT_Export 导出时需要", None)

SUDO = Binary("sudo", "QQ 数据不可访问或 Linux 下扫描 QQ 进程内存时需要", "sudo")
SQLCIPHER = Binary("sqlcipher", "解密数据库时需要", "sqlcipher")
# Termux 的 openssl 只含库，命令行工具在子包 openssl-tool
OPENSSL = Binary("openssl", "解密超过 1 GiB 的数据库时需要", "openssl-tool")
CHAFA = Binary("chafa", "运行 avatar --chafa 时需要", "chafa")
GIT = Binary("git", "克隆 Tealina28/QQNT_Export 时需要", "git")
# Termux 的 xdg-utils 位于需要另行启用的 x11-repo，不提供安装
XDG_OPEN = Binary("xdg-open", "WebUI 自动打开页面时需要", None)

# check 命令列出的依赖，按此顺序显示
MODULES = (PILLOW, RICH, TOMLKIT)
BINARIES = (SUDO, SQLCIPHER, OPENSSL, CHAFA)
