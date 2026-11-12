"""schema.Table: 列号、protobuf 字段号与枚举名称的查询。

判定基准: 测试内手写的一张小表。登记表 (schema/*.py) 的内容是调查得到的事实，不在这里复述。
"""

import unittest

from schema import Column, ProtoField, Table

__all__ = []

_TABLE = Table("sample", columns={
    "1000": Column("uid"),
    "2000": Column("gender", enum={1: "男", 2: "女"}),
    "3000": Column("relation", proto={
        3001: ProtoField("preset_ids", enum={1: "情侣"}),
        3002: ProtoField("note"),
    }),
})


class LookupTests(unittest.TestCase):
    def test_column_number_by_name(self) -> None:
        self.assertEqual(_TABLE.column_id("gender"), "2000")
        self.assertIsNone(_TABLE.column_id("absent"))

    def test_field_number_by_name(self) -> None:
        self.assertEqual(_TABLE.field_id("3000", "note"), 3002)
        unregistered = {"字段未登记": ("3000", "absent"), "列没有 protobuf 字段": ("1000", "note"), "列未登记": ("9999", "note")}
        for reason, (column, name) in unregistered.items():
            with self.subTest(reason=reason):
                self.assertIsNone(_TABLE.field_id(column, name))

    def test_entry_by_path(self) -> None:
        self.assertEqual(_TABLE.entry("2000").name, "gender")
        self.assertEqual(_TABLE.entry("3000.3001").name, "preset_ids")
        self.assertIsNone(_TABLE.entry("9999"))
        self.assertIsNone(_TABLE.entry("3000.9999"))


class EnumTests(unittest.TestCase):
    def test_column_and_field_values_map_to_names(self) -> None:
        self.assertEqual(_TABLE.enum("2000", 2), "女")
        self.assertEqual(_TABLE.enum("3000.3001", 1), "情侣")

    def test_unregistered_values_have_no_name(self) -> None:
        unregistered = {"取值未登记": ("2000", 7), "列没有枚举": ("1000", 1), "字段没有枚举": ("3000.3002", 1), "列未登记": ("9999", 1), "空值": ("2000", None)}
        for reason, (path, value) in unregistered.items():
            with self.subTest(reason=reason):
                self.assertIsNone(_TABLE.enum(path, value))

    def test_booleans_are_not_treated_as_one_and_zero(self) -> None:
        self.assertIsNone(_TABLE.enum("2000", True))


if __name__ == "__main__":
    unittest.main()
