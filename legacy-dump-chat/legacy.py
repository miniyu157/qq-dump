import subprocess
import sys
from pathlib import Path


def run(args):
    script = Path(__file__).resolve().parent / "QQRootFastDecrypt" / "old.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--profile-db",
            args.profile_info_db,
            "--nt-msg-db",
            args.nt_msg_db,
            "--output",
            args.output,
        ]
    )
