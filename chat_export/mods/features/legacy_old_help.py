import mods.utils as utils

META = {"key": "2", "title": "QQRootFastDecrypt 帮助信息", "order": 2}


def run(args):
    utils.start_new_py(args.base_dir / "old.py", "--help")
