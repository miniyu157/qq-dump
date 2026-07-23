"""codegen 核心实现 —— 使用 ast 读取、生成、修改 schema 包源代码。

操作 schema 目录下:
- 数据库子包（如 profile_info/）
- schema/__init__.py 的导入和导出

公开 API 见 __init__.py。
"""

from __future__ import annotations

import ast
import shutil
from dataclasses import fields, is_dataclass
from pathlib import Path

from dbtools.discover import get_columns_by_files
from dbtools.schema.base import Column, Table

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


# 命名推导（机械规则，来自 CLAUDE.md）


def _filename_to_dirname(filename: str) -> str:
    """'profile_info.db' → 'profile_info'"""
    return filename.removesuffix(".db")


def _validate_db_filename(filename: str) -> None:
    """校验数据库文件名的合法性。

    Database.filename 必须以 .db 结尾，且去掉后缀后的部分必须是合法的
    Python 标识符（否则生成的目录名和变量名会导致语法错误）。

    Raises:
        ValueError: 文件名不合法。
    """
    if not filename.endswith(".db"):
        raise ValueError(f"{filename!r}: 必须以 .db 结尾")
    dirname = filename.removesuffix(".db")
    if not dirname.isidentifier():
        raise ValueError(f"{filename!r}: 去掉 .db 后缀后 '{dirname}' 不是合法的 Python 标识符")


def _filename_to_varname(filename: str) -> str:
    """'profile_info.db' → 'PROFILE_INFO_DB'"""
    return filename.replace(".", "_").upper()


def _table_to_varname(table_name: str) -> str:
    """'buddy_list' → 'BUDDY_LIST'"""
    return table_name.upper()


# AST 节点构建工具


def _import_from_future() -> ast.ImportFrom:
    return ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )


def _import_from(module: str, names: list[str], level: int = 0) -> ast.ImportFrom:
    return ast.ImportFrom(
        module=module,
        names=[ast.alias(name=n) for n in names],
        level=level,
    )


def _assign_stmt(name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store())],
        value=value,
    )


def _make_name(id: str) -> ast.Name:
    return ast.Name(id=id, ctx=ast.Load())


# 对象 → AST 表达式（将 dataclass 实例序列化为 Python 源码 AST）


def _obj_to_ast(obj):
    """将任意 Python 值转为 AST 表达式节点。

    支持: None, bool, int, str, list, dataclass 实例。
    """
    if obj is None:
        return ast.Constant(value=None)
    if isinstance(obj, bool):
        return ast.Constant(value=obj)
    if isinstance(obj, int):
        return ast.Constant(value=obj)
    if isinstance(obj, str):
        return ast.Constant(value=obj)
    if isinstance(obj, list):
        return ast.List(
            elts=[_obj_to_ast(x) for x in obj],
            ctx=ast.Load(),
        )
    if is_dataclass(obj) and not isinstance(obj, type):
        return _dataclass_to_call(obj)
    raise TypeError(f"无法将 {type(obj).__name__} 转为 AST: {obj!r}")


def _dataclass_to_call(obj) -> ast.Call:
    """将 dataclass 实例转为 ast.Call 节点。

    跳过值为 None 的字段，以及值与默认值相等的字段，
    保持输出简洁，与现有手写代码风格一致。
    """
    import dataclasses as _dc

    cls_name = type(obj).__name__
    keywords: list[ast.keyword] = []
    for f in fields(obj):
        value = getattr(obj, f.name)
        if value is None:
            continue
        if f.default is not _dc.MISSING and value == f.default:
            continue
        keywords.append(ast.keyword(arg=f.name, value=_obj_to_ast(value)))
    return ast.Call(
        func=ast.Name(id=cls_name, ctx=ast.Load()),
        args=[],
        keywords=keywords,
    )


# 代码生成


def _module_to_source(module: ast.Module) -> str:
    module = ast.fix_missing_locations(module)
    return ast.unparse(module)


def _generate_table_source(table: Table) -> str:
    """为一个 Table 生成完整的 .py 文件源代码。"""
    varname = _table_to_varname(table.name)
    base_imports = ["Table"]
    if table.columns:
        base_imports.append("Column")
    module = ast.Module(
        body=[
            _import_from_future(),
            _import_from("..base", base_imports),
            _assign_stmt(varname, _obj_to_ast(table)),
        ],
        type_ignores=[],
    )
    return _module_to_source(module)


