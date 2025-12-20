import mods.utils as utils

META = {"key": "1", "title": "聊天记录导出工具", "order": 1}


def run(args):
    utils.start_new_py(
        args.base_dir / "QQRootFastDecrypt/old.py", ["--input", args.input, "--output", args.output]
    )
