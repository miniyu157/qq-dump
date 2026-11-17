"""补全 CLI 参数缺省值，按需读取环境配置。"""

import argparse

from app.env import flag_setting, path_setting

__all__ = ["resolve_options"]

_DEFAULTS = {
    "user": None,
    "qq": None,
    "output_dir": ".",
    "db_dir": None,
}

_PATH_ENV = {
    "root_dir": "QQDUMP_ROOT_DIR",
    "key_cache": "QQDUMP_KEY_CACHE",
    "profile_db": "QQDUMP_PROFILE_DB",
    "nt_msg_db": "QQDUMP_NT_MSG_DB",
    "group_info_db": "QQDUMP_GROUP_INFO_DB",
}

_FLAG_ENV = {
    "sudo_notice": "QQDUMP_SUDO_NOTICE",
    "verbose": "QQDUMP_VERBOSE",
}


def resolve_options(args: argparse.Namespace) -> None:
    """原地补全参数；CLI 优先，未指定 -E 时读取进程环境变量与仓库 .env。

    平台不由参数指定，由 accounts.locate_data_root 按数据根目录的结构识别；root_dir 缺省时的取值也由它确定。
    """
    ignore_env = getattr(args, "ignore_env", False)

    for attr, default in _DEFAULTS.items():
        if not hasattr(args, attr):
            setattr(args, attr, default)

    for attr, name in _PATH_ENV.items():
        value = getattr(args, attr, None)
        if not value and not ignore_env:
            value = path_setting(name)
        setattr(args, attr, value or None)

    for attr, name in _FLAG_ENV.items():
        value = getattr(args, attr, None)
        if value is None:
            value = False if ignore_env else flag_setting(name)
        setattr(args, attr, value)
