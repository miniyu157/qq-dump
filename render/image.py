"""终端图像渲染：Kitty 图形协议、半块字符像素画与真彩色 ASCII 字符画。"""

import base64
import fcntl
import io
import os
import shutil
import struct
import sys
import termios

from PIL import Image

__all__ = ["render"]


def render(source: str | bytes, *, use_ascii: bool = False, width_ratio: float = 0.45, file=None) -> None:
    """把图像打印到终端。

    use_ascii 为真时输出真彩色 ASCII 字符画；否则终端支持 Kitty 图形协议时整幅输出，
    不支持时输出半块字符像素画，每格承载上下两个像素。width_ratio 为渲染宽度占终端列数的
    比例，file 缺省为 stdout。
    """
    if file is None:
        file = sys.stdout

    width = max(1, int(shutil.get_terminal_size().columns * width_ratio))
    if use_ascii:
        lines = _ascii_lines(source, width)
    elif _kitty_capable():
        lines = [_kitty_escape(source, width)]
    else:
        lines = _half_block_lines(source, width)

    for line in lines:
        print(line, file=file)


def _kitty_capable() -> bool:
    """终端是否支持 Kitty 图形协议；按已知环境标记判断，无法判断时视为不支持。"""
    term = os.environ.get("TERM", "")
    program = os.environ.get("TERM_PROGRAM", "")
    return bool(os.environ.get("KITTY_WINDOW_ID")) or "kitty" in term or "ghostty" in term or program in ("ghostty", "kitty", "WezTerm")


def _kitty_escape(source: str | bytes, width: int) -> str:
    """按 Kitty 图形协议编码整幅图像：PNG 转 base64 后每 4096 字节分块传输，由终端缩放到 width 个单元格宽。"""
    image = _open_image(source)
    limit = width * 8  # Kitty 每个单元格按 8 像素宽计算
    if image.width > limit:
        image = image.resize((limit, round(image.height / image.width * limit)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    chunks = [payload[index:index + 4096] for index in range(0, len(payload), 4096)]
    sequences = []
    for index, chunk in enumerate(chunks):
        more = 0 if index == len(chunks) - 1 else 1
        header = f"a=T,f=100,t=d,q=2,c={width},m={more}" if index == 0 else f"m={more}"
        sequences.append(f"\033_G{header};{chunk}\033\\")
    return "".join(sequences)


def _half_block_lines(source: str | bytes, width: int) -> list[str]:
    """半块字符像素画：每个单元格用上下两个像素的 24 位真彩色拼成 ▀。"""
    image = _open_image(source)
    cell = _cell_ratio()
    height = round(image.height / image.width * width * 2 / cell)
    height = max(2, height - height % 2)
    image = image.resize((width, height))
    pixels = image.load()
    lines = []
    for y in range(0, image.height, 2):
        cells = []
        for x in range(width):
            top, bottom = pixels[x, y], pixels[x, y + 1]
            cells.append(f"\033[38;2;{top[0]};{top[1]};{top[2]}m\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀")
        lines.append("".join(cells) + "\033[0m")
    return lines


def _ascii_lines(source: str | bytes, width: int) -> list[str]:
    """真彩色 ASCII 字符画：亮度决定字符，原图像素颜色作为前景色。"""
    image = _open_image(source)
    cell = _cell_ratio()
    height = max(1, round(image.height / image.width * width / cell))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    gray = image.convert("L")
    pixels = image.load()
    luminance = gray.load()
    ramp = " .:-=+*#%@"
    last = len(ramp) - 1
    lines = []
    for y in range(height):
        cells = []
        for x in range(width):
            char = ramp[round(luminance[x, y] / 255 * last)]
            if char == " ":
                cells.append(char)
                continue
            red, green, blue = pixels[x, y]
            cells.append(f"\033[38;2;{red};{green};{blue}m{char}")
        lines.append("".join(cells) + "\033[0m")
    return lines


def _cell_ratio() -> float:
    """终端单元格的高宽比；缺省依次尝试 stdout、stderr 与 /dev/tty，取不到像素尺寸时按 2 处理。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            ratio = _ratio_from(stream.fileno())
        except (AttributeError, OSError, ValueError):
            ratio = None
        if ratio:
            return ratio
    try:
        with open("/dev/tty", "rb") as tty:
            ratio = _ratio_from(tty.fileno())
    except OSError:
        ratio = None
    return ratio or 2.0


def _ratio_from(fd: int) -> float | None:
    try:
        rows, cols, xpixel, ypixel = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    except OSError:
        return None
    if not (rows and cols and xpixel and ypixel):
        return None
    ratio = (ypixel / rows) / (xpixel / cols)
    return ratio if ratio > 0 else None


def _open_image(source: str | bytes) -> Image.Image:
    """路径或字节串统一转为 RGB 图像。"""
    if isinstance(source, bytes):
        return Image.open(io.BytesIO(source)).convert("RGB")
    return Image.open(source).convert("RGB")
