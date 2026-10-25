"""QQ 头像抓取与 24 小时磁盘缓存。"""

import os
import tempfile
import time
import urllib.request
from pathlib import Path

__all__ = ["avatar", "prepare_cache"]

_URL = "https://q1.qlogo.cn/g?b=qq&nk={uin}&s=140"
_TTL = 24 * 60 * 60
_CACHE = Path(__file__).resolve().parents[1] / ".cache" / "avatars"


def prepare_cache() -> None:
    """创建缓存目录；不可写时在启动阶段直接暴露错误"""
    _CACHE.mkdir(parents=True, exist_ok=True)


def _image_type(data: bytes) -> str:
    """按文件头判断图片类型，未知类型按二进制处理"""
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _fetch(uin: str) -> bytes | None:
    """从 QQ 头像接口读取原始字节，失败返回 None"""
    request = urllib.request.Request(_URL.format(uin=uin), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read()
    except OSError:
        return None


def avatar(uin: str) -> tuple[bytes, str] | None:
    """返回头像字节与 MIME；非数字 UIN 返回 None，24 小时内命中缓存直接读取，抓取失败时回退到过期缓存"""
    if not uin.isdigit():
        return None
    path = _CACHE / uin
    if path.is_file() and time.time() - path.stat().st_mtime < _TTL:
        data = path.read_bytes()
    else:
        data = _fetch(uin)
        if data is None:
            data = path.read_bytes() if path.is_file() else None
        else:
            _CACHE.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=_CACHE, delete=False) as tmp:
                tmp.write(data)
                temp_path = tmp.name
            try:
                os.replace(temp_path, path)
            finally:
                Path(temp_path).unlink(missing_ok=True)
    if data is None:
        return None
    return data, _image_type(data)
