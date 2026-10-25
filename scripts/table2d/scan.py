"""扫描库中全部 blob 的 protobuf 字段，结果按库文件指纹缓存在 .cache/ 下。

记录的是数据的原始层级，不受渲染侧展开深度的限制。每个字段路径记录出现次数与层级，
层级即路径的段数，单独记一份是为了让读取方不必再解析路径。
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from lib.wire import as_text, parse_fields

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CHUNK = 1 << 20
TABLES = "SELECT name FROM pragma_table_list WHERE schema = 'main' AND type IN ('table', 'virtual') AND substr(name, 1, 7) <> 'sqlite_' ORDER BY name"


def file_digest(path):
    """库文件指纹，取内容而非元信息，副本改路径后仍能命中同一份缓存"""
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(fields, path, depth, out):
    for num, wire, value in fields:
        name = f"{path}.{num}" if path else str(num)
        entry = out.setdefault(name, {"depth": depth, "count": 0})
        entry["count"] += 1
        if wire == "bytes" and value and as_text(value) is None:
            nested = parse_fields(value)
            if nested:
                walk(nested, name, depth + 1, out)


def scan_table(conn, table):
    """一张表 -> 列 -> {blobs, fields}；只统计字段的出现，不保留取值"""
    columns = {}
    cursor = conn.execute(f"SELECT * FROM [{table}]")
    headers = [d[0] for d in cursor.description]
    for record in cursor:
        for index, header in enumerate(headers):
            value = record[index]
            if not isinstance(value, bytes) or not value:
                continue
            column = columns.setdefault(header, {"blobs": 0, "fields": {}})
            column["blobs"] += 1
            fields = parse_fields(value)
            if fields:
                walk(fields, "", 1, column["fields"])
    return columns


def census_of(db_path, report=None):
    """取该库的扫描结果，缓存缺失时扫描并写回。

    report 是进度回调，按 (缓存路径, 表名, 序号, 总数) 调用，表名为 None 表示即将开始扫描
    """
    digest = file_digest(db_path)
    cache = CACHE_DIR / f"{digest}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["tables"]

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # TEXT 不保证是合法 UTF-8；census 只解析 bytes，容错解码避免取行阶段抛错
    conn.text_factory = lambda raw: raw.decode("utf-8", errors="surrogateescape")
    names = [row[0] for row in conn.execute(TABLES)]
    if report is not None:
        report(cache, None, 0, len(names))
    tables = {}
    for index, table in enumerate(names, 1):
        if report is not None:
            report(cache, table, index, len(names))
        tables[table] = scan_table(conn, table)
    CACHE_DIR.mkdir(exist_ok=True)
    document = {"db": db_path, "md5": digest, "tables": tables}
    cache.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return tables
