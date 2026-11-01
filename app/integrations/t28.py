"""Tealina28/QQNT_Export 的本地接入: 改写配置、选择导出选项并启动外部导出器。

外部项目位于仓库根目录的 tmp/QQNT_Export，使用其自带 .venv 运行。
"""

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from app.ansi import err
from app.errors import AppError
from app.utils import cancel_log, good_log, require_binaries, require_modules, warn_log
from lib.tui.choose import ChoiceCancelled, choose, choose_many
from lib.tui.confirm import confirm

__all__ = ["check_environment", "run"]

_EXPORT_RELATIVE = Path("tmp") / "QQNT_Export"
_EXPORT_DIR = Path(__file__).resolve().parents[2] / _EXPORT_RELATIVE

# 已知取值；配置中的未知值仍会出现在菜单里
_FORMATS = ("chatlab_json", "chatlab_jsonl", "html")
_TYPES = ("c2c", "group", "dataline")
_DATALINE_OWNERS = ("pc", "phone", "pad")


def check_environment() -> None:
    """检查 Tealina28/QQNT_Export 的运行前提；须在 run() 与补全数据库前调用。

    缺少入口目录时询问是否从上游克隆；config.toml 缺失时从 example.toml 复制，
    example.toml 也没有时退出；.venv/bin/python 缺失时询问是否创建虚拟环境，
    创建后询问是否安装 requirements.txt。
    入口文件缺失、拒绝克隆或创建、克隆或创建失败，或本解释器缺少 tomlkit 时，
    输出提示并以状态码 1 退出。
    """
    if not _EXPORT_DIR.is_dir():
        _clone_export_project()

    entry_path = _EXPORT_DIR / "main.py"
    if not entry_path.is_file():
        warn_log(f"找不到 Tealina28/QQNT_Export 入口文件: {entry_path}")
        sys.exit(1)

    config_path = _EXPORT_DIR / "config.toml"
    example_path = _EXPORT_DIR / "example.toml"
    if not config_path.is_file():
        if not example_path.is_file():
            warn_log(f"找不到 {config_path.name}，{example_path.name} 也没有: {_EXPORT_DIR}")
            sys.exit(1)
        shutil.copyfile(example_path, config_path)
        good_log(f"已复制 {example_path.name} 到 {config_path.name}: {_EXPORT_DIR}")

    interpreter = _EXPORT_DIR / ".venv" / "bin" / "python"
    if not interpreter.is_file():
        _create_virtualenv()

    require_modules("Tealina28/QQNT_Export 导出", ["tomlkit"])


def _clone_export_project() -> None:
    """询问是否克隆上游项目；拒绝或取消时退出，确认后检查 git 并浅克隆 dev 分支到 _EXPORT_DIR。"""
    try:
        approved = confirm(f"目前没有仓库，是否要克隆到 {err.HL}{_EXPORT_RELATIVE}{err.RESET}？\n仓库 {err.HL}https://github.com/Tealina28/QQNT_Export.git{err.RESET} 的 {err.HL}dev{err.RESET} 分支，浅克隆。")
    except (ChoiceCancelled, EOFError):
        approved = False
    if not approved:
        cancel_log("未克隆 Tealina28/QQNT_Export")
        sys.exit(1)

    require_binaries("克隆 Tealina28/QQNT_Export ", ["git"])
    proc = subprocess.run(["git", "clone", "--depth", "1", "--branch", "dev", "https://github.com/Tealina28/QQNT_Export.git", str(_EXPORT_DIR)], check=False)
    if proc.returncode != 0:
        warn_log(f"克隆失败，退出码 {proc.returncode}")
        sys.exit(1)


def _create_virtualenv() -> None:
    """询问是否创建虚拟环境；拒绝或取消时退出，确认后用当前解释器创建到 _EXPORT_DIR/.venv。

    创建后询问是否安装 requirements.txt，安装失败时退出。
    """
    try:
        approved = confirm(f"目前在 {err.HL}{_EXPORT_RELATIVE}{err.RESET} 内没有 .venv/bin/python，是否创建虚拟环境？")
    except (ChoiceCancelled, EOFError):
        approved = False
    if not approved:
        cancel_log("未创建虚拟环境")
        sys.exit(1)

    venv_dir = _EXPORT_DIR / ".venv"
    proc = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=False)
    if proc.returncode != 0:
        warn_log(f"创建虚拟环境失败，退出码 {proc.returncode}: {venv_dir}")
        sys.exit(1)
    good_log(f"已创建虚拟环境: {venv_dir}")

    try:
        install = confirm(f"是否执行 {err.HL}.venv/bin/pip install -r requirements.txt{err.RESET} 安装依赖？")
    except (ChoiceCancelled, EOFError):
        install = False
    if not install:
        return
    proc = subprocess.run([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "-r", "requirements.txt"], cwd=str(_EXPORT_DIR), check=False)
    if proc.returncode != 0:
        warn_log(f"安装依赖失败，退出码 {proc.returncode}: {venv_dir}")
        sys.exit(1)
    good_log("依赖安装完成")


