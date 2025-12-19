import sqlite3
import os
import atexit
import base64
from datetime import datetime
from pathlib import Path
import subprocess
import json
import sys
import warnings

import mods.schema as dbsma
import mods.msg as msg
import mods.utils as utils
import mods.ui as ui

console = msg.Console()


def cleanup():
    pass


atexit.register(cleanup)





# 递归嵌套 protobuf



# def start_old_script(*args):
#     script = BASE_DIR / "old.py"
#     if len(args) == 1 and isinstance(args[0], (list, tuple)):
#         args = args[0]

#     subprocess.run([sys.executable, script, *args])


def main():
    ui.menu_loop(ARGS)


if __name__ == "__main__":
    ARGS = utils.parseArgs()
    ARGS.base_dir = Path(__file__).resolve().parent
    utils.check_paths(ARGS)

    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        msg.error(f"未捕获的异常: {e}")
        # sys.exit(1)
