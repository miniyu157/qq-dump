#!/usr/bin/env python3
"""在脚本上一级的 test/root/ 下生成一份 Android 布局的 QQ 数据目录，供手动试用 key、db、friends、web 等命令。

数据由 test/support 的构造器生成，与自动化测试使用同一套定义；不需要 sqlcipher。
test/root/ 已存在时拒绝运行，需要重新生成时手动删除。先在同级临时目录内生成，全部成功后再改名，中途失败不留半份数据。

账号场景:
  user 0  10001  只有空的数据库目录
  user 0  10002  库的文件头缺少 QQ_NT DB 标记 (rand 为空)；gpro 文件头无法识别盐值
  user 10 10003  可解密的 profile_info.db (含 35 个额外好友)、nt_msg.db 与 gpro 库；错误密钥、明文、空文件、
                 仅文件头的库，以及不参与匹配的 readme.txt
  user 0  格式无效的账号标记: 缺少 ### 分隔、uin 为空、uid 为空

用法: python test/manual/make_root.py，随后例如 ./qqdump -E -r test/root key
"""

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support import qqnt, roots

__all__ = []

ROOT = Path(__file__).resolve().parents[1] / "root"


def _build(root: Path) -> None:
    roots.android_account(root, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")

    uid = "u_BBBBBBBBBBBBBBBBBBBBBB"
    db_dir = roots.android_account(root, "0", "10002", uid)
    plain = qqnt.plain_database(lambda conn: conn.execute("CREATE TABLE t (x)"))
    (db_dir / "nt_msg.db").write_bytes(qqnt.encrypt_database(plain, roots.android_nt_key(uid, "").encode(), header=roots.nt_header(None)))
    (db_dir / f"gpro_v1-6_{uid}.db").write_bytes(roots.gpro_header(None))

    db_dir = roots.android_sample_account(root, "10", "10003", "u_CCCCCCCCCCCCCCCCCCCCCC", extra_friends=35)
    wrong = hashlib.md5(b"wrong").hexdigest().encode()
    (db_dir / "wrong_key.db").write_bytes(qqnt.encrypt_database(plain, wrong, header=roots.nt_header(roots.RAND)))
    (db_dir / "empty.db").touch()
    (db_dir / "header_only.db").write_bytes(roots.nt_header(roots.RAND))
    (db_dir / "readme.txt").write_text("不是数据库，get_keys.py 与 decrypt_db.py 只匹配 *.db\n", encoding="utf-8")

    marks = root / "data" / "user" / "0" / "com.tencent.mobileqq" / "files" / "uid"
    for name in ("10004", "###u_EEEEEEEEEEEEEEEEEEEEEE", "10006###"):
        (marks / name).touch()


def main() -> None:
    if ROOT.exists():
        sys.exit(f"错误: 文件夹已存在 {ROOT}")
    staging = Path(tempfile.mkdtemp(prefix=".root-", dir=ROOT.parent))
    try:
        _build(staging)
        staging.rename(ROOT)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(ROOT)


if __name__ == "__main__":
    main()
