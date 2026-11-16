"""应用层共用的异常。"""

__all__ = ["AppError", "ScriptFailed"]


class AppError(Exception):
    """可预期的用户侧错误，由入口统一输出。"""


class ScriptFailed(AppError):
    """cli/ 脚本以非 0 退出。原因已由脚本、Python 或 sudo 输出到 stderr，调用方不再输出本异常的消息。"""
