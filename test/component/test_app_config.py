"""app.config 与 app.env: 命令行参数的缺省值补全，取值优先级为 命令行 > 环境变量 > 仓库根目录的 .env。

判定基准: 手工设定的三处取值。
环境替身: 进程环境变量整体替换；.env 改指到临时文件 (app.env.ENV_FILE)。不读开发者本机的配置。
"""

import argparse
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.config import resolve_options
from app.env import flag_setting, path_setting, text_setting

__all__ = []


class _ConfigCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env_file = Path(temporary.name) / ".env"
        for replacement in (patch.dict(os.environ, {}, clear=True), patch("app.env.ENV_FILE", self.env_file)):
            replacement.start()
            self.addCleanup(replacement.stop)

    def _dotenv(self, content: str) -> None:
        self.env_file.write_text(content, encoding="utf-8")

    def _resolve(self, **options: object) -> argparse.Namespace:
        args = argparse.Namespace(**options)
        resolve_options(args)
        return args


class DefaultTests(_ConfigCase):
    def test_nothing_given_anywhere(self) -> None:
        args = self._resolve()
        self.assertEqual(
            {name: getattr(args, name) for name in ("platform", "user", "qq", "output_dir", "db_dir", "root_dir", "key_cache", "profile_db", "nt_msg_db", "sudo_notice", "verbose")},
            {"platform": "auto", "user": None, "qq": None, "output_dir": ".", "db_dir": None, "root_dir": None, "key_cache": None, "profile_db": None, "nt_msg_db": None, "sudo_notice": False, "verbose": False},
        )


class PrecedenceTests(_ConfigCase):
    def test_platform(self) -> None:
        self._dotenv("QQDUMP_PLATFORM=windows\n")
        self.assertEqual(self._resolve().platform, "windows")
        os.environ["QQDUMP_PLATFORM"] = "android"
        self.assertEqual(self._resolve().platform, "android")
        self.assertEqual(self._resolve(platform="linux").platform, "linux")
        # 命令行显式给出 auto 也算给出
        self.assertEqual(self._resolve(platform="auto").platform, "auto")

    def test_path_options(self) -> None:
        variables = {"root_dir": "QQDUMP_ROOT_DIR", "key_cache": "QQDUMP_KEY_CACHE", "profile_db": "QQDUMP_PROFILE_DB", "nt_msg_db": "QQDUMP_NT_MSG_DB"}
        # 绝对路径的写法随系统而不同，取临时目录下的路径
        from_dotenv = self.env_file.parent / "from-dotenv"
        for option, variable in variables.items():
            with self.subTest(option=option):
                self._dotenv(f"{variable}={from_dotenv}\n")
                self.assertEqual(Path(getattr(self._resolve(), option)), from_dotenv)
                with patch.dict(os.environ, {variable: "/from/environment"}):
                    self.assertEqual(getattr(self._resolve(), option), "/from/environment")
                    self.assertEqual(getattr(self._resolve(**{option: "/from/command-line"}), option), "/from/command-line")

    def test_flags(self) -> None:
        for option, variable in {"sudo_notice": "QQDUMP_SUDO_NOTICE", "verbose": "QQDUMP_VERBOSE"}.items():
            with self.subTest(option=option):
                self._dotenv(f"{variable}=1\n")
                self.assertIs(getattr(self._resolve(), option), True)
                with patch.dict(os.environ, {variable: "0"}):
                    self.assertIs(getattr(self._resolve(), option), False)
                    self.assertIs(getattr(self._resolve(**{option: True}), option), True)
                # 命令行的 --no-xxx 压过环境中的开启
                self.assertIs(getattr(self._resolve(**{option: False}), option), False)

    def test_ignore_env_skips_environment_and_dotenv(self) -> None:
        self._dotenv("QQDUMP_ROOT_DIR=/from/dotenv\nQQDUMP_VERBOSE=1\n")
        os.environ.update({"QQDUMP_PLATFORM": "android", "QQDUMP_KEY_CACHE": "/from/environment"})
        args = self._resolve(ignore_env=True)
        self.assertEqual((args.platform, args.root_dir, args.key_cache, args.verbose), ("auto", None, None, False))
        self.assertEqual(self._resolve(ignore_env=True, platform="linux", root_dir="/from/command-line").root_dir, "/from/command-line")


class DotenvFileTests(_ConfigCase):
    def test_comments_blank_lines_and_lines_without_equals_are_ignored(self) -> None:
        self._dotenv("# 注释\n\nQQDUMP_PLATFORM=linux\nnot a setting\n  # QQDUMP_VERBOSE=1\n")
        self.assertEqual(text_setting("QQDUMP_PLATFORM"), "linux")
        self.assertIs(flag_setting("QQDUMP_VERBOSE"), False)

    def test_surrounding_quotes_and_spaces_are_removed(self) -> None:
        self._dotenv("A = 'single quoted'\nB=\"double quoted\"\nC =  spaced  \nD='unbalanced\"\n")
        self.assertEqual([text_setting(name) for name in "ABCD"], ["single quoted", "double quoted", "spaced", "'unbalanced\""])

    def test_relative_paths_are_resolved_against_the_dotenv_directory(self) -> None:
        absolute = self.env_file.parent.parent / "elsewhere" / "qq"
        self._dotenv(f"RELATIVE=data/keys.json\nABSOLUTE={absolute}\nEMPTY=\n")
        self.assertEqual(Path(path_setting("RELATIVE")), self.env_file.parent / "data" / "keys.json")
        self.assertEqual(Path(path_setting("ABSOLUTE")), absolute)
        self.assertIsNone(path_setting("EMPTY"))
        self.assertIsNone(path_setting("ABSENT"))

    def test_environment_paths_are_returned_as_given(self) -> None:
        with patch.dict(os.environ, {"RELATIVE": "data/keys.json"}):
            self.assertEqual(path_setting("RELATIVE"), "data/keys.json")

    def test_flag_values(self) -> None:
        for value, expected in {"1": True, "true": True, "YES": True, " on ": True, "0": False, "false": False, "": False, "enabled": False}.items():
            with self.subTest(value=value), patch.dict(os.environ, {"FLAG": value}):
                self.assertIs(flag_setting("FLAG"), expected)
        self.assertIs(flag_setting("ABSENT"), False)

    def test_reading_settings_does_not_change_the_process_environment(self) -> None:
        self._dotenv("QQDUMP_PLATFORM=linux\n")
        text_setting("QQDUMP_PLATFORM")
        self.assertNotIn("QQDUMP_PLATFORM", os.environ)


if __name__ == "__main__":
    unittest.main()
