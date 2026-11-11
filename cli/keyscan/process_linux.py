"""Linux 进程后端: 枚举 QQ 进程、列可读内存区域、读进程内存。

经 /proc 与 ctypes 调用 libc 的 process_vm_readv, 不引入第三方依赖。
读取其他进程内存需要 root 或 CAP_SYS_PTRACE, 并受 /proc/sys/kernel/yama/ptrace_scope 限制;
打不开时 ProcessReader 抛 OSError。

接口与 process_windows 一致: find_qq_pids() 得到候选 pid, 再对每个 pid 用
ProcessReader 枚举区域并读取, 用后 close()。
"""

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Self

__all__ = ["ProcessReader", "find_qq_pids", "find_wrapper_node_pids", "is_qq_process_name"]

_WRAPPER_NODE = "wrapper.node"


class _IOVec(ctypes.Structure):
    _fields_ = [("iov_base", ctypes.c_void_p), ("iov_len", ctypes.c_size_t)]


_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
_libc.process_vm_readv.restype = ctypes.c_ssize_t
_libc.process_vm_readv.argtypes = [ctypes.c_int, ctypes.POINTER(_IOVec), ctypes.c_ulong, ctypes.POINTER(_IOVec), ctypes.c_ulong, ctypes.c_ulong]


def _pids() -> list[int]:
    return [int(name) for name in os.listdir("/proc") if name.isdigit()]


def _comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def is_qq_process_name(name: str) -> bool:
    """进程名是否属于 QQ NT; 接受 qq 及 qq 前缀的进程名, 不区分大小写。"""
    stem = name.rsplit(".", 1)[0].lower() if name else ""
    return stem == "qq" or stem.startswith("qq")


def _maps_has_wrapper(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/maps", encoding="utf-8", errors="replace") as maps:
            return any(_WRAPPER_NODE in line for line in maps)
    except OSError:
        return False


def find_wrapper_node_pids() -> list[int]:
    """枚举 /proc/<pid>/maps 引用 wrapper.node 的进程, 即 QQ NT 主进程; 无权读取的进程不列出。"""
    return [pid for pid in _pids() if _maps_has_wrapper(pid)]


def find_qq_pids() -> list[tuple[int, str]]:
    """返回待扫描的 QQ 进程 (pid, 进程名)。

    有加载 wrapper.node 的主进程时只返回主进程: Electron 的 zygote/utility 等子进程不持有
    数据库, 实测扫不出候选, 本机 10 个子进程白读约 10 秒。一个主进程都识别不到时 (例如无权
    读取 maps), 退回所有名字匹配 QQ 的进程, 由调用方逐个尝试。
    """
    mains = find_wrapper_node_pids()
    if mains:
        return [(pid, _comm(pid)) for pid in mains]
    return [(pid, name) for pid in _pids() if is_qq_process_name(name := _comm(pid))]


class ProcessReader:
    """以只读方式访问 pid 的内存, 提供 regions() 与 read(); close() 为接口对称, 无句柄需释放。"""

    def __init__(self, pid: int) -> None:
        """读取 pid 的 /proc/<pid>/maps; 进程不存在或无权读取时抛 OSError。"""
        maps = Path(f"/proc/{pid}/maps").read_text(encoding="utf-8", errors="replace")
        self._pid = pid
        self._regions = _parse_maps(maps)

    def regions(self) -> list[tuple[int, int]]:
        """返回可读内存区域的 (基址, 字节数) 列表。"""
        return self._regions

    def read(self, addr: int, size: int) -> bytearray:
        """读取 addr 处至多 size 字节; 失败时返回空 bytearray。"""
        # process_vm_readv 直接写入 bytearray, 省掉 buf.raw 与切片两次拷贝 (主进程 3.2 GB 时 3.4 s -> 1.1 s)
        buf = bytearray(size)
        view = (ctypes.c_char * size).from_buffer(buf)
        local = _IOVec(ctypes.addressof(view), size)
        remote = _IOVec(addr, size)
        n = _libc.process_vm_readv(self._pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
        # 导出缓冲区的视图存在时 bytearray 不能改变大小, 先释放再截断
        del view
        if n <= 0:
            return bytearray()
        del buf[n:]
        return buf

    def close(self) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _parse_maps(text: str) -> list[tuple[int, int]]:
    """解析 maps 文本, 保留权限位以 r 开头的区域。"""
    regions = []
    for line in text.splitlines():
        address, _, rest = line.partition(" ")
        if not rest.startswith("r"):
            continue
        start, sep, end = address.partition("-")
        if not sep:
            continue
        try:
            lo, hi = int(start, 16), int(end, 16)
        except ValueError:
            continue
        if hi > lo:
            regions.append((lo, hi - lo))
    return regions
