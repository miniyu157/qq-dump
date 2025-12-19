import mods.utils as utils

META = {"key": "1", "title": "QQRootFastDecrypt", "order": 1}


def run(args):
    utils.start_new_py(
        args.base_dir / "old.py", ["--input", args.input, "--output", args.output]
    )
