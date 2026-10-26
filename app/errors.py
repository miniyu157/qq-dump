"""应用层共用的异常。"""

__all__ = ["AppError"]


class AppError(Exception):
    """可预期的用户侧错误，由入口统一输出。"""
