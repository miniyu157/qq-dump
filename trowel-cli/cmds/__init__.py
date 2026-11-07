"""操作。每个模块提供 run(conn, args)，参数由 app.usage 声明。

run 会向 stdout 输出渲染结果；表不存在时以退出码 1 退出进程。
_status 是各子命令共用的 maps/ 状态显示文字与样式。
"""
