from enum import Enum, auto


class Status(Enum):
    """条目的采用状态

    UNDEFINED 只用于说明「未登记」，不能写在映射里
    EXPLORING 始终可见，仅作着色标记
    """

    UNDEFINED = auto()
    HIDDEN = auto()
    DISCARDED = auto()
    EXPLORING = auto()


class ProtoField:
    def __init__(self, name=None, status=None, enum=None):
        self.name = name
        self.status = status
        self.enum = enum or {}


class Column:
    def __init__(self, name=None, proto=None, status=None, enum=None):
        self.name = name
        self.proto = proto
        self.status = status
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

    def label(self, path):
        """列路径的语义名称，无映射返回 None"""
        entry = self.entry(path)
        return entry.name if entry else None

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

    def status(self, path):
        """列路径登记的状态，未登记返回 None"""
        entry = self.entry(path)
        return entry.status if entry else None

    def blocked(self, path, show_undefined, show_hidden, show_discarded):
        """该列路径不渲染的原因，能渲染返回 None"""
        entry = self.entry(path)
        if entry is None:
            return None if show_undefined else Status.UNDEFINED
        if entry.status is Status.EXPLORING:
            return None
        if entry.status is Status.HIDDEN and not show_hidden:
            return Status.HIDDEN
        if entry.status is Status.DISCARDED and not show_discarded:
            return Status.DISCARDED
        return None