def _generate_db_init_source(
    filename: str,
    db_varname: str,
    table_specs: list[tuple[str, str]],  # [(modulename, varname), ...]
) -> str:
    """为数据库子包生成 __init__.py 源代码。

    Args:
        filename: 数据库文件名，如 "profile_info.db"
        db_varname: Database 变量名，如 "PROFILE_INFO_DB"
        table_specs: [(模块名, 表变量名), ...]
    """
    body: list[ast.stmt] = [
        ast.Expr(value=ast.Constant(value=f"{filename} 数据库。")),
        _import_from_future(),
        _import_from("..base", ["Database"]),
    ]

    # 表导入
    for modulename, varname in table_specs:
        body.append(_import_from(modulename, [varname], level=1))

    # Database 变量
    table_names = [ast.Name(id=v, ctx=ast.Load()) for _, v in table_specs]
    db_call = ast.Call(
        func=ast.Name(id="Database", ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg="filename", value=ast.Constant(value=filename)),
            ast.keyword(arg="tables", value=ast.List(elts=table_names, ctx=ast.Load())),
        ],
    )
    body.append(ast.Assign(targets=[ast.Name(id=db_varname, ctx=ast.Store())], value=db_call))

    module = ast.Module(body=body, type_ignores=[])
    return _module_to_source(module)


# AST 解析与查询（读取现有代码结构）


def _parse_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_db_call(module: ast.Module) -> ast.Call | None:
    """在模块中查找 Database(...) 调用（赋值右侧）。"""
    for node in ast.walk(module):
        if isinstance(node, ast.Assign):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "Database"
            ):
                return node.value
    return None


def _extract_table_list(db_call: ast.Call) -> ast.List | None:
    """从 Database(...) 调用中提取 tables=[...] 列表节点。"""
    for kw in db_call.keywords:
        if kw.arg == "tables" and isinstance(kw.value, ast.List):
            return kw.value
    return None


def _extract_table_var_names_from_list(table_list: ast.List) -> list[str]:
    """从 tables=[...] 列表中提取所有表变量名。"""
    result: list[str] = []
    for elt in table_list.elts:
        if isinstance(elt, ast.Name):
            result.append(elt.id)
    return result


def _extract_table_map_from_module(module: ast.Module) -> dict[str, str]:
    """从模块中提取所有 ``Table(...)`` 赋值，返回 ``{table_name: varname}``。

    正确处理多表模块（如 config.py 定义多张表）。
    仅匹配赋值目标为简单 Name 的节点。
    """
    result: dict[str, str] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Name) and call.func.id == "Table"):
            continue
        if not node.targets or not isinstance(node.targets[0], ast.Name):
            continue
        varname = node.targets[0].id
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                result[kw.value.value] = varname
                break
    return result


def _find_table_call(module: ast.Module, table_name: str) -> ast.Call:
    """在模块中查找 ``Table(name=table_name, ...)`` 调用节点。

    按 ``name`` 关键字值匹配，而非按赋值目标名。支持多表模块
    （如 config.py 定义多张表）。

    Raises:
        ValueError: 未找到匹配的 Table 调用。
    """
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Name) and call.func.id == "Table"):
            continue
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == table_name:
                return call
    raise ValueError(f"Table {table_name!r} not found in module")


def _extract_columns_list(table_call: ast.Call) -> ast.List:
    """从 ``Table(...)`` 调用中提取 ``columns=[...]`` 列表节点。

    Raises:
        ValueError: 缺少 ``columns`` 关键字或其值不是 ast.List。
    """
    for kw in table_call.keywords:
        if kw.arg == "columns" and isinstance(kw.value, ast.List):
            return kw.value
    raise ValueError("Table call has no columns=[...] list")


def _collect_column_ids(columns_list: ast.List) -> set[str]:
    """收集 ``columns=[...]`` 中已存在的 ``Column.id`` 值。

    Raises:
        ValueError: 列表中包含非 ``Column(...)`` 调用的元素。
    """
    ids: set[str] = set()
    for i, elt in enumerate(columns_list.elts):
        if not isinstance(elt, ast.Call):
            raise ValueError(f"columns[{i}]: 期望 Column(...) 调用，实际为 {type(elt).__name__}")
        if not (isinstance(elt.func, ast.Name) and elt.func.id == "Column"):
            raise ValueError(f"columns[{i}]: 期望 Column(...) 调用，实际为 {ast.unparse(elt.func)}")
        for kw in elt.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                ids.add(kw.value.value)
                break
    return ids


