import atexit
from pathlib import Path
import sys

import mods.msg as msg
import mods.utils as utils
import mods.ui as ui

console = msg.Console()


def cleanup():
    pass


atexit.register(cleanup)


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
