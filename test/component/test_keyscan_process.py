"""cli.keyscan 的进程后端: 枚举 QQ 进程，读取进程内存。按运行系统选择 process_windows 或 process_linux。

判定基准: 测试进程自身。读取器打开本进程，读回一段内容已知的缓冲区；不需要 QQ，也不需要特权。
QQ 进程的真实内存布局不在这里验证，见实机层。
"""

import ctypes
import os
import sys
import unittest

try:
    if sys.platform == "win32":
        from cli.keyscan import process_windows as backend
    else:
        from cli.keyscan import process_linux as backend
except (ImportError, OSError, AttributeError) as exc:
    raise unittest.SkipTest(f"本系统没有可用的进程后端: {exc}") from exc

__all__ = []

_MARKER = b"qq-dump process reader self test \x00\x01\x02\xff"


class ProcessReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.buffer = ctypes.create_string_buffer(_MARKER, 4096)
        self.address = ctypes.addressof(self.buffer)

    def test_reads_back_known_bytes_of_this_process(self) -> None:
        with backend.ProcessReader(os.getpid()) as reader:
            self.assertEqual(bytes(reader.read(self.address, len(_MARKER))), _MARKER)
            self.assertEqual(bytes(reader.read(self.address + 3, 5)), _MARKER[3:8])

    def test_readable_regions_cover_the_buffer(self) -> None:
        with backend.ProcessReader(os.getpid()) as reader:
            regions = reader.regions()
        self.assertTrue(any(base <= self.address and self.address + len(_MARKER) <= base + size for base, size in regions))
        self.assertTrue(all(size > 0 for _, size in regions))

    def test_unmapped_address_yields_no_bytes(self) -> None:
        with backend.ProcessReader(os.getpid()) as reader:
            self.assertEqual(len(reader.read(0x10, 16)), 0)

    def test_process_that_does_not_exist_cannot_be_opened(self) -> None:
        with self.assertRaises(OSError):
            backend.ProcessReader(0x7FFFFFF0)


class ProcessListingTests(unittest.TestCase):
    def test_process_names(self) -> None:
        self.assertTrue(backend.is_qq_process_name("QQ.exe" if sys.platform == "win32" else "qq"))
        self.assertFalse(backend.is_qq_process_name("python"))

    def test_listing_yields_pid_and_name_pairs(self) -> None:
        # 本机可能没有 QQ 在运行，只断言调用成功且形状正确；本进程不是 QQ
        found = backend.find_qq_pids()
        self.assertTrue(all(isinstance(pid, int) and isinstance(name, str) for pid, name in found))
        self.assertNotIn(os.getpid(), [pid for pid, _ in found])


if __name__ == "__main__":
    unittest.main()
