"""数据库发现结果类型 —— 原始数据库元数据，不含业务语义。"""

from .main import DBColumn, DBFile, DBTable

__all__ = ["DBColumn", "DBFile", "DBTable"]
