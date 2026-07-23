"""QQNT 数据库 schema —— 数据库/表/列 层级结构。

类型分为两层：
- Protobuf 层：直接对应标准 protobuf 的 message / field / enum 定义
- 数据库层：QQNT SQLite 数据库的表/列描述，可引用 protobuf 层类型
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Protobuf 层


@dataclass
class EnumValue:
    """枚举值。对应 protobuf EnumValueDescriptorProto。"""

    number: int
    label: str
    description: str = ""


@dataclass
class EnumType:
    """枚举类型。对应 protobuf EnumDescriptorProto。"""

    name: str
    values: list[EnumValue]


@dataclass
class ProtoField:
    """Protobuf 字段。对应 protobuf FieldDescriptorProto。

    field_type 对应标准 protobuf Type 枚举的子集（省略 QQNT 中未出现的类型）：
      varint  — TYPE_INT32/INT64/UINT32/64/SINT32/64/BOOL
      string  — TYPE_STRING
      bytes   — TYPE_BYTES
      nested  — TYPE_MESSAGE（struct 指向子 message）
      enum    — TYPE_ENUM（enum 指向枚举定义）
    """

    # fmt: off
    number: int                                      # field number（protobuf 规范中是 int32）
    name: str                                        # 字段说明
    field_type: Literal["varint", "string", "bytes", "nested", "enum"] = "varint"
    repeated: bool = False                           # 对应 proto3 repeated 修饰
    struct: ProtoStruct | None = None                # field_type="nested" 时
    enum: EnumType | None = None                     # field_type="enum" 时
    # fmt: on


@dataclass
class ProtoStruct:
    """Protobuf message 定义。对应 protobuf DescriptorProto。"""

    name: str
    fields: list[ProtoField]

    def field(self, name: str) -> ProtoField:
        """按 name 获取字段。未找到则 raise KeyError。"""
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"field {name!r} not found in {self.name}")


# 数据库层


@dataclass
class FlagBit:
    """标志位定义，用于 SQL INTEGER 列的位掩码语义。"""

    position: int  # bit 位（0-based）
    label: str
    description: str = ""


@dataclass
class FlagsType:
    """位掩码/标志位类型，用于 SQL INTEGER 列。"""

    name: str
    bits: list[FlagBit]
    width: int = 32  # 位宽


@dataclass
class Column:
    """数据库表列（SQL column）。"""

    # fmt: off
    id: str                                 # 列号（QQNT 数据库以数字字符串为列名）
    name: str                               # 列说明
    field_type: str = ""                    # SQL 类型：INTEGER | TEXT | BLOB 等（空=未分析）
    proto: ProtoStruct | None = None        # BLOB 列内部的 protobuf 结构
    enum: EnumType | None = None            # INTEGER 列对应的枚举
    flags: FlagsType | None = None          # INTEGER 列的位掩码定义
    # fmt: on


@dataclass
class Table:
    """数据表。"""

    name: str
    columns: list[Column]

    def column(self, name: str) -> Column:
        """按 name 获取列。未找到则 raise KeyError。"""
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"column {name!r} not found in {self.name}")


@dataclass
class Database:
    """数据库文件。"""

    filename: str
    tables: list[Table]

    def table(self, name: str) -> Table:
        """按 name 获取表。未找到则 raise KeyError。"""
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(f"table {name!r} not found in {self.filename}")
