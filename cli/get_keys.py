#!/usr/bin/env python3
"""读取 QQ NT 数据库密钥与账号信息。

平台指数据来自哪个系统的 QQ, 决定数据根目录下的布局与取密钥的方式, 对外输出同一种 JSON 数组:
  android         按 uid 从文件头派生密钥 (KEY_SOURCES), 不需运行中的 QQ。
  windows, linux  从已登录 QQ 进程内存扫描 raw_key, 用 settings.db 验证; 须在运行该 QQ 的系统上进行。
                  -k 给出的密钥缓存优先于扫描, 同样经验证才采用, 可在任意系统上使用; 本脚本只读缓存。
平台由 -P 指定; auto 时先按 -r 所指数据根目录下的结构识别, 识别不出再看运行系统。
--locate 只输出 {"platform": 判定的平台, "roots": 数据根目录候选}, 供调用方在取密钥前确定 -P 与 -r。

按 -u/-a 过滤账号标记, 格式无效的标记静默跳过; 每条账号记录以 platform 记下所属平台, keys 按匹配优先级排列,
每项含 name、pattern、key、hmac_algorithm、key_note 与 files; files 列出归属该类别的
文件名与字节数, 每个文件只归属首个模式匹配的类别。没有归属文件的类别不列出, 有归属
文件但无法取得密钥时 key 为 null。windows 与 linux 每个账号只产出一条 nt 规则 (单一 raw_key
解全部 *.db), 未登录、权限不足, 或本机不是数据所属的系统且密钥缓存中没有匹配的密钥时 key 为 null。
"""

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

# 以 python cli/get_keys.py 独立运行时 sys.path[0] 是 cli/, 加入仓库根以 import cli.keyscan
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROG = Path(__file__).name


class KeyUnavailable(Exception):
    """密钥获取器无法从匹配的文件取得密钥；消息以文件名开头，后接原因"""


class KeySource(NamedTuple):
    name: str
    # 文件名 glob，可引用账号记录的字段
    pattern: str
    hmac_algorithm: str
    # (账号记录, 归属该类别的文件) -> (密钥, 写入 key_note 的附加信息)
    read: Callable[[dict[str, str], list[Path]], tuple[str, dict[str, str]]]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


def db_rand(dbs: list[Path]) -> str:
    """返回 QQ_NT DB 标记后的 8 位随机串；无合格匹配时返回空串。"""
    # 明文前导位于第 1 页起始的 1024 字节内，按体积升序取首个携带 QQ_NT DB 标记的库
    for db in sorted(dbs, key=lambda path: path.stat().st_size):
        with db.open("rb") as f:
            lines = re.findall(rb"[\x20-\x7e]+", f.read(1024))
        for line, rand in pairwise(lines):
            if b"QQ_NT DB" in line:
                rand = rand.decode("ascii")
                if re.fullmatch(r"[A-Za-z0-9]{8}", rand):
                    return rand
                break
    return ""


def gpro_salt(db_path: Path) -> bytes:
    """读取 gpro 文件头中 Guild DB 标记后的盐值；头部结构不符时返回空字节串。"""
    # 1024 字节明文头部：标记之后依次为 4 字节小端长度与对应长度的盐值
    with db_path.open("rb") as f:
        header = f.read(1024)
    marker = b"Guild DB v1.0.0"
    start = header.find(marker)
    if start < 0:
        return b""
    length_at = start + len(marker)
    length = int.from_bytes(header[length_at:length_at + 4], "little")
    salt = header[length_at + 4:length_at + 4 + length]
    return salt if length == 16 and len(salt) == 16 else b""


def gpro_key(uin: str, salt: bytes) -> str:
    uin_bytes = uin.encode()
    md5_sha1 = md5(hashlib.sha1(uin_bytes).digest())
    user_seed = md5(md5(uin_bytes) + md5_sha1)
    return md5(md5(salt) + user_seed)


def read_nt_key(account: dict[str, str], files: list[Path]) -> tuple[str, dict[str, str]]:
    """缺少 rand 时仍以空串计算密钥"""
    rand = db_rand(files)
    return md5(account["uid_hash"] + rand), {"rand": rand}


def read_gpro_key(account: dict[str, str], files: list[Path]) -> tuple[str, dict[str, str]]:
    db = files[0]
    try:
        salt = gpro_salt(db)
    except OSError as exc:
        raise KeyUnavailable(f"{db.name} 文件头读取失败: {exc}") from exc
    if not salt:
        raise KeyUnavailable(f"{db.name} 文件头无法识别盐值")
    return gpro_key(account["uin"], salt), {"salt": salt.decode("ascii", errors="replace")}


