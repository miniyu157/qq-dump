"""数据访问层对外的异常。"""

__all__ = ["DatabaseError"]


class DatabaseError(Exception):
    """库文件无法打开或读取，或文件名未登记映射；消息可直接展示给用户。"""
