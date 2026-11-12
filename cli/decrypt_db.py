#!/usr/bin/env python3
"""解密 QQ NT 数据库文件。"""

import argparse
import hashlib
import hmac
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from fnmatch import fnmatchcase
from pathlib import Path


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def progress(msg: str) -> None:
    """终端中原地刷新当前行；非终端时逐行输出，避免日志文件中堆成一行"""
    if sys.stderr.isatty():
        print(f"\r\x1b[2K{msg}", end="", file=sys.stderr, flush=True)
    else:
        log(msg)


def end_progress(reported: bool) -> None:
    """为原地刷新的进度行补上换行，后续日志另起一行"""
    if reported and sys.stderr.isatty():
        print(file=sys.stderr)


# 明文文件头长度与 cipher_page_size
HEADER_SIZE = 1024
PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16

# 未加密 SQLite 库的文件头 magic，用于识别并非加密库的文件
SQLITE_HEADER = b"SQLite format 3\0"

# SQLite 把文件偏移 2^30 所在的整页留给文件锁。QQ 的文件带 1024 字节明文头，留空的是第 262144 页；
# 剥头后 SQLite 改认 262145 为锁页，而这一页存着真实数据，读到即报 database disk image is malformed。
LOCK_PAGE = 0x40000000 // PAGE_SIZE + 1

# HMAC 算法 -> (页尾保留字节, 摘要名, 摘要长度)；保留字节为 IV 加摘要向 16 字节对齐
PAGE_CIPHER = {"HMAC_SHA1": (48, "sha1", 20), "HMAC_SHA512": (80, "sha512", 64)}

KDF_ITER = 4000
HMAC_KDF_ITER = 2

# 复制与导出超过 PROGRESS_DELAY 秒后开始输出进度，此后每隔 PROGRESS_INTERVAL 秒刷新一次
PROGRESS_DELAY = 3
PROGRESS_INTERVAL = 1
COPY_CHUNK = 16 * 1024 * 1024
MIB = 1024 * 1024

# quick_check 对锁页的报告: 带 Tree 前缀时父指针位于某个 cell 或页头的右子指针，Freelist 前缀表示锁页在空闲列表，无前缀表示锁页是根页
LOCK_REF = f"2nd reference to page {LOCK_PAGE}"
LOCK_REF_RE = re.compile(rf"page (\d+) (?:cell (\d+)|(right child)): {LOCK_REF}$")


def key_rule(text: str) -> tuple[str, str, str]:
    """解析 -k 的 [模式=]密钥[:算法]，返回 (模式, 密钥, 算法)

    PC 的 raw_key 可含 = 与 :，因此模式取首个 = 之前的部分，算法只在末段以 :HMAC_ 开头时切出；
    含 = 的密钥须写明模式 (如 *=)，否则 = 之前的部分会被当作模式。
    """
    pattern, sep, rest = text.partition("=")
    if not sep:
        pattern, rest = "", text
    key, colon, hmac_algorithm = rest.rpartition(":")
    if not colon or not hmac_algorithm.startswith("HMAC_"):
        key, hmac_algorithm = rest, "HMAC_SHA1"
    if hmac_algorithm not in PAGE_CIPHER:
        raise argparse.ArgumentTypeError(f"不支持的 HMAC 算法: {hmac_algorithm}")
    return pattern or "*", key, hmac_algorithm


def db_cipher(filename: str, rules: list[tuple[str, str, str]]) -> tuple[str, str] | None:
    """按顺序取首条文件名模式匹配的规则，返回其密钥与 HMAC 算法；无匹配或该规则的密钥为空时返回 None"""
    for pattern, key, hmac_algorithm in rules:
        if fnmatchcase(Path(filename).name, pattern):
            return (key, hmac_algorithm) if key else None
    return None


