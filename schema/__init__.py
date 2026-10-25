"""本项目使用的 QQ 数据库表结构。

scripts/table2d/maps 是研究工具的完整调查记录；这里只登记主程序实际读取的列与
protobuf 字段，标识符统一使用英文语义名，枚举值保留界面文案。
"""


class ProtoField:
    def __init__(self, name, enum=None):
        self.name = name
        self.enum = enum or {}


class Column:
    def __init__(self, name, proto=None, enum=None):
        self.name = name
        self.proto = proto
        self.enum = enum or {}


class Table:
    def __init__(self, name, columns):
        self.name = name
        self.columns = columns

    def entry(self, path):
        """列路径对应的条目：列本身或它下属的字段，未登记返回 None"""
        head, *rest = path.split(".")
        column = self.columns.get(head)
        if column is None or not rest:
            return column
        return (column.proto or {}).get(int(rest[-1]))

    def column_id(self, name):
        """语义名称对应的列号，未登记返回 None"""
        for number, column in self.columns.items():
            if column.name == name:
                return number
        return None

    def field_id(self, column, name):
        """列下 protobuf 字段名称对应的字段号，未登记返回 None"""
        entry = self.columns.get(column)
        if entry is None or not entry.proto:
            return None
        for number, field in entry.proto.items():
            if field.name == name:
                return number
        return None

    def enum(self, path, value):
        """列路径的枚举名称，未登记返回 None"""
        entry = self.entry(path)
        if not entry or not entry.enum or isinstance(value, bool) or not isinstance(value, (int, str)):
            return None
        return entry.enum.get(value)
