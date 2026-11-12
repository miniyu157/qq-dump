"""protobuf 线格式的编码器，按线格式规范独立实现，用来构造被测解析器的输入。"""

__all__ = ["field", "fixed32", "fixed64", "varint"]


def varint(value: int) -> bytes:
    """无符号整数的 base-128 变长编码，低位组在前。"""
    output = bytearray()
    while True:
        low, value = value & 0x7F, value >> 7
        output.append(low | 0x80 if value else low)
        if not value:
            return bytes(output)


def field(number: int, value: int | bytes) -> bytes:
    """整数编码为 varint 字段 (线型 0)，字节串编码为长度前缀字段 (线型 2)。"""
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def fixed64(number: int, value: bytes) -> bytes:
    """8 字节定长字段 (线型 1)。"""
    return varint(number << 3 | 1) + value


def fixed32(number: int, value: bytes) -> bytes:
    """4 字节定长字段 (线型 5)。"""
    return varint(number << 3 | 5) + value
