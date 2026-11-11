"""Windows 进程后端: 枚举 QQ 进程、列可读内存区域、读进程内存。

全部经 ctypes 调用 kernel32, 不引入第三方依赖。
识别到加载 wrapper.node 的主进程时只扫主进程; 主进程的模块快照可能被拒, 识别不到时退回
所有名为 QQ 的进程, 由调用方逐个扫描并用 settings.db 验证来确定目标。

同一用户下读 QQ 进程内存通常不需要管理员。经 venv 的 Scripts\\python.exe 启动器运行时,
进程快照曾看不到主进程, 应直接用基础解释器运行; 打不开的进程由调用方计为权限不足。

调用顺序: find_qq_pids() 得到候选 pid, 再对每个 pid 用 ProcessReader 枚举区域并读取。
ProcessReader 必须 close() 释放句柄, 建议用 with 语句。
"""

import ctypes
from ctypes import wintypes
from typing import Self

__all__ = ["ProcessReader", "find_qq_pids", "find_wrapper_node_pids", "is_qq_process_name"]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_TH32CS_SNAPPROCESS = 0x00000002
_TH32CS_SNAPMODULE = 0x00000008
_TH32CS_SNAPMODULE32 = 0x00000010
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_MAX_MODULE_NAME32 = 255
_MAX_PATH = 260

_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_VM_READ = 0x0010

_MEM_COMMIT = 0x1000
_PAGE_GUARD = 0x100
# 可读的页保护位 (取低字节与这些比较)
_READABLE = frozenset({0x02, 0x04, 0x08, 0x20, 0x40, 0x80})

_WRAPPER_NODE = "wrapper.node"


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


class _MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (_MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * _MAX_PATH),
    ]


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)]
_kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MODULEENTRY32W)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.VirtualQueryEx.restype = ctypes.c_size_t
_kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
_kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def _process_has_wrapper(pid: int) -> bool:
    """pid 是否加载了 wrapper.node 模块; 快照失败 (受保护/系统进程) 视为否。"""
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPMODULE | _TH32CS_SNAPMODULE32, pid)
    if snap == _INVALID_HANDLE_VALUE:
        return False
    try:
        entry = _MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(_MODULEENTRY32W)
        ok = _kernel32.Module32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szModule.lower() == _WRAPPER_NODE:
                return True
            ok = _kernel32.Module32NextW(snap, ctypes.byref(entry))
        return False
    finally:
        _kernel32.CloseHandle(snap)


def find_wrapper_node_pids() -> list[int]:
    """返回加载了 wrapper.node 的 QQ 进程 pid, 即 QQ NT 主进程。

    只检查名为 QQ 的进程; 对全系统逐个做模块快照本机实测约 175 ms, 只查 QQ 进程约 5 ms。
    模块快照被拒的进程不会出现在结果中, 定位目标进程应以 find_qq_pids() 为准。
    """
    return [pid for pid, _ in _snapshot_qq_processes() if _process_has_wrapper(pid)]


def is_qq_process_name(name: str) -> bool:
    """进程镜像名是否属于 QQ NT; 比较不含扩展名的主干, 接受 qq 及 qq 前缀的辅助进程。"""
    stem = name.rsplit(".", 1)[0].lower() if name else ""
    return stem == "qq" or stem.startswith("qq")


def find_qq_pids() -> list[tuple[int, str]]:
    """返回待扫描的 QQ 进程 (pid, 镜像名)。

    有加载 wrapper.node 的主进程时只返回主进程: 渲染、GPU 等子进程不持有数据库, 实测扫不出
    候选, 本机 7 个子进程白读约 3.7 秒。主进程的模块快照可能被拒, 一个主进程都识别不到时
    退回快照中所有名为 QQ 的进程, 由调用方逐个尝试。
    """
    found = _snapshot_qq_processes()
    mains = [(pid, name) for pid, name in found if _process_has_wrapper(pid)]
    return mains or found


def _snapshot_qq_processes() -> list[tuple[int, str]]:
    """进程快照中名为 QQ 的 (pid, 镜像名), 按快照顺序; 快照失败时返回空列表。"""
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == _INVALID_HANDLE_VALUE:
        return []
    found = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            if is_qq_process_name(name):
                found.append((entry.th32ProcessID, name))
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)
    return found


class ProcessReader:
    """以只读方式打开 pid, 提供 regions() 与 read(); 用后须 close()。"""

    def __init__(self, pid: int) -> None:
        """打开 pid 的句柄 (仅查询与读内存权限); 失败时抛 OSError, 多因目标进程提权或受保护。"""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_INFORMATION | _PROCESS_VM_READ, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle

    def regions(self) -> list[tuple[int, int]]:
        """枚举已提交、可读、非 guard 的内存区域, 返回 (基址, 字节数) 列表。"""
        regions = []
        info = _MEMORY_BASIC_INFORMATION()
        size = ctypes.sizeof(info)
        addr = 0
        while _kernel32.VirtualQueryEx(self._handle, ctypes.c_void_p(addr), ctypes.byref(info), size):
            base = info.BaseAddress or 0
            region_size = info.RegionSize
            committed = info.State == _MEM_COMMIT
            guarded = bool(info.Protect & _PAGE_GUARD)
            readable = (info.Protect & 0xFF) in _READABLE
            if committed and not guarded and readable and region_size > 0:
                regions.append((base, region_size))
            nxt = base + region_size
            if nxt <= addr:
                break
            addr = nxt
        return regions

    def read(self, addr: int, size: int) -> bytearray:
        """读取 addr 处至多 size 字节; 部分成功时返回已读部分, 完全失败返回空 bytearray。"""
        # ReadProcessMemory 直接写入 bytearray, 省掉 ctypes 数组切片与 bytes() 两次拷贝
        buf = bytearray(size)
        view = (ctypes.c_char * size).from_buffer(buf)
        read_bytes = ctypes.c_size_t(0)
        ok = _kernel32.ReadProcessMemory(self._handle, ctypes.c_void_p(addr), view, size, ctypes.byref(read_bytes))
        # 导出缓冲区的视图存在时 bytearray 不能改变大小, 先释放再截断
        del view
        if not ok and read_bytes.value == 0:
            return bytearray()
        del buf[read_bytes.value:]
        return buf

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
