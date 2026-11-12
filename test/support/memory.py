"""假的进程内存与进程后端，用来在没有 QQ 进程的情况下驱动内存扫描。

QQ 把 SQLCipher 的算法标记 \\x09HMAC_SHA1 留在密钥附近，扫描以它为锚点；这一事实出自 QQBackup/x_key_scanner。
"""

__all__ = ["ANCHOR", "FakeBackend", "memory_with_key", "put_anchor"]

ANCHOR = b"\x09HMAC_SHA1"


def put_anchor(buffer: bytearray, slot: int) -> None:
    """在 16 字节对齐的 slot 处放一个锚点: slot 为长度前缀之前的字节，标记从 slot + 1 开始。"""
    buffer[slot] = 0x00
    buffer[slot + 1:slot + 1 + len(ANCHOR)] = ANCHOR


def memory_with_key(key: bytes) -> bytes:
    """一段 4 KiB 的内存，锚点旁 0x100 字节处放着 key。"""
    buffer = bytearray(0x1000)
    put_anchor(buffer, 0x800)
    buffer[0x900:0x900 + len(key)] = key
    return bytes(buffer)


class FakeBackend:
    """进程后端的替身，接口同 process_windows / process_linux: find_qq_pids 与 ProcessReader。

    memories 为 pid -> 内存字节；denied 中的 pid 打开时抛 PermissionError；
    unreadable 中的 pid 能打开但读不到任何字节 (Linux 受 ptrace_scope 限制时的表现)。
    scanned 记录被打开过的 pid。
    """

    def __init__(self, memories: dict[int, bytes], *, denied: tuple[int, ...] = (), unreadable: tuple[int, ...] = ()) -> None:
        self.scanned: list[int] = []
        backend = self

        class ProcessReader:
            def __init__(self, pid: int) -> None:
                backend.scanned.append(pid)
                if pid in denied:
                    raise PermissionError(5, "Access is denied")
                self._data = b"" if pid in unreadable else memories.get(pid, b"")
                self._size = len(memories.get(pid, bytes(0x1000)))

            def regions(self) -> list[tuple[int, int]]:
                return [(0, self._size)]

            def read(self, addr: int, size: int) -> bytes:
                return self._data[addr:addr + size]

            def close(self) -> None:
                pass

        self.ProcessReader = ProcessReader
        self._pids = [*memories, *denied, *unreadable]

    def find_qq_pids(self) -> list[tuple[int, str]]:
        return [(pid, "QQ.exe") for pid in self._pids]