# 顺序即匹配优先级: decrypt_db.py 对每个文件使用首条匹配的规则，专用库须排在通配模式之前
KEY_SOURCES = (
    KeySource("gpro", "gpro_v1-6_{uid}.db", "HMAC_SHA512", read_gpro_key),
    KeySource("nt", "*.db", "HMAC_SHA1", read_nt_key),
)


def scan_accounts(root: Path, user: str | None = None, qq: str | None = None) -> list[dict[str, str]]:
    """按 user 与 qq (uin 或 uid) 过滤账号记录"""
    accounts = []
    pattern = f"data/user/{user or '*'}/com.tencent.mobileqq/files/uid/*"
    for uid_path in sorted(root.glob(pattern)):
        uin, sep, uid = uid_path.name.partition("###")
        if not (sep and uin and uid):
            continue
        if qq and qq not in (uin, uid):
            continue

        qq_path = uid_path.parents[2]
        uid_hash = md5(uid)
        path_hash = md5(uid_hash + "nt_kernel")
        db_dir = qq_path / "databases" / "nt_db" / f"nt_qq_{path_hash}"
        accounts.append({
            "qq_path": str(qq_path),
            "user": qq_path.parent.name,
            "uin": uin,
            "uid": uid,
            "uid_hash": uid_hash,
            "path_hash": path_hash,
            "db_dir": str(db_dir),
        })
    return accounts


def account_keys(account: dict[str, str], *, verbose: bool) -> list[dict[str, object]]:
    who = f"{account['user']}.{account['uin']}"
    keys = []
    claimed = set()
    for source in KEY_SOURCES:
        pattern = source.pattern.format(**account)
        # 文件归属首个模式匹配的类别，与 decrypt_db.py 取首条匹配规则一致
        files = [path for path in sorted(Path(account["db_dir"]).glob(pattern)) if path not in claimed]
        claimed.update(files)
        if not files:
            if verbose:
                log(f"{PROG}: 用户 {who} 无 {source.name} 数据库，未取得 {source.name} 密钥")
            continue
        try:
            key, note = source.read(account, files)
        except KeyUnavailable as exc:
            key, note = None, {}
            if verbose:
                log(f"{PROG}: 用户 {who} 的 {source.name} 数据库 {exc}，未取得 {source.name} 密钥")
        sizes = [{"name": path.name, "size": path.stat().st_size} for path in files]
        keys.append({"name": source.name, "pattern": pattern, "key": key, "hmac_algorithm": source.hmac_algorithm, "key_note": note, "files": sizes})
    return keys


def read_keys_android(root: Path, user: str | None, qq: str | None, *, verbose: bool = False) -> list[dict[str, object]]:
    """Android 分支: 按 uid 从文件头派生各账号密钥。"""
    return [{"platform": "android", **account, "keys": account_keys(account, verbose=verbose)} for account in scan_accounts(root, user, qq)]


def _detect_platform(root_dir: str | None) -> str:
    """auto 平台判定: root_dir 下的结构能识别时以它为准, 否则为运行系统对应的平台。

    有 data/user 为 android, 有 <uin>/nt_qq/nt_db 为 windows, 有 nt_qq_<哈希>/nt_db 为 linux。
    """
    if root_dir is not None:
        root = Path(root_dir).expanduser()
        if (root / "data" / "user").is_dir():
            return "android"
        from cli.keyscan import locate

        layout = locate.detect_layout(root)
        if layout is not None:
            return layout
    return _system_platform()


def _system_platform() -> str:
    """运行系统对应的平台: Windows 为 windows; 其余系统存在 /data/user 为 android, 否则为 linux。"""
    if sys.platform == "win32":
        return "windows"
    return "android" if Path("/data/user").is_dir() else "linux"


def data_roots(platform: str, root_dir: str | None, *, verbose: bool = False) -> list[Path]:
    """platform 的数据根目录候选: 指定了 root_dir 时只有它; 否则 android 为 /, windows 与 linux 为本机默认位置上有数据的目录。

    默认位置为 Windows 的 UserDataInfo.ini 所指的 Tencent Files, Linux 的 ~/.config/QQ 与
    flatpak 的 ~/.var/app/com.qq.QQ/config/QQ (sudo 下回退到调用者的家目录); 可能不止一个,
    本机不是对应的系统时为空。
    """
    if root_dir is not None:
        return [Path(root_dir).expanduser().resolve()]
    if platform == "android":
        return [Path("/")]
    from cli.keyscan import locate

    return [root.resolve() for root in locate.default_data_roots(platform, verbose=verbose)]


