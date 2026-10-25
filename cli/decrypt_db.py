#!/usr/bin/env python3
"""解密 QQ NT 数据库文件。"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def db_cipher(filename: str, key: str | None, gpro_key: str | None) -> tuple[str, str] | None:
    if filename.startswith("gpro_v1-6_"):
        return (gpro_key, "HMAC_SHA512") if gpro_key else None
    return (key, "HMAC_SHA1") if key else None


def safe_output_path(output: str | Path, out_name: str) -> str:
    base = Path(output).resolve()
    target = (base / out_name).resolve()
    if target == base:
        raise ValueError(f"输出路径不能是输出目录本身: {target}")
    if base not in target.parents:
        raise ValueError(f"输出路径越出输出目录: {target}")
    return str(target)


def db_decrypt(db_path: Path, out_path: str, key: str, hmac_algorithm: str) -> None:
    if Path(out_path).resolve() == db_path.resolve():
        raise ValueError(f"输出路径不能与源数据库相同: {out_path}")
    if Path(out_path).is_dir():
        raise ValueError(f"输出路径是目录，拒绝覆盖: {out_path}")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        fd, tmp_path = tempfile.mkstemp(dir="/tmp")
    except OSError:
        fd, tmp_path = tempfile.mkstemp()
    os.close(fd)
    try:
        with db_path.open("rb") as src, open(tmp_path, "wb") as dst:
            src.seek(1024)
            shutil.copyfileobj(src, dst)

        Path(out_path).unlink(missing_ok=True)

        key_sql = key.replace("'", "''")
        out_sql = out_path.replace("'", "''")
        sql = "\n".join([
            f"PRAGMA key = '{key_sql}';",
            "PRAGMA kdf_iter = 4000;",
            f"PRAGMA cipher_hmac_algorithm = {hmac_algorithm};",
            "PRAGMA cipher_page_size = 4096;",
            f"ATTACH DATABASE '{out_sql}' AS plaintext KEY '';",
            "SELECT sqlcipher_export('plaintext');",
            "DETACH DATABASE plaintext;",
        ]) + "\n"
        result = subprocess.run(["sqlcipher", tmp_path], input=sql.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"sqlcipher 失败 ({result.returncode}): {detail}")
    finally:
        Path(tmp_path).unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="解密 QQ NT 数据库文件")
    parser.add_argument("-d", "--db-dir", required=True, help="数据库目录")
    parser.add_argument("-k", "--key", help="数据库密钥")
    parser.add_argument("-g", "--gpro-key", help="gpro 数据库密钥")
    parser.add_argument("files", nargs="*", metavar="file", help="要解密的文件名；省略时解密全部 .db")
    parser.add_argument("-o", "--output-dir", default=".", help="输出目录，默认为 .")
    parser.add_argument("-f", "--name-format", default="{filename}", help="输出文件名模版，斜杠表示目录层，默认为 '{filename}'")
    args = parser.parse_args()

    db_dir = Path(args.db_dir).expanduser().resolve()
    files = args.files or sorted(db.name for db in db_dir.glob("*.db"))

    failed = False
    for name in files:
        db_path = db_dir / name
        if not db_path.is_file():
            print(f"警告: 文件不存在，跳过: {db_path}", file=sys.stderr)
            failed = True
            continue
        cipher = db_cipher(name, args.key, args.gpro_key)
        if cipher is None:
            print(f"警告: 缺少可用密钥，跳过: {name}", file=sys.stderr)
            failed = True
            continue
        key, hmac_algorithm = cipher
        try:
            out_path = safe_output_path(args.output_dir, args.name_format.format(filename=name))
            db_decrypt(db_path, out_path, key, hmac_algorithm)
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"警告: {name}: {exc}", file=sys.stderr)
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
