"""lib.wire: protobuf 线格式的字段切分与文本判定。

判定基准: protobuf 编码文档中的字节示例，以及按线格式规范手写的字节串。
"""

import unittest

from support.wire import field, fixed32, fixed64

from lib.wire import Field, as_text, parse_fields

__all__ = []


class ParseFieldsTests(unittest.TestCase):
    """完整的消息被切成字段序列，保留字段号、线型与原始值。"""

    def test_varint_field(self) -> None:
        self.assertEqual(parse_fields(bytes.fromhex("089601")), [Field(1, "varint", 150)])

    def test_length_delimited_field(self) -> None:
        self.assertEqual(parse_fields(bytes.fromhex("120774657374696e67")), [Field(2, "bytes", b"testing")])

    def test_fixed_width_fields_keep_raw_bytes(self) -> None:
        eight, four = bytes(range(8)), bytes(range(4))
        self.assertEqual(parse_fields(b"\x09" + eight + b"\x0d" + four), [Field(1, "fixed64", eight), Field(1, "fixed32", four)])

    def test_fields_keep_order_and_repeats(self) -> None:
        message = field(3, 1) + field(1, b"a") + field(3, 2) + field(3, 1)
        self.assertEqual(parse_fields(message), [Field(3, "varint", 1), Field(1, "bytes", b"a"), Field(3, "varint", 2), Field(3, "varint", 1)])

    def test_largest_values(self) -> None:
        # 字段号上限 2^29 - 1，varint 上限 2^64 - 1
        message = bytes.fromhex("f8ffffff0f") + b"\xff" * 9 + b"\x01"
        self.assertEqual(parse_fields(message), [Field(2**29 - 1, "varint", 2**64 - 1)])

    def test_empty_bytes_field_and_empty_message(self) -> None:
        self.assertEqual(parse_fields(b"\x0a\x00"), [Field(1, "bytes", b"")])
        self.assertEqual(parse_fields(b""), [])

    def test_nested_message_is_left_as_bytes(self) -> None:
        inner = field(25007, 1) + field(25008, "同学".encode())
        outer = parse_fields(field(25011, inner))
        self.assertEqual(outer, [Field(25011, "bytes", inner)])
        self.assertEqual(parse_fields(outer[0].value), [Field(25007, "varint", 1), Field(25008, "bytes", "同学".encode())])


class MalformedInputTests(unittest.TestCase):
    """不是完整消息的字节串整体判为无法解析 (None)，不返回前面已切出的部分。"""

    def test_truncated_input(self) -> None:
        truncated = {
            "键未结束": b"\x80",
            "缺少 varint 值": b"\x08",
            "varint 值未结束": b"\x08\x96",
            "缺少长度": b"\x12",
            "内容短于长度": b"\x12\x07test",
            "fixed64 不足 8 字节": b"\x09" + bytes(7),
            "fixed32 不足 4 字节": b"\x0d" + bytes(3),
        }
        for reason, data in truncated.items():
            with self.subTest(reason=reason):
                self.assertIsNone(parse_fields(data))

    def test_valid_prefix_does_not_rescue_a_broken_tail(self) -> None:
        self.assertIsNone(parse_fields(field(1, 150) + b"\x12\x07test"))

    def test_field_number_zero(self) -> None:
        self.assertIsNone(parse_fields(b"\x00\x00"))

    def test_unsupported_wire_types(self) -> None:
        # 3 与 4 是已废弃的 group，6 与 7 未定义
        for wire_type in (3, 4, 6, 7):
            with self.subTest(wire_type=wire_type):
                self.assertIsNone(parse_fields(bytes([1 << 3 | wire_type]) + bytes(8)))

    def test_varint_longer_than_ten_bytes(self) -> None:
        self.assertIsNone(parse_fields(b"\x08" + b"\x80" * 10 + b"\x01"))


class AsTextTests(unittest.TestCase):
    def test_printable_utf8_is_text(self) -> None:
        self.assertEqual(as_text("昵称 nick 😀".encode()), "昵称 nick 😀")

    def test_newline_and_tab_are_allowed(self) -> None:
        self.assertEqual(as_text(b"line 1\r\n\tline 2"), "line 1\r\n\tline 2")

    def test_binary_content_is_not_text(self) -> None:
        not_text = {"空串": b"", "非法 UTF-8": b"\xff\xfe", "截断的多字节字符": "中".encode()[:2], "含控制字符": b"a\x00b", "嵌套消息": field(1, 150) + fixed32(2, bytes(4)) + fixed64(3, bytes(8))}
        for reason, data in not_text.items():
            with self.subTest(reason=reason):
                self.assertIsNone(as_text(data))


if __name__ == "__main__":
    unittest.main()