def _single_root(platform: str, roots: list[Path]) -> Path:
    """roots 恰有一个时返回它; 没有或不止一个时以 OSError 要求用 -r 指定。"""
    if not roots:
        raise OSError(f"当前按 {platform} 平台处理，没有找到 QQ 数据根目录；请用 -r 指定，或用 -P 更换平台")
    if len(roots) > 1:
        raise OSError(f"当前按 {platform} 平台处理，找到多个 QQ 数据根目录，请用 -r 指定其中之一: {'、'.join(map(str, roots))}")
    return roots[0]


def read_keys_pc(root: Path, qq: str | None, *, layout: str, key_cache: str | None, verbose: bool = False) -> list[dict[str, object]]:
    """windows 与 linux 分支: 按 layout 枚举数据根目录 root 下的账号, 再取各账号 raw_key。

    Windows 布局的账号由目录名 (uin) 枚举, 再尽力从 login.db 补全 uid; Linux 布局的账号目录名是
    uid 的哈希, 必须解密 login.db 才能定位。枚举只读数据目录, 与运行系统无关。
    key_cache 为密钥缓存文件路径, 只读; 其中平台为 layout、uin 相同且通过验证的密钥直接采用; 没有时传 None。
    其余账号在 layout 与运行系统相同时扫描 QQ 进程内存 (Linux 上通常需要 root), 否则记为 no key。
    """
    from cli.keyscan import pc
    from cli.keyscan.key_cache import read_cached_keys

    accounts = _windows_accounts(root, verbose=verbose) if layout == "windows" else _linux_accounts(root, verbose=verbose)
    cached = read_cached_keys(Path(key_cache).expanduser(), platform=layout) if key_cache is not None else {}
    backend = _process_backend() if layout == _system_platform() else None
    return pc.read_keys_pc(qq, accounts, layout=layout, cached=cached, backend=backend, verbose=verbose)


def _process_backend():
    """运行系统的进程后端模块。"""
    if sys.platform == "win32":
        from cli.keyscan import process_windows as backend
    else:
        from cli.keyscan import process_linux as backend
    return backend


def _windows_accounts(root: Path, *, verbose: bool) -> list:
    """Windows 布局: 按目录名 (uin) 枚举账号, 一个都没有时抛 OSError; 再尽力用 login.db 补全 uid, 解不开 login.db 不致命。"""
    from cli.keyscan import locate, login_db

    accounts = locate.windows_accounts(root)
    if not accounts:
        raise OSError(f"当前按 windows 平台处理，未在数据根目录找到账号: {root}；可用 -r 更换数据根目录，或用 -P 更换平台")
    try:
        uid_by_uin = {entry.uin: entry.uid for entry in login_db.read_accounts(locate.windows_login_db(root), verbose=verbose)}
    except OSError as exc:
        if verbose:
            print(f"get_keys: 读取 login.db 补全 uid 失败 (不影响取密钥): {exc}", file=sys.stderr)
        uid_by_uin = {}
    return [account._replace(uid=uid_by_uin.get(account.uin, account.uid)) for account in accounts]


def _linux_accounts(root: Path, *, verbose: bool) -> list:
    """Linux 布局: 读取并合并各候选 login.db 的账号, 计算各账号的 nt_db 目录。

    部分安装把 login.db 放在第二种布局; 逐个读取存在的候选并按 uin 去重合并, 冲突时以靠前的
    候选为准。存在的候选都读不了时抛最后一个 OSError, 一个候选都不存在时抛 OSError。
    """
    from cli.keyscan import locate, login_db

    merged: dict[str, login_db.Account] = {}
    read_any = False
    last_error: OSError | None = None
    for path in locate.linux_login_db_candidates(root):
        if not path.is_file():
            continue
        try:
            entries = login_db.read_accounts(path, verbose=verbose)
        except OSError as exc:
            last_error = exc
            continue
        read_any = True
        for entry in entries:
            merged.setdefault(entry.uin, entry)
    if not read_any:
        raise last_error or OSError(f"当前按 linux 平台处理，未在数据根目录找到 login.db: {root}；可用 -r 更换数据根目录，或用 -P 更换平台")

    accounts = []
    for entry in merged.values():
        db_dir = locate.account_db_dir(root, entry.uid)
        accounts.append(locate.PcAccount(uin=entry.uin, uid=entry.uid, qq_path=str(db_dir.parent), db_dir=str(db_dir)))
    return accounts


