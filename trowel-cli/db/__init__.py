"""只读访问已解密的 SQLite 数据库。

connection 判断文件是否为 SQLite 数据库并以只读方式打开；
schema 列出表与列；rows 读取表的行。
各模块只返回数据结构，不输出也不退出进程。
"""