def plain_header_size(db_path: Path) -> int | None:
    """明文库返回 SQLite 文件头之前的字节数，即 0 或 QQ 文件头的长度；不是明文库时返回 None"""
    with db_path.open("rb") as src:
        header = src.read(HEADER_SIZE + len(SQLITE_HEADER))
    if header.startswith(SQLITE_HEADER):
        return 0
    if header[HEADER_SIZE:].startswith(SQLITE_HEADER):
        return HEADER_SIZE
    return None


def safe_output_path(output: str | Path, out_name: str) -> str:
    base = Path(output).resolve()
    target = (base / out_name).resolve()
    if target == base:
        raise ValueError("输出路径不能是输出目录本身")
    if base not in target.parents:
        raise ValueError("输出路径越出输出目录")
    return str(target)


def sqlcipher_script(key: str, hmac_algorithm: str, statements: list[str]) -> bytes:
    key_sql = key.replace("'", "''")
    return ("\n".join([
        f"PRAGMA key = '{key_sql}';",
        f"PRAGMA kdf_iter = {KDF_ITER};",
        f"PRAGMA cipher_hmac_algorithm = {hmac_algorithm};",
        f"PRAGMA cipher_page_size = {PAGE_SIZE};",
        *statements,
    ]) + "\n").encode()


def run_sqlcipher(db_path: str, key: str, hmac_algorithm: str, statements: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["sqlcipher", db_path], input=sqlcipher_script(key, hmac_algorithm, statements), capture_output=True, check=False)


def resolve_hmac_algorithm(tmp_path: str, key: str, hmac_algorithm: str, *, verbose: bool = False) -> str:
    fallback = "HMAC_SHA512" if hmac_algorithm == "HMAC_SHA1" else "HMAC_SHA1"
    for algorithm in (hmac_algorithm, fallback):
        if verbose and algorithm != hmac_algorithm:
            log(f"{hmac_algorithm} 解密校验失败，正在尝试 {algorithm} ...")
        checked = run_sqlcipher(tmp_path, key, algorithm, ["SELECT count(*) FROM sqlite_master;"])
        if checked.returncode == 0:
            return algorithm
        stderr = checked.stderr.decode(errors="replace")
        if "hmac check failed" not in stderr:
            break
    raise RuntimeError(sqlcipher_reason(checked.returncode, stderr))


def copy_body(db_path: Path, tmp_path: str, header_size: int = HEADER_SIZE) -> None:
    """复制剥除文件头后的内容；进度按已复制字节计算，总量确定"""
    total = db_path.stat().st_size - header_size
    copied = 0
    next_report = time.monotonic() + PROGRESS_DELAY
    reported = False
    try:
        with db_path.open("rb") as src, open(tmp_path, "wb") as dst:
            src.seek(header_size)
            while chunk := src.read(COPY_CHUNK):
                dst.write(chunk)
                copied += len(chunk)
                if time.monotonic() >= next_report:
                    progress(f"已复制 {copied / MIB:.0f} / {total / MIB:.0f} MiB ({copied / total:.0%})")
                    reported = True
                    next_report += PROGRESS_INTERVAL
    finally:
        end_progress(reported)