def run(*, db_dir: str | Path, output_dir: str | Path) -> int:
    """改写配置并启动 Tealina28/QQNT_Export，返回其退出码，输出数据库与导出目录。

    db_dir 内的库文件使用外部导出器规定的名称；私聊选择读取 profile_info.db。
    交互终端中依次询问导出格式、会话类型及过滤/设备；非交互时沿用现有选项。
    调用前须先执行 check_environment()。
    会写入 config.toml 并启动子进程；取消菜单或未选格式/类型时以状态码 1 退出，
    过滤器空选择表示全部。配置无法解析时抛 AppError，数据库读取错误向上传播。
    """
    database_dir = Path(db_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()

    entry_path = _EXPORT_DIR / "main.py"
    config_path = _EXPORT_DIR / "config.toml"
    interpreter = _EXPORT_DIR / ".venv" / "bin" / "python"

    import tomlkit

    try:
        document = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    except tomlkit.exceptions.ParseError as exc:
        raise AppError(f"无法解析配置: {config_path} ({exc})") from exc
    document["db_path"] = str(database_dir)
    document["output_path"] = str(output_dir)

    # 非交互环境沿用现有配置，避免脚本被输入阻塞
    if sys.stdin.isatty() and sys.stderr.isatty():
        _configure(document, config_path, database_dir)
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    proc = subprocess.run([str(interpreter), str(entry_path), str(config_path)], cwd=str(_EXPORT_DIR), check=False)
    return proc.returncode


def _configure(document, config_path: Path, db_dir: Path) -> None:
    """依次询问导出格式、会话类型及对应过滤/设备，并写回文档。

    格式与类型菜单中已有值在前；写回时已知值固定在前，未知值保持配置顺序。
    """
    current_formats = _string_array(document, "output_format", ("chatlab_json",), config_path)
    formats = _select_known(current_formats, _FORMATS, title="请选择导出格式 (output_format, 不勾选则取消):", message="未选择导出格式")
    current_types = _string_array(document, "conversation_types", _TYPES, config_path)
    types = _select_known(current_types, _TYPES, title="请选择会话类型 (conversation_types, 不勾选则取消):", message="未选择会话类型")
    _set_array(document, "output_format", formats)
    _set_array(document, "conversation_types", types)
    if "c2c" in types:
        current_c2c = _int_array(document, "c2c_filters", config_path)
        _set_array(document, "c2c_filters", _select_c2c_filters(current_c2c, str(db_dir / "profile_info.db")))
    if "group" in types:
        current_group = _int_array(document, "group_filters", config_path)
        _set_array(document, "group_filters", _select_group_filters(current_group, (
            "note: 目前未设计此功能可靠来源，请勿勾选；",
            "note: 可以手动在 tmp/QQNT_Export/config.toml 中填充",
            "      group_filters 数组，会加入到此菜单中；",
        ), "group_filters"))
    if "dataline" in types:
        document["dataline_owner"] = _select_owner(_dataline_owner(document, config_path))


def _string_array(document, key: str, default: Sequence[str], config_path: Path) -> list[str]:
    """读取字符串数组字段；缺失时返回默认值，类型不符时中止。"""
    value = document.get(key)
    if value is None:
        return list(default)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AppError(f"配置中的 {key} 必须是字符串数组: {value!r} ({config_path})")
    return list(value)


def _int_array(document, key: str, config_path: Path) -> list[int]:
    """读取整数数组字段；缺失视为空，类型不符时中止。"""
    value = document.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise AppError(f"配置中的 {key} 必须是整数数组: {value!r} ({config_path})")
    return list(value)


def _dataline_owner(document, config_path: Path) -> str:
    """读取 dataline_owner；缺失或为空时使用默认 pc，已知设备去除空白并统一小写。"""
    value = document.get("dataline_owner")
    if value is None or (isinstance(value, str) and not value.strip()):
        return "pc"
    if not isinstance(value, str):
        raise AppError(f"配置中的 dataline_owner 必须是字符串: {value!r} ({config_path})")
    value = value.strip()
    for name in _DATALINE_OWNERS:
        if value.lower() == name:
            return name
    return value


def _menu(options: list[str], *, title: str, selected: list[int], message: str) -> list[int]:
    """调用多选菜单；Esc 或 EOF 时提示并中止整个命令。"""
    try:
        return choose_many(options, title=f"{err.BOLD}{err.INFO}{title}{err.RESET}", selected=selected)
    except (ChoiceCancelled, EOFError):
        cancel_log(message)
        sys.exit(1)


def _select_known(current: list[str], known: Sequence[str], *, title: str, message: str) -> list[str]:
    """菜单展示已有值后接缺失的已知值；返回值按已知值优先排序，未知值保持配置顺序。"""
    current = list(dict.fromkeys(current))
    options = current + [name for name in known if name not in current]
    indices = _menu(options, title=title, selected=list(range(len(current))), message=message)
    if not indices:
        cancel_log(message)
        sys.exit(1)
    chosen = {options[index] for index in indices}
    return [name for name in known if name in chosen] + [name for name in current if name not in known and name in chosen]


def _friend_label(friend) -> str:
    """用户标签: 昵称 (备注: 备注) (QQ: uin)；备注用 faint、QQ 号用 90m、非好友标记用 33m。"""
    parts = [friend.nickname] if friend.nickname else []
    if friend.remark:
        parts.append(f"{err.FAINT}(备注: {friend.remark}){err.RESET}")
    parts.append(("\033[90m" if err.TTY else "") + f"(QQ: {friend.uin}){err.RESET}")
    label = " ".join(parts)
    if friend.is_friend:
        return label
    return label + (" \033[33m" if err.TTY else " ") + f"[非好友]{err.RESET}"


def _select_c2c_filters(current: list[int], profile_db: str) -> list[int]:
    """从 api 读取全部资料条目并多选 QQ 号；不勾选表示全部，无候选时中止。

    菜单不校验 c2c 映射；部分条目可能未被 nt_uid_mapping_table 收录，
    选中后由外部导出器报错。
    """
    from api import load_friends

    current = list(dict.fromkeys(current))
    friends = load_friends(profile_db)
    uins = [friend.uin for friend in friends]
    options = [_friend_label(friend) for friend in friends]
    for value in current:
        if value not in uins:
            options.append(str(value))
            uins.append(value)
    if not options:
        raise AppError("没有可供选择的 c2c 用户")
    indices = _menu(
        options,
        title="请选择 c2c_filters (不勾选表示全部):",
        selected=[index for index, uin in enumerate(uins) if uin in current],
        message="未完成 c2c_filters 选择",
    )
    return [uins[index] for index in indices]


def _select_group_filters(current: list[int], extras: Sequence[str | int], key: str) -> list[int]:
    """多选过滤值；不勾选表示全部，非整数值按类型校验中止。"""
    current = list(dict.fromkeys(current))
    current_labels = {str(value) for value in current}
    options = [str(value) for value in current] + [str(value) for value in extras if str(value) not in current_labels]
    indices = _menu(
        options,
        title=f"请选择 {key} (不勾选表示全部):",
        selected=list(range(len(current))),
        message=f"未完成 {key} 选择",
    )
    try:
        return [int(options[index]) for index in indices]
    except ValueError:
        raise AppError(f"{key} 必须是整数数组") from None


def _select_owner(current: str) -> str:
    """单选数据线设备；已知值顺序固定，光标定位当前值，未知值追加在末尾。"""
    options = list(_DATALINE_OWNERS)
    if current not in options:
        options.append(current)
    try:
        index = choose(options, title=f"{err.BOLD}{err.INFO}请选择 dataline_owner:{err.RESET}", initial=options.index(current))
    except (ChoiceCancelled, EOFError):
        cancel_log("未选择 dataline_owner")
        sys.exit(1)
    return options[index]


def _set_array(document, key: str, values: list) -> None:
    """原地更新数组字段；原数组多行时保持多行，数组内部注释会丢失，空数组写成单行，缺失时新建。"""
    current = document.get(key)
    if isinstance(current, list) and "\n" in current.as_string():
        current.clear()
        current.extend(values)
        current.multiline(True)
    else:
        document[key] = values
