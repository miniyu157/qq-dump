"""操作。每个模块提供 run，参数由 app.usage 声明；多数为 run(conn, args)，list_files、alias 与 preview_tables 另需配置。

run 会向 stdout 输出渲染结果；需要表存在的操作经 db.schema.require_table 检查，表不存在时抛出 MissingTable。
_status 是各子命令共用的 maps/ 状态显示文字与样式；_listing 是 list_files 与 preview_tables 共用的分组列表。
"""