def export_plaintext(tmp_path: str, out_path: str, key: str, hmac_algorithm: str, src_size: int) -> None:
    """导出明文库；sqlcipher_export 不报告进度，以输出文件大小近似，最终大小无法预知，故不计百分比"""
    out_sql = out_path.replace("'", "''")
    script = sqlcipher_script(key, hmac_algorithm, [
        f"ATTACH DATABASE '{out_sql}' AS plaintext KEY '';",
        "SELECT sqlcipher_export('plaintext');",
        "DETACH DATABASE plaintext;",
    ])
    reported = False
    try:
        with subprocess.Popen(["sqlcipher", tmp_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            pending = script
            timeout = PROGRESS_DELAY
            while True:
                try:
                    _, stderr = proc.communicate(pending, timeout=timeout)
                    break
                except subprocess.TimeoutExpired:
                    # 输入只能在首次调用时传入，超时后重试须传 None，未发送的部分由 Popen 继续写入
                    pending = None
                    timeout = PROGRESS_INTERVAL
                    # ATTACH 不会立即创建输出文件，首次写入前按 0 计
                    written = os.path.getsize(out_path) if os.path.exists(out_path) else 0
                    progress(f"已写入 {written / MIB:.0f} MiB / 源库 {src_size / MIB:.0f} MiB")
                    reported = True
    finally:
        end_progress(reported)
    if proc.returncode != 0:
        raise RuntimeError(sqlcipher_reason(proc.returncode, stderr.decode(errors="replace")))


def derive_keys(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    """主密钥取自口令与 salt，HMAC 密钥由主密钥与按 SQLCipher 默认掩码 0x3A 异或后的 salt 派生"""
    key = hashlib.pbkdf2_hmac("sha512", passphrase.encode(), salt, KDF_ITER, 32)
    hmac_salt = bytes(byte ^ 0x3A for byte in salt)
    return key, hashlib.pbkdf2_hmac("sha512", key, hmac_salt, HMAC_KDF_ITER, 32)


def page_mac(raw: bytes, pgno: int, hmac_key: bytes, hmac_algorithm: str) -> bytes:
    """页尾摘要覆盖密文、IV 与页号，因此迁页必须重算"""
    reserve, digest, mac_size = PAGE_CIPHER[hmac_algorithm]
    start = SALT_SIZE if pgno == 1 else 0
    return hmac.new(hmac_key, raw[start : PAGE_SIZE - reserve + IV_SIZE] + pgno.to_bytes(4, "little"), digest).digest()[:mac_size]


def aes_cbc(flag: str, key: bytes, iv: bytes, data: bytes) -> bytes:
    argv = ["openssl", "enc", flag, "-aes-256-cbc", "-nopad", "-K", key.hex(), "-iv", iv.hex()]
    result = subprocess.run(argv, input=data, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"openssl 失败 ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def read_page(handle, pgno: int) -> bytes:
    handle.seek((pgno - 1) * PAGE_SIZE)
    return handle.read(PAGE_SIZE)


def write_page(handle, pgno: int, raw: bytes) -> None:
    handle.seek((pgno - 1) * PAGE_SIZE)
    handle.write(raw)


def relocate_lock_page(tmp_path: str, key: str, hmac_algorithm: str, *, verbose: bool = False) -> None:
    """把锁页上的数据迁到 QQ 留空的前一页，并改写指向它的父指针；锁页是根页或位于溢出链时放弃导出"""
    # quick_check 无需自行遍历 b-tree 即可报出父指针位置，代价是多扫一遍全库。
    # 它退出时关闭最后一个连接，SQLite 随之把副本的 WAL 合并回主文件，之后直接改页才不会被 WAL 中的同号页覆盖
    if verbose:
        log("正在检查锁页引用 ...")
    checked = run_sqlcipher(tmp_path, key, hmac_algorithm, ["PRAGMA quick_check;"])
    refs = [line for line in checked.stdout.decode(errors="replace").splitlines() if line.endswith(LOCK_REF)]
    if not refs:
        if verbose:
            log("未发现锁页引用，跳过迁移")
        return
    if len(refs) > 1:
        raise RuntimeError(f"锁页 {LOCK_PAGE} 被多处引用，放弃导出")
    if refs[0].startswith("Freelist: "):
        if verbose:
            log("锁页位于空闲列表，导出不会读取，跳过迁移")
        return
    found = LOCK_REF_RE.search(refs[0])
    if found is None:
        raise RuntimeError(f"锁页 {LOCK_PAGE} 是表或索引的根页，暂不支持迁移，放弃导出")
    parent = int(found.group(1))
    cell = None if found.group(3) else int(found.group(2))

    reserve, _, mac_size = PAGE_CIPHER[hmac_algorithm]
    body = PAGE_SIZE - reserve
    mac_at = body + IV_SIZE
    with open(tmp_path, "r+b") as handle:
        handle.seek(0)
        aes_key, hmac_key = derive_keys(key, handle.read(SALT_SIZE))

        if read_page(handle, LOCK_PAGE - 1) != bytes(PAGE_SIZE):
            raise RuntimeError(f"页 {LOCK_PAGE - 1} 并非空页，放弃导出")

        if verbose:
            log(f"正在将锁页 {LOCK_PAGE} 迁移至页 {LOCK_PAGE - 1}，并更新父页 {parent} 的引用 ...")
        # 密文与 IV 原样复制，AES-CBC 只依赖页内的 IV，页号仅进入摘要
        moved = read_page(handle, LOCK_PAGE)
        write_page(handle, LOCK_PAGE - 1, moved[:mac_at] + page_mac(moved, LOCK_PAGE - 1, hmac_key, hmac_algorithm) + moved[mac_at + mac_size :])

        raw = read_page(handle, parent)
        # 第 1 页的前 16 字节存放 salt，不参与加密；b-tree 页头位于 100 字节的数据库文件头之后
        start, hdr = (SALT_SIZE, 100) if parent == 1 else (0, 0)
        iv = raw[body:mac_at]
        plain = bytes(start) + aes_cbc("-d", aes_key, iv, raw[start:body])
        offset = hdr + 8 if cell is None else struct.unpack_from(">H", plain, hdr + 12 + 2 * cell)[0]
        # cell 前缀的报告也可能来自该 cell 的溢出链，此时父页是叶子页，或该位置不是子页指针
        if plain[hdr] not in (0x02, 0x05) or struct.unpack_from(">I", plain, offset)[0] != LOCK_PAGE:
            raise RuntimeError(f"锁页 {LOCK_PAGE} 位于页 {parent} 的溢出链，暂不支持迁移，放弃导出")
        patched = plain[:offset] + struct.pack(">I", LOCK_PAGE - 1) + plain[offset + 4 :]
        encrypted = raw[:start] + aes_cbc("-e", aes_key, iv, patched[start:]) + iv
        write_page(handle, parent, encrypted + page_mac(encrypted, parent, hmac_key, hmac_algorithm) + raw[mac_at + mac_size :])


def make_work_dir(db_path: Path, out_path: str) -> Path:
    """校验输出路径与剩余空间，在输出目录下创建隐藏临时目录并返回；由调用方删除"""
    if Path(out_path).resolve() == db_path.resolve():
        raise ValueError("输出路径不能与源数据库相同")
    if Path(out_path).is_dir():
        raise ValueError("输出路径是目录，拒绝覆盖")
    size = db_path.stat().st_size
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(out_dir).free
    if free < size:
        raise RuntimeError(f"输出目录空间不足: 临时副本需要 {size / MIB:.0f} MiB，可用 {free / MIB:.0f} MiB")
    return Path(tempfile.mkdtemp(dir=out_dir, prefix=f".{Path(out_path).name}."))


def copy_plain(db_path: Path, out_path: str, header_size: int) -> None:
    """复制明文库 db_path 及其 -wal 到 out_path，剥除 header_size 字节的文件头；复制完成后才替换 out_path"""
    work = make_work_dir(db_path, out_path)
    tmp_path = str(work / "body")
    wal = db_path.with_name(f"{db_path.name}-wal")
    try:
        copy_body(db_path, tmp_path, header_size)
        if wal.is_file():
            shutil.copyfile(wal, f"{tmp_path}-wal")
            checked = subprocess.run(["sqlcipher", tmp_path], input=b"PRAGMA wal_checkpoint(TRUNCATE);\n", capture_output=True, check=False)
            if checked.returncode != 0:
                raise RuntimeError(sqlcipher_reason(checked.returncode, checked.stderr.decode(errors="replace")))
        os.replace(tmp_path, out_path)
    finally:
        shutil.rmtree(work)


def db_decrypt(db_path: Path, out_path: str, key: str, hmac_algorithm: str, *, verbose: bool = False) -> None:
    """解密 db_path 及其 -wal 到 out_path；剥头副本与导出中的库放在输出目录下的隐藏临时目录，导出成功后才替换 out_path"""
    size = db_path.stat().st_size
    # 迁移锁页要先复制整库并跑一遍 quick_check，缺少 openssl 时在开销发生前报错
    has_lock_page = size >= HEADER_SIZE + LOCK_PAGE * PAGE_SIZE
    if has_lock_page:
        if verbose:
            log("数据库超过 1 GiB，准备临时副本并检查锁页 ...")
        if shutil.which("openssl") is None:
            raise RuntimeError("超过 1 GiB 的库需要 openssl 迁移锁页，未找到 openssl")

    # 导出文件由 sqlcipher 按 umask 创建，sudo 运行时其他用户仍可读取
    work = make_work_dir(db_path, out_path)
    tmp_path, tmp_out = str(work / "body"), str(work / "out")
    wal = db_path.with_name(f"{db_path.name}-wal")
    try:
        copy_body(db_path, tmp_path)
        # QQ 尚未 checkpoint 的提交仍在 WAL 中，副本带上它，sqlcipher 读取时才能看到最新数据
        if wal.is_file():
            shutil.copyfile(wal, f"{tmp_path}-wal")
        hmac_algorithm = resolve_hmac_algorithm(tmp_path, key, hmac_algorithm, verbose=verbose)

        if has_lock_page:
            relocate_lock_page(tmp_path, key, hmac_algorithm, verbose=verbose)

        export_plaintext(tmp_path, tmp_out, key, hmac_algorithm, size)
        os.replace(tmp_out, out_path)
    finally:
        shutil.rmtree(work)


def sqlcipher_reason(code: int, stderr: str) -> str:
    """把 sqlcipher 的多行 stderr 归纳为一行原因；未识别时取末行"""
    if "hmac check failed" in stderr:
        return "解密校验失败"
    lines = [line for line in stderr.splitlines() if line.strip()]
    return f"sqlcipher 失败 ({code}): {lines[-1].strip() if lines else '无输出'}"


def help_text() -> str:
    """返回唯一的帮助文本；stdout 不是终端时移除其中的 ANSI 样式"""
    prog = Path(sys.argv[0]).name
    text = f"""\033[1m解密 QQ NT 数据库文件 -- 导出为标准布局的明文 SQLite 库\033[0m

\033[1;4m用法:\033[0m
  \033[1m{prog}\033[0m -d <目录> [选项] [文件...]

\033[1;4m参数:\033[0m
  \033[1m[文件...]\033[0m                         要解密的文件名 \033[2m(默认: 目录中的全部 .db)\033[0m

\033[1;4m选项:\033[0m
  \033[1m-d, --db-dir <目录>\033[0m               数据库目录
  \033[1m-k, --key <[模式=]密钥[:算法]>\033[0m    密钥规则，可重复
  \033[1m-o, --output-dir <目录=.>\033[0m         输出目录 \033[2m(默认: 当前目录)\033[0m
  \033[1m-f, --name-format <模版>\033[0m          输出文件名模版，斜杠表示目录层
                                    \033[2m(默认: {{filename}})\033[0m
  \033[1m-e, --skip-empty\033[0m                  跳过文件过小的数据库
  \033[1m-c, --copy-plain\033[0m                  复制明文库 \033[2m(默认: 提示后跳过)\033[0m
  \033[1m-v, --verbose\033[0m                     显示详细调试信息
  \033[1m-h, --help\033[0m                        显示本帮助

\033[1;4m密钥规则:\033[0m
  格式为 [模式=]密钥[:算法]，可重复指定；密钥可由同目录的 get_keys.py 取得。
  模式是文件名 glob，省略时匹配全部文件；每个文件使用首条模式匹配的规则，
  专用规则须写在通配规则之前。
  密钥可含 : 与 =，含 = 时须写明模式 (如 '*=密钥')；
  留空表示匹配的文件没有可用密钥。
  算法为 HMAC_SHA1 或 HMAC_SHA512，省略时为 HMAC_SHA1；校验失败时改试另一种。

\033[1;4m明文库:\033[0m
  未加密的 SQLite 文件不需要密钥，带有 1024 字节 QQ 文件头的也按明文库处理。
  默认提示后跳过，不计入失败；开启 --copy-plain 时复制到输出目录，
  剥除 QQ 文件头并合并 -wal 中的数据。

\033[1;4m退出码:\033[0m
  \033[1m0\033[0m  全部文件已导出，或按 --skip-empty、明文库规则跳过
  \033[1m1\033[0m  至少一个文件失败，或未找到 sqlcipher
  \033[1m2\033[0m  参数错误

\033[1;4m示例:\033[0m
  解密目录中的全部 .db
  {prog} -d <目录> -k <密钥> -o out

  只解密指定文件，并指定算法
  {prog} -d <目录> -k <密钥>:HMAC_SHA512 gpro_v1-6_<uid>.db

  gpro 库与其余库使用不同的密钥
  {prog} -d <目录> -k 'gpro_v1-6_*.db=<gpro 密钥>:HMAC_SHA512' -k <密钥>

  连同明文库一并导出，每个库单独一个目录
  {prog} -d <目录> -k <密钥> --copy-plain -o out -f '{{filename}}/data.db'
"""
    return text if sys.stdout.isatty() else re.sub(r"\033\[[0-9;]*m", "", text)


class HelpParser(argparse.ArgumentParser):
    """帮助文本自持，argparse 只负责 -h 的触发与退出"""

    def format_help(self) -> str:
        return help_text()

    def format_usage(self) -> str:
        """参数错误时不输出 argparse 生成的 usage，只保留错误消息"""
        return ""


def main() -> None:
    parser = HelpParser()
    parser.add_argument("-d", "--db-dir", required=True)
    parser.add_argument("-k", "--key", action="append", type=key_rule, default=[])
    parser.add_argument("files", nargs="*")
    parser.add_argument("-o", "--output-dir", default=".")
    parser.add_argument("-f", "--name-format", default="{filename}")
    parser.add_argument("-e", "--skip-empty", action="store_true")
    parser.add_argument("-c", "--copy-plain", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if shutil.which("sqlcipher") is None:
        log("错误: 未找到 sqlcipher，无法解密数据库")
        sys.exit(1)

    db_dir = Path(args.db_dir).expanduser().resolve()
    files = args.files or sorted(db.name for db in db_dir.glob("*.db"))

    failed = 0
    for name in files:
        db_path = db_dir / name
        if not db_path.is_file():
            log(f"无法解密 {name}: 文件不存在")
            failed += 1
            continue
        try:
            header_size = plain_header_size(db_path)
            if header_size is not None:
                if not args.copy_plain:
                    log(f"{name} 是明文库，已跳过 (使用 --copy-plain 复制)")
                    continue
                log(f"正在复制明文库 {name} ...")
                out_path = safe_output_path(args.output_dir, args.name_format.format(filename=name))
                copy_plain(db_path, out_path, header_size)
                continue
            cipher = db_cipher(name, args.key)
            if cipher is None:
                log(f"无法解密 {name}: 缺少可用密钥")
                failed += 1
                continue
            key, hmac_algorithm = cipher
            if args.skip_empty and db_path.stat().st_size < HEADER_SIZE + PAGE_SIZE:
                continue
            log(f"正在解密 {name} ...")
            out_path = safe_output_path(args.output_dir, args.name_format.format(filename=name))
            db_decrypt(db_path, out_path, key, hmac_algorithm, verbose=args.verbose)
        except (ValueError, RuntimeError, OSError) as exc:
            log(f"错误: {name}: {exc}")
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
