"""app.accounts: 取密钥之前的步骤——确定数据根目录、判断是否需要提权，以及取密钥时的缓存与提权重跑。

判定基准: 手工设定的目录状态与取密钥结果。
替身: app.scripts 的 get_keys 与 locate_data (真实行为由 contract/test_app_scripts 背书，记录由 support.records 构造)、
终端选择 choose、运行环境 (sys.platform、os.geteuid、终端探测、个别文件系统调用的权限错误)。不启动子进程。
"""

import io
import json
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support.records import key_entry, record

from app.accounts import locate_data_root, prepare_access, read_keys, valid_keys
from app.scripts import DataLocation
from lib.tui.choose import ChoiceCancelled

__all__ = []

_KEY = "key0123456789!@#"


def _found(platform: str = "linux") -> list[dict[str, object]]:
    return [record(platform, "10001", key_entry(_KEY))]


def _unresolved(reason: str) -> list[dict[str, object]]:
    return [record("linux", "10001", key_entry(None, reason=reason))]


class LocateDataRootTests(unittest.TestCase):
    """只有一个候选时直接采用，多个时询问，没有或取消时以状态码 1 退出。"""

    def _locate(self, roots: list[str], *, choice: object = None) -> tuple[str, str]:
        with (
            patch("app.accounts.locate_data", return_value=DataLocation("linux", roots)),
            patch("app.accounts.choose", side_effect=[choice] if isinstance(choice, int) else choice) as chooser,
            redirect_stderr(io.StringIO()),
        ):
            result = locate_data_root("auto", None)
        self.asked = chooser.called
        return result

    def test_single_root_is_used_without_asking(self) -> None:
        self.assertEqual(self._locate(["/data/qq"]), ("linux", "/data/qq"))
        self.assertFalse(self.asked)

    def test_several_roots_are_offered_for_choice(self) -> None:
        self.assertEqual(self._locate(["/data/native", "/data/flatpak"], choice=1), ("linux", "/data/flatpak"))
        self.assertTrue(self.asked)

    def test_no_root_exits(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self._locate([])
        self.assertEqual(raised.exception.code, 1)

    def test_cancelled_or_unanswerable_choice_exits(self) -> None:
        for error in (ChoiceCancelled("用户取消选择"), EOFError(), ValueError("输入无效")):
            with self.subTest(error=type(error).__name__), self.assertRaises(SystemExit) as raised:
                self._locate(["/data/native", "/data/flatpak"], choice=error)
            self.assertEqual(raised.exception.code, 1)


class ValidKeysTests(unittest.TestCase):
    def test_records_are_passed_through(self) -> None:
        records = _unresolved("not found")
        self.assertIs(valid_keys(records), records)

    def test_no_record_at_all_exits(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            valid_keys([])
        self.assertEqual(raised.exception.code, 1)


class ScanEscalationTests(unittest.TestCase):
    """Linux 下因无权读取 QQ 进程内存而未取得密钥时，询问并得到同意后才以 sudo 重跑。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name) / "keys.json"

    def _read(self, first: list, *, system: str = "linux", as_root: bool = False, confirm: bool = True, interactive: bool = True, after_sudo: list | None = None) -> tuple[list, list[bool]]:
        """返回 (read_keys 的结果, 各次调用 get_keys 时的 as_root)。"""
        calls = []

        def fake_get_keys(user, qq, root_dir, *, platform, key_cache, as_root):
            calls.append(as_root)
            return after_sudo if as_root and after_sudo is not None else first

        # stderr 换成替身: 既吞掉提示，又能控制是否为终端
        with (
            patch("app.accounts.sys.platform", system),
            patch("app.accounts.get_keys", fake_get_keys),
            patch("app.accounts.sys.stdin") as stdin,
            patch("app.accounts.sys.stderr") as stderr,
            patch("app.accounts.choose", return_value=0 if confirm else 1) as chooser,
        ):
            stdin.isatty.return_value = interactive
            stderr.isatty.return_value = interactive
            result = read_keys(None, None, "/data/qq", platform="linux", key_cache=str(self.cache), as_root=as_root)
        self.asked = chooser.called
        return result, calls

    def test_permission_denied_and_confirmed_reruns_with_sudo(self) -> None:
        found = _found()
        result, calls = self._read(_unresolved("permission denied"), after_sudo=found)
        self.assertEqual((result, calls), (found, [False, True]))

    def test_key_obtained_by_the_rerun_is_cached_by_this_unprivileged_process(self) -> None:
        self._read(_unresolved("permission denied"), after_sudo=_found())
        self.assertEqual([entry["keys"][0]["key"] for entry in json.loads(self.cache.read_text(encoding="utf-8"))], [_KEY])

    def test_declined_keeps_the_first_result(self) -> None:
        denied = _unresolved("permission denied")
        result, calls = self._read(denied, confirm=False)
        self.assertEqual((result, calls), (denied, [False]))
        self.assertFalse(self.cache.exists())

    def test_without_a_terminal_nobody_is_asked(self) -> None:
        denied = _unresolved("permission denied")
        result, calls = self._read(denied, interactive=False)
        self.assertEqual((result, calls, self.asked), (denied, [False], False))

    def test_other_reasons_do_not_lead_to_sudo(self) -> None:
        for reason in ("not found", "no key", "no settings.db", "key mismatch"):
            with self.subTest(reason=reason):
                _, calls = self._read(_unresolved(reason))
                self.assertEqual((calls, self.asked), ([False], False))

    def test_windows_has_no_sudo_to_rerun_with(self) -> None:
        _, calls = self._read(_unresolved("permission denied"), system="win32")
        self.assertEqual((calls, self.asked), ([False], False))

    def test_already_privileged_run_is_not_repeated(self) -> None:
        _, calls = self._read(_unresolved("permission denied"), as_root=True)
        self.assertEqual((calls, self.asked), ([True], False))


class KeyCacheTests(unittest.TestCase):
    """windows 与 linux 平台: 缓存文件存在才交给 get_keys，新取得的密钥记入缓存并提示。android 不经缓存。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.default_cache = Path(temporary.name) / "keys.json"

    def _read(self, records: list, *, platform: str = "windows", key_cache: str | None = None) -> tuple[list, list[str | None], str]:
        """返回 (read_keys 的结果, 各次传给 get_keys 的 key_cache, 向 stderr 的输出)。"""
        passed = []

        def fake_get_keys(user, qq, root_dir, *, platform, key_cache, as_root):
            passed.append(key_cache)
            return records

        output = io.StringIO()
        with patch("app.accounts.get_keys", fake_get_keys), patch("app.accounts.DEFAULT_KEY_CACHE", self.default_cache), redirect_stderr(output):
            result = read_keys(None, None, "/data/qq", platform=platform, key_cache=key_cache, as_root=False)
        return result, passed, output.getvalue()

    def test_first_run_scans_without_a_cache_and_stores_the_key(self) -> None:
        found = _found("windows")
        result, passed, output = self._read(found)
        self.assertEqual((result, passed), (found, [None]))
        self.assertTrue(self.default_cache.is_file())
        self.assertIn("windows.10001", output)
        self.assertIn(str(self.default_cache), output)

    def test_later_runs_pass_the_cache_and_stay_quiet(self) -> None:
        found = _found("windows")
        self._read(found)
        result, passed, output = self._read(found)
        self.assertEqual((result, passed, output), (found, [str(self.default_cache)], ""))

    def test_given_cache_file_replaces_the_default(self) -> None:
        given = self.default_cache.with_name("given.json")
        self._read(_found("windows"), key_cache=str(given))
        self.assertTrue(given.is_file())
        self.assertFalse(self.default_cache.exists())
        _, passed, _ = self._read([], key_cache=str(given))
        self.assertEqual(passed, [str(given)])

    def test_android_neither_reads_nor_writes_the_cache(self) -> None:
        self.default_cache.write_text("[]", encoding="utf-8")
        found = [record("android", "10001", key_entry("0123456789abcdef0123456789abcdef"), user="0")]
        result, passed, output = self._read(found, platform="android", key_cache=str(self.default_cache))
        self.assertEqual((result, passed, output), (found, [None], ""))
        self.assertEqual(self.default_cache.read_text(encoding="utf-8"), "[]")

    def test_cache_that_cannot_be_written_only_warns(self) -> None:
        self.default_cache.mkdir()
        found = _found("windows")
        result, passed, output = self._read(found)
        self.assertEqual((result, passed), (found, [None]))
        self.assertIn("密钥缓存", output)


class AndroidAccessTests(unittest.TestCase):
    """android 平台: QQ 私有目录确定不存在时退出；存在但当前身份读不了时返回 True，表示取密钥须经 sudo。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.users = self.root / "data" / "user"
        # 不依赖运行测试者的身份与系统: 固定为 Linux 上的普通用户。Windows 没有 os.geteuid，须以 create 补上
        for replacement in (patch("app.accounts.os.geteuid", return_value=1000, create=True), patch("app.accounts.sys.platform", "linux")):
            replacement.start()
            self.addCleanup(replacement.stop)

    def _create_qq(self, user: str) -> Path:
        directory = self.users / user / "com.tencent.mobileqq"
        (directory / "files" / "uid").mkdir(parents=True)
        return directory

    def _needs_sudo(self, user: str | None = None) -> bool:
        return prepare_access(str(self.root), user, platform="android", decrypting=False)

    def _assert_exits(self, user: str | None = None) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            self._needs_sudo(user)
        self.assertEqual(raised.exception.code, 1)

    def test_readable_qq_needs_no_sudo(self) -> None:
        self._create_qq("0")
        self.assertIs(self._needs_sudo(), False)

    def test_several_readable_qq_directories_need_no_sudo(self) -> None:
        self._create_qq("0")
        self._create_qq("10")
        self.assertIs(self._needs_sudo(), False)

    def test_android_user_without_qq_does_not_force_sudo(self) -> None:
        self._create_qq("0")
        (self.users / "10").mkdir()
        for order in (("0", "10"), ("10", "0")):
            with self.subTest(order=order), patch("app.accounts.Path.iterdir", return_value=[self.users / user for user in order]):
                self.assertIs(self._needs_sudo(), False)

    def test_qq_without_uid_directory_follows_its_own_permissions(self) -> None:
        (self.users / "0" / "com.tencent.mobileqq").mkdir(parents=True)
        self.assertIs(self._needs_sudo(), False)
        with patch("app.accounts.os.access", return_value=False):
            self.assertIs(self._needs_sudo(), True)

    def test_missing_qq_exits(self) -> None:
        situations = {
            "没有 data/user": lambda: None,
            "data/user 为空": lambda: self.users.mkdir(parents=True),
            "各用户下都没有 QQ": lambda: [(self.users / user).mkdir(parents=True, exist_ok=True) for user in ("0", "10")],
        }
        for reason, arrange in situations.items():
            with self.subTest(reason=reason):
                arrange()
                self._assert_exits()

    def test_data_user_that_is_a_file_exits(self) -> None:
        self.users.parent.mkdir(parents=True)
        self.users.touch()
        self._assert_exits()

    def test_selected_user_without_qq_exits_even_if_another_user_has_it(self) -> None:
        self._create_qq("0")
        (self.users / "10").mkdir()
        self._assert_exits("10")

    def test_unlistable_users_directory_needs_sudo(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.Path.iterdir", side_effect=PermissionError("synthetic permission denial")):
            self.assertIs(self._needs_sudo(), True)
            # 指定了用户就不需要列出全部用户
            self.assertIs(self._needs_sudo("0"), False)

    def test_one_unreadable_qq_among_several_needs_sudo(self) -> None:
        self._create_qq("0")
        denied = self._create_qq("10")
        original = Path.stat

        def stat(path, *args, **kwargs):
            if path == denied:
                raise PermissionError("synthetic permission denial")
            return original(path, *args, **kwargs)

        with patch("app.accounts.Path.stat", stat):
            for order in (("0", "10"), ("10", "0")):
                with self.subTest(order=order), patch("app.accounts.Path.iterdir", return_value=[self.users / user for user in order]):
                    self.assertIs(self._needs_sudo(), True)

    def test_unreadable_qq_is_not_mistaken_for_missing(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.Path.stat", side_effect=PermissionError("synthetic permission denial")):
            self.assertIs(self._needs_sudo("0"), True)

    def test_unreadable_uid_directory_needs_sudo_only_for_that_user(self) -> None:
        self._create_qq("0")
        denied = self._create_qq("10") / "files" / "uid"
        original = os.scandir

        def scandir(path):
            if Path(path) == denied:
                raise PermissionError("synthetic permission denial")
            return original(path)

        with patch("app.accounts.os.scandir", side_effect=scandir):
            self.assertEqual([self._needs_sudo(), self._needs_sudo("0"), self._needs_sudo("10")], [True, False, True])

    def test_root_needs_no_sudo_but_still_requires_qq_to_exist(self) -> None:
        with patch("app.accounts.os.geteuid", return_value=0, create=True):
            self._assert_exits()
            self._create_qq("0")
            self.assertIs(self._needs_sudo(), False)

    def test_android_data_can_be_checked_on_windows(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.sys.platform", "win32"), patch("app.accounts.os.geteuid", create=True) as geteuid:
            self.assertIs(self._needs_sudo(), False)
        geteuid.assert_not_called()


class PcAccessTests(unittest.TestCase):
    def test_windows_and_linux_data_is_never_checked_or_escalated_up_front(self) -> None:
        # 数据目录不可访问时由 get_keys.py 报错，不在这里拦截
        for platform in ("windows", "linux"):
            with self.subTest(platform=platform):
                self.assertIs(prepare_access("/nonexistent/qq-data", None, platform=platform, decrypting=False), False)


if __name__ == "__main__":
    unittest.main()
