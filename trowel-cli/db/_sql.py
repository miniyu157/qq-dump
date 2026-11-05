"""db 包内共用的 SQL 拼接辅助。"""

__all__ = ["quote_identifier"]


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
