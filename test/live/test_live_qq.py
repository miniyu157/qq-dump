"""实机层: 对本机真实的 QQ 数据取密钥并解密，检验 QQ 更新后取密钥与解密是否仍然成立。

判定基准: 取到的密钥能让真实的库通过 SQLite 完整性检查。
默认跳过，设置 QQDUMP_TEST_LIVE=1 后运行；QQDUMP_TEST_LIVE_BIG=1 另外解密一个超过 1 GiB 的库 (验证锁页迁移)。
只调用 cli 脚本，不读写密钥缓存；解密输出在临时目录，结束后删除。windows 与 linux 须 QQ 正在运行并已登录。
"""

import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.cli import run_script
from support.requires import live, live_big, needs_openssl, needs_sqlcipher

__all__ = []

_GIB = 1024**3


def _system_platform() -> str:
    """运行系统对应的平台，规则同帮助: Windows 为 windows，存在 /data/user 为 android，其余为 linux。"""
    if sys.platform == "win32":
        return "windows"
    return "android" if Path("/data/user").is_dir() else "linux"


def _check(path: Path, pragma: str) -> str:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute(f"PRAGMA {pragma}").fetchone()[0]
    finally:
        conn.close()


@live
@needs_sqlcipher
class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.platform = _system_platform()
        located = run_script("get_keys.py", "--locate", "-P", cls.platform)
        if located.code != 0 or not located.json()["roots"]:
            raise unittest.SkipTest(f"本机没有 {cls.platform} 平台的 QQ 数据根目录")
        cls.root = located.json()["roots"][0]
        result = run_script("get_keys.py", "-P", cls.platform, "-r", cls.root)
        if result.code != 0:
            raise AssertionError(f"get_keys.py 失败 ({result.code}): {result.err}")
        cls.records = result.json()
        cls.log = result.err

    def _usable(self) -> list[tuple[dict[str, object], dict[str, object]]]:
        """(账号记录, 有密钥的规则) 列表；一个都没有时说明原因并跳过或失败。"""
        usable = [(record, entry) for record in self.records for entry in record["keys"] if entry["key"]]
        if usable:
            return usable
        reasons = {entry["key_note"].get("reason") for record in self.records for entry in record["keys"]}
        if reasons == {"permission denied"}:
            self.skipTest(f"无权读取 QQ 进程内存，请以 root 运行: sudo QQDUMP_TEST_LIVE=1 {sys.executable} -m unittest discover -s test/live -t test")
        # QQ 在运行并已登录却一个账号也没取到，正是本层要发现的回归；QQ 没运行或停在登录界面时同样会到这里，由运行者判断
        self.fail(f"没有任何账号取得密钥 (原因: {sorted(map(str, reasons))})。若 QQ 正在运行并已登录，说明取密钥的方式已不适用于当前版本。\n{self.log}")

    def _decrypt(self, record: dict[str, object], entry: dict[str, object], name: str, out: Path):
        rule = f"{entry['pattern']}={entry['key']}:{entry['hmac_algorithm']}"
        return run_script("decrypt_db.py", "-d", record["db_dir"], "-k", rule, "-o", str(out), name)

    def test_obtained_key_opens_a_real_database(self) -> None:
        record, entry = self._usable()[0]
        names = [file["name"] for file in sorted(entry["files"], key=lambda file: file["size"]) if file["size"] > 5120]
        name = "settings.db" if "settings.db" in names else names[0]
        with TemporaryDirectory() as directory:
            result = self._decrypt(record, entry, name, Path(directory))
            self.assertEqual(result.code, 0, result.err)
            self.assertEqual(_check(Path(directory) / name, "integrity_check"), "ok")

    @live_big
    @needs_openssl
    def test_database_larger_than_one_gib_survives_lock_page_relocation(self) -> None:
        big = [(record, entry, file) for record, entry in self._usable() for file in entry["files"] if file["size"] > _GIB]
        if not big:
            self.skipTest("本机已取得密钥的账号下没有超过 1 GiB 的库")
        record, entry, file = max(big, key=lambda item: item[2]["size"])
        # 解密时输出目录约需源库两倍的空间，临时目录所在的盘须放得下
        with TemporaryDirectory() as directory:
            result = self._decrypt(record, entry, file["name"], Path(directory))
            self.assertEqual(result.code, 0, result.err)
            self.assertEqual(_check(Path(directory) / file["name"], "quick_check"), "ok")


if __name__ == "__main__":
    unittest.main()