def _iter_init_imports(db_dir: Path):
    """迭代 ``__init__.py`` 中所有 ``from .xxx import YYY`` 导入的模块。

    按模块名去重，每个 ``.py`` 文件至多解析一次。
    Yields ``(module_path, module_ast, imported_varnames)``。
    """
    init_py = db_dir / "__init__.py"
    module = _parse_file(init_py)

    module_varnames: dict[str, list[str]] = {}
    for node in module.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.module is None:
            continue
        for alias in node.names:
            module_varnames.setdefault(node.module, []).append(alias.name)

    for modulename, varnames in module_varnames.items():
        mod_path = db_dir / f"{modulename}.py"
        if mod_path.exists():
            yield mod_path, _parse_file(mod_path), varnames


def _get_existing_table_map(db_dir: Path) -> dict[str, str]:
    """解析 DB 子包，获取 ``{表名: 变量名}`` 映射。

    按 ``__init__.py`` 的 import 关系解析每个模块，匹配导入的变量名
    与模块中的 Table 定义。正确处理多表模块。
    """
    result: dict[str, str] = {}
    for mod_path, table_mod, imported_varnames in _iter_init_imports(db_dir):
        table_map = _extract_table_map_from_module(table_mod)
        for varname in imported_varnames:
            for table_name, mapped_varname in table_map.items():
                if mapped_varname == varname:
                    result[table_name] = varname
                    break
    return result


def _find_db_varname(db_dir: Path) -> str | None:
    """在 DB __init__.py 中查找 Database 变量的名称。"""
    init_py = db_dir / "__init__.py"
    module = _parse_file(init_py)
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_DB"):
                call = node.value
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "Database":
                    return target.id
    return None


