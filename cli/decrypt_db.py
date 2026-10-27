#!/usr/bin/env python3
"""解密 QQ NT 数据库文件。"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# stderr 消息的来源前缀
PROG = Path(__file__).name

# 明文文件头长度与 cipher_page_size
HEADER_SIZE = 1024
PAGE_SIZE = 4096


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
    # 不足一个密文页时 sqlcipher 不报错，会导出一个空库；照常导出，只提示结果为空
    if db_path.stat().st_size < HEADER_SIZE + PAGE_SIZE:
        print(f"[{PROG}] 警告: {db_path.name}: 文件过小，导出结果为空库", file=sys.stderr)
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
            raise RuntimeError(sqlcipher_reason(result.returncode, result.stderr.decode(errors="replace")))
    finally:
        Path(tmp_path).unlink()


def sqlcipher_reason(code: int, stderr: str) -> str:
    """把 sqlcipher 的多行 stderr 归纳为一行原因；未识别时取末行"""
    # 密钥错误与非加密库都在第 1 页 HMAC 校验处失败，sqlcipher 无法区分两者
    if "hmac check failed" in stderr:
        return "密钥不匹配或文件不是加密库"
    lines = [line for line in stderr.splitlines() if line.strip()]
    return f"sqlcipher 失败 ({code}): {lines[-1].strip() if lines else '无输出'}"


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

    failed = 0
    for name in files:
        db_path = db_dir / name
        if not db_path.is_file():
            print(f"[{PROG}] 警告: 跳过 {name}: 文件不存在", file=sys.stderr)
            failed += 1
            continue
        cipher = db_cipher(name, args.key, args.gpro_key)
        if cipher is None:
            print(f"[{PROG}] 警告: 跳过 {name}: 缺少可用密钥", file=sys.stderr)
            failed += 1
            continue
        key, hmac_algorithm = cipher
        try:
            out_path = safe_output_path(args.output_dir, args.name_format.format(filename=name))
            db_decrypt(db_path, out_path, key, hmac_algorithm)
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"[{PROG}] 警告: {name}: {exc}", file=sys.stderr)
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