def help_text() -> str:
    """返回唯一的帮助文本；stdout 不是终端时移除其中的 ANSI 样式"""
    prog = Path(sys.argv[0]).name
    text = f"""\033[1m读取 QQ NT 数据库密钥与账号信息 -- 输出 JSON 数组\033[0m

\033[1;4m用法:\033[0m
  \033[1m{prog}\033[0m [选项]

\033[1;4m选项:\033[0m
  \033[1m-P, --platform <平台>\033[0m             数据所属的平台 \033[2m(默认: auto)\033[0m
  \033[1m-u, --user <ID>\033[0m                   Android 用户 ID \033[2m(仅 android)\033[0m
  \033[1m-a, --qq <uin/uid>\033[0m                QQ uin 或 uid 文本
  \033[1m-r, --root-dir <目录>\033[0m             数据根目录 \033[2m(默认: 平台的默认位置)\033[0m
  \033[1m-k, --key-cache <文件>\033[0m            密钥缓存，只读 \033[2m(默认: 不使用)\033[0m
  \033[1m-l, --locate\033[0m                      只输出判定的平台与数据根目录候选，不取密钥
  \033[1m-v, --verbose\033[0m                     显示详细调试信息
  \033[1m-h, --help\033[0m                        显示本帮助

\033[1;4m平台:\033[0m
  数据来自哪个系统的 QQ，决定数据根目录下的结构与取密钥的方式，
  与运行本脚本的系统无关。
  \033[1mandroid\033[0m   按 uid 从文件头派生密钥，不需要运行中的 QQ
  \033[1mwindows\033[0m   每账号单一 raw_key 解全部库; 先取 -k 密钥缓存中通过验证的密钥，
            没有时从已登录 QQ 进程内存扫描，扫描须在运行该 QQ 的系统上进行
  \033[1mlinux\033[0m     同 windows; 扫描通常需 root
  \033[1mauto\033[0m      指定了 -r 时按其下的结构识别; 识别不出或未指定时看运行系统:
            Windows 为 windows，存在 /data/user 为 android，其余为 linux

\033[1;4m数据根目录:\033[0m
  \033[1mandroid\033[0m   默认为 /，其下为 data/user/<ID>/com.tencent.mobileqq
  \033[1mwindows\033[0m   默认为 QQ 配置所指的 Tencent Files，其下为 <uin>/nt_qq/nt_db
  \033[1mlinux\033[0m     默认为 ~/.config/QQ 或 flatpak 的 ~/.var/app/com.qq.QQ/config/QQ，
            其下为 nt_qq_<哈希>/nt_db
  默认位置只在对应的系统上提供; 没有或不止一个时须用 -r 指定。

\033[1;4m密钥缓存:\033[0m
  此前取得的密钥，格式即本脚本输出的 JSON 数组，可以只保留部分字段:
  只读取各记录的 platform、uin 与 keys 中的 key。
  raw_key 随设备而不同，同一平台的同一 uin 可有多条记录。
  只试平台与 uin 都相同的密钥，后写入的在前，用 settings.db 验证通过才采用，
  并优先于扫描进程内存。本脚本只读缓存，写入由调用方完成。
  android 的密钥由文件头派生，不读取密钥缓存。

\033[1;4m输出:\033[0m
  每个匹配的账号一条记录，含 platform、user、uin、uid、db_dir 与 keys。
  keys 按匹配优先级列出各类数据库的 name、pattern、key、hmac_algorithm、
  key_note 与 files。
  files 列出归属该类别的文件名与字节数，每个文件只归属首个模式匹配的类别。
  没有归属文件的类别不列出，有归属文件但无法取得密钥时 key 为 null。

\033[1;4m示例:\033[0m
  读取全部账号的密钥 (自动判定平台)
  {prog}

  只读取 Android 用户 0 下指定账号的密钥
  {prog} -P android -u 0 -a <uin>

  从其他 Android 数据根目录读取，其下须有 data/user/<ID>/com.tencent.mobileqq
  {prog} -r <目录>

  把输出保存为密钥缓存; 之后不需要 QQ 运行，也可以带到其他系统处理拷贝来的数据
  {prog} > keys.json
  {prog} -r <数据根目录> -k keys.json
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
    parser.add_argument("-u", "--user")
    parser.add_argument("-a", "--qq")
    parser.add_argument("-r", "--root-dir")
    parser.add_argument("-P", "--platform", choices=("auto", "android", "windows", "linux"), default="auto")
    parser.add_argument("-k", "--key-cache")
    parser.add_argument("-l", "--locate", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    platform = _detect_platform(args.root_dir) if args.platform == "auto" else args.platform
    roots = data_roots(platform, args.root_dir, verbose=args.verbose)
    if args.locate:
        print(json.dumps({"platform": platform, "roots": [str(root) for root in roots]}, ensure_ascii=False, indent=2))
        return

    root = _single_root(platform, roots)
    if platform == "android":
        records = read_keys_android(root, args.user, args.qq, verbose=args.verbose)
    else:
        records = read_keys_pc(root, args.qq, layout=platform, key_cache=args.key_cache, verbose=args.verbose)

    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(f"{PROG}: {exc}")