def _scan_existing_dbs(schema_dir: Path) -> dict[str, Path]:
    """扫描 schema/ 目录，获取 {filename: dir_path} 映射。

    解析每个子包的 __init__.py，找到 Database(filename=...) 中的 filename 值。
    """
    result: dict[str, Path] = {}
    for item in sorted(schema_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("template"):
            continue
        init_py = item / "__init__.py"
        if not init_py.exists():
            continue
        module = _parse_file(init_py)
        db_call = _find_db_call(module)
        if db_call is None:
            continue
        for kw in db_call.keywords:
            if kw.arg == "filename" and isinstance(kw.value, ast.Constant):
                result[kw.value.value] = item
                break
    return result


# AST 修改工具（在现有 AST 中插入/追加节点）


def _ensure_base_import(module: ast.Module, name: str) -> None:
    """确保模块中存在 ``from ..base import <name>``。

    若已有 ``from ..base import ...`` 节点，追加 **name** 到其 names 列表。
    否则在 import 区域插入新节点。

    兼容两种 AST 表示：codegen 生成的 ``module="..base", level=0`` 和
    ast.parse 解析的 ``module="base", level=2``。
    """
    for node in module.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if (node.module == "..base") or (node.module == "base" and node.level == 2):
            existing = {alias.name for alias in node.names}
            if name not in existing:
                node.names.append(ast.alias(name=name))
            return
    _insert_import(module, _import_from("..base", [name]))


def _insert_import(module: ast.Module, new_import: ast.ImportFrom) -> None:
    """在模块 body 的 import 区域末尾插入一条 import 语句。

    import 区域定义为: __future__、docstring、以及所有 ImportFrom 之后。
    """
    insert_idx = 0
    for i, node in enumerate(module.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_idx = i + 1
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            # docstring — 保持在它之后
            insert_idx = max(insert_idx, i + 1)
    module.body.insert(insert_idx, new_import)


def _add_to_all_db_list(module: ast.Module, name: str) -> None:
    """向模块的 __all_db__ 列表追加一个数据库名称（如果尚不存在）。"""
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all_db__":
                if isinstance(node.value, ast.List):
                    existing = {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
                    if name not in existing:
                        node.value.elts.append(ast.Constant(value=name))
                return


def _add_to_table_list(table_list: ast.List, var_name: str) -> bool:
    """向 tables=[...] 列表追加一个表变量名。已存在则返回 False。"""
    for elt in table_list.elts:
        if isinstance(elt, ast.Name) and elt.id == var_name:
            return False
    table_list.elts.append(_make_name(var_name))
    return True


def _remove_from_all_db_list(module: ast.Module, name: str) -> None:
    """从 ``__all_db__`` 列表中移除指定数据库名称。"""
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all_db__":
                if isinstance(node.value, ast.List):
                    node.value.elts = [
                        elt for elt in node.value.elts if not (isinstance(elt, ast.Constant) and elt.value == name)
                    ]
                return


def _remove_from_table_list(table_list: ast.List, var_name: str) -> None:
    """从 ``tables=[...]`` 列表中移除一个表变量名。"""
    table_list.elts = [elt for elt in table_list.elts if not (isinstance(elt, ast.Name) and elt.id == var_name)]


def _remove_import(module: ast.Module, modulename: str, varnames: set[str]) -> None:
    """从模块中移除指定变量名的 import。

    若 import 语句还有其他变量名（多表模块），仅移除指定的 alias。
    若移除后 import 无剩余变量名（单表模块），删除整条 import 语句。
    """
    for i, node in enumerate(module.body):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != modulename or node.level != 1:
            continue
        node.names = [alias for alias in node.names if alias.name not in varnames]
        if not node.names:
            del module.body[i]
        return


def _remove_table_assignment(module: ast.Module, table_name: str) -> None:
    """从表模块中删除指定 ``Table(name=table_name, ...)`` 的赋值语句。

    用于多表模块场景——只删除目标 Table 的赋值，保留其他 Table。
    """
    for i, node in enumerate(module.body):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Name) and call.func.id == "Table"):
            continue
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == table_name:
                del module.body[i]
                return
    raise ValueError(f"Table {table_name!r} not found in module")


# 文件写入


def _write_py(path: Path, source: str) -> None:
    path.write_text(source + "\n", encoding="utf-8")


# 核心操作


def _create_new_db(
    schema_dir: Path,
    filename: str,
    tables: list[Table],
) -> None:
    """创建全新的数据库 schema 子包。"""
    dirname = _filename_to_dirname(filename)
    db_varname = _filename_to_varname(filename)
    db_dir = schema_dir / dirname
    db_dir.mkdir(parents=True, exist_ok=True)

    table_specs: list[tuple[str, str]] = []
    for table in tables:
        modulename = table.name
        varname = _table_to_varname(table.name)
        table_source = _generate_table_source(table)
        _write_py(db_dir / f"{modulename}.py", table_source)
        table_specs.append((modulename, varname))

    # 生成 DB __init__.py
    init_source = _generate_db_init_source(filename, db_varname, table_specs)
    _write_py(db_dir / "__init__.py", init_source)

    # 更新 schema/__init__.py
    _add_db_to_schema_init(schema_dir, dirname, db_varname)


def _merge_existing_db(
    db_dir: Path,
    filename: str,
    new_tables: list[Table],
) -> None:
    """向已有数据库增量添加新表。不移除任何现有表。"""
    db_varname = _find_db_varname(db_dir)
    if db_varname is None:
        raise ValueError(f"在 {db_dir} 中未找到 Database 变量")

    existing = _get_existing_table_map(db_dir)
    init_py = db_dir / "__init__.py"
    module = _parse_file(init_py)
    db_call = _find_db_call(module)
    if db_call is None:
        raise ValueError(f"在 {init_py} 中未找到 Database(...) 调用")
    table_list = _extract_table_list(db_call)
    if table_list is None:
        raise ValueError(f"在 {init_py} 中未找到 tables=[...] 列表")

    added = 0
    for table in new_tables:
        if table.name in existing:
            continue

        modulename = table.name
        varname = _table_to_varname(table.name)

        # 写入表文件
        table_source = _generate_table_source(table)
        _write_py(db_dir / f"{modulename}.py", table_source)

        # 向 __init__.py 添加 import
        new_import = _import_from(modulename, [varname], level=1)
        _insert_import(module, new_import)

        # 向 tables 列表添加变量名
        _add_to_table_list(table_list, varname)

        existing[table.name] = varname
        added += 1

    if added > 0:
        _write_py(init_py, _module_to_source(module))


def _add_db_to_schema_init(schema_dir: Path, dirname: str, db_varname: str) -> None:
    """向 schema/__init__.py 添加新数据库的 import 和 __all__ 条目。"""
    init_path = schema_dir / "__init__.py"
    module = _parse_file(init_path)

    # 检查是否已存在
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == dirname:
            return  # 已存在，不重复添加

    new_import = _import_from(dirname, [db_varname], level=1)
    _insert_import(module, new_import)
    _add_to_all_db_list(module, db_varname)

    _write_py(init_path, _module_to_source(module))


# 公开 API


def add_db(filename: str, tables: list[str]) -> None:
    """添加或合并数据库 schema。

    接收表名字符串列表，内部转换为 schema 层 Table 后写入
    dbtools/schema/ 目录。

    若 filename 对应的数据库尚不存在，创建完整的新子包（目录、表文件、
    __init__.py），并更新 schema/__init__.py。

    若 filename 已存在，仅增量添加 tables 中尚不存在的表——不移除任何
    现有 schema。表的去重依据为 Table.name（SQL 表名）。

    Args:
        filename: 完整数据库文件名，如 "profile_info.db"
        tables: SQL 表名列表（来自 discover 模块的 get_tables_by_files）
    """
    _validate_db_filename(filename)
    schema_tables = [Table(name=t, columns=[]) for t in tables]
    schema_dir = _SCHEMA_DIR
    existing_dbs = _scan_existing_dbs(schema_dir)

    if filename in existing_dbs:
        _merge_existing_db(existing_dbs[filename], filename, schema_tables)
    else:
        _create_new_db(schema_dir, filename, schema_tables)


def add_columns(db_name: str, table_name: str, *paths: str) -> None:
    """从 SQLite 文件发现列信息，追加到已有表的 schema 定义中。

    调用 ``get_columns_by_files(*paths, table_name)`` 获取实际列，
    将 ``DBColumn`` 映射为 ``schema.base.Column``，仅追加 ``id`` 尚不
    存在的列（增量合并）。已有的列定义保持不变。

    列映射:
        DBColumn.name  →  Column.id
        f"unknown_{DBColumn.name}"  →  Column.name
        DBColumn.col_type  →  Column.field_type

    目标数据库和表必须在 ``dbtools/schema/`` 中已存在。

    Args:
        db_name: 数据库文件名，如 ``"profile_info.db"``。
        table_name: SQL 表名，如 ``"buddy_list"``。
        *paths: 一个或多个 SQLite 数据库文件路径，用于发现列。

    Raises:
        ValueError: **db_name** 不在 schema 目录中，
            或 **table_name** 不在该数据库子包中。
    """
    existing_dbs = _scan_existing_dbs(_SCHEMA_DIR)
    if db_name not in existing_dbs:
        raise ValueError(f"Database {db_name!r} not found in schema")
    db_dir = existing_dbs[db_name]

    # 仅搜索 __init__.py 实际导入的模块（不扫描未导入的工具模块）
    table_path: Path | None = None
    table_module: ast.Module | None = None
    for mod_path, mod_ast, _imported_varnames in _iter_init_imports(db_dir):
        for node in mod_ast.body:
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            if not (isinstance(call.func, ast.Name) and call.func.id == "Table"):
                continue
            for kw in call.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == table_name:
                    table_path = mod_path
                    table_module = mod_ast
                    break
            if table_path is not None:
                break
        if table_path is not None:
            break

    if table_path is None or table_module is None:
        raise ValueError(f"Table {table_name!r} not found in {db_name}")

    table_call = _find_table_call(table_module, table_name)
    columns_list = _extract_columns_list(table_call)
    existing_ids = _collect_column_ids(columns_list)

    db_columns = get_columns_by_files(*paths, table=table_name)

    new_columns: list[Column] = []
    for db_col in db_columns:
        col_id = db_col.name
        if col_id not in existing_ids:
            new_columns.append(
                Column(
                    id=col_id,
                    name=f"unknown_{col_id}",
                    field_type=db_col.col_type,
                )
            )
            existing_ids.add(col_id)

    if not new_columns:
        return

    for col in new_columns:
        columns_list.elts.append(_obj_to_ast(col))

    _ensure_base_import(table_module, "Column")

    source = _module_to_source(table_module)
    _write_py(table_path, source)


def add_empty_db(filename: str) -> None:
    """创建空数据库 schema 子包（无表）。

    生成目录、``__init__.py``，更新 ``schema/__init__.py``。
    若数据库已存在则无操作。

    Args:
        filename: 数据库文件名，必须以 ``.db`` 结尾。
    """
    _validate_db_filename(filename)
    add_db(filename, [])


def add_empty_table(db_name: str, table_name: str) -> None:
    """向数据库添加一个空表（``columns=[]``）。

    若数据库不存在则创建之。若表已存在则无操作。

    Args:
        db_name: 数据库文件名。
        table_name: SQL 表名。
    """
    add_db(db_name, [table_name])


def remove_db(filename: str) -> None:
    """安全移除数据库 schema 子包。

    删除子包目录，并从 ``schema/__init__.py`` 中移除对应的 import
    和 ``__all_db__`` 条目。

    Args:
        filename: 数据库文件名，如 ``"profile_info.db"``。

    Raises:
        ValueError: 数据库不在 schema 目录中。
    """
    _validate_db_filename(filename)
    schema_dir = _SCHEMA_DIR
    existing_dbs = _scan_existing_dbs(schema_dir)

    if filename not in existing_dbs:
        raise ValueError(f"Database {filename!r} not found in schema")

    db_dir = existing_dbs[filename]
    db_varname = _find_db_varname(db_dir)
    if db_varname is None:
        raise ValueError(f"在 {db_dir} 中未找到 Database 变量")

    # 删除子包目录
    shutil.rmtree(db_dir)

    # 更新 schema/__init__.py
    dirname = _filename_to_dirname(filename)
    init_path = schema_dir / "__init__.py"
    module = _parse_file(init_path)
    _remove_import(module, dirname, {db_varname})
    _remove_from_all_db_list(module, db_varname)
    _write_py(init_path, _module_to_source(module))


def remove_table(db_name: str, *table_names: str) -> None:
    """安全移除数据库中的一张或多张表。

    删除表定义文件（单表模块）或从多表模块中移除对应的 Table 赋值。
    同时更新 ``__init__.py`` 的 import 和 ``tables`` 列表。

    移除最后一张表后，数据库子包保留（空数据库），行为与
    ``add_empty_db`` 对称。

    Args:
        db_name: 数据库文件名，如 ``"profile_info.db"``。
        *table_names: 一个或多个 SQL 表名，如 ``"buddy_list"``。

    Raises:
        ValueError: 数据库或任意表不在 schema 目录中，或未指定表名。
    """
    if not table_names:
        raise ValueError("至少需要指定一个表名")

    schema_dir = _SCHEMA_DIR
    existing_dbs = _scan_existing_dbs(schema_dir)

    if db_name not in existing_dbs:
        raise ValueError(f"Database {db_name!r} not found in schema")

    db_dir = existing_dbs[db_name]
    existing_tables = _get_existing_table_map(db_dir)

    # fail-fast：验证所有表存在
    for table_name in table_names:
        if table_name not in existing_tables:
            raise ValueError(f"Table {table_name!r} not found in {db_name}")

    # 构建 varname → (mod_path, mod_ast, modulename) 映射
    varname_to_module: dict[str, tuple[Path, ast.Module, str]] = {}
    for mod_path, mod_ast, imported_varnames in _iter_init_imports(db_dir):
        for vn in imported_varnames:
            varname_to_module[vn] = (mod_path, mod_ast, mod_path.stem)

    # 按模块文件分组待移除的表
    from collections import defaultdict

    module_tables: dict[Path, list[tuple[str, str]]] = defaultdict(list)
    for table_name in table_names:
        varname = existing_tables[table_name]
        mod_path, _, _ = varname_to_module[varname]
        module_tables[mod_path].append((table_name, varname))

    # 处理每个模块文件
    for mod_path, tables_in_module in module_tables.items():
        mod_ast = _parse_file(mod_path)
        module_table_map = _extract_table_map_from_module(mod_ast)
        active_in_module = {tn for tn, tv in module_table_map.items() if tn in existing_tables}
        removing_from_module = {tn for tn, _ in tables_in_module}

        if removing_from_module >= active_in_module:
            # 移除该模块的所有活跃表 → 删除整个文件
            mod_path.unlink()
        else:
            # 仅移除部分表
            for table_name, _ in tables_in_module:
                _remove_table_assignment(mod_ast, table_name)
            source = _module_to_source(mod_ast)
            _write_py(mod_path, source)

    # 更新 __init__.py（一次性处理所有移除）
    init_py = db_dir / "__init__.py"
    module = _parse_file(init_py)

    # 按 modulename 分组 varnames 用于移除 import
    modulename_varnames: dict[str, set[str]] = defaultdict(set)
    for table_name in table_names:
        varname = existing_tables[table_name]
        _, _, modulename = varname_to_module[varname]
        modulename_varnames[modulename].add(varname)

    for modulename, varnames in modulename_varnames.items():
        _remove_import(module, modulename, varnames)

    # 移除 tables=[...] 中的变量名
    db_call = _find_db_call(module)
    if db_call is None:
        raise ValueError(f"在 {init_py} 中未找到 Database(...) 调用")
    table_list = _extract_table_list(db_call)
    if table_list is None:
        raise ValueError(f"在 {init_py} 中未找到 tables=[...] 列表")
    for table_name in table_names:
        _remove_from_table_list(table_list, existing_tables[table_name])

    _write_py(init_py, _module_to_source(module))
