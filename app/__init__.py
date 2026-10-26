"""本项目的应用层: cli/ 脚本调用、数据库补全流程与表现约定。

scripts 是 cli/ 的唯一调用方，负责构造命令行与决定是否经 sudo 执行；
databases 组合 scripts 与交互选择，为子命令补全缺省的数据库路径；
ansi、utils、output 为主题配色、风格化消息、依赖检查与 JSON 输出。

ansi 在导入时读取 stdout 与 stderr 的 TTY 状态，utils 的检查函数在依赖缺失时退出进程。
通用且无副作用的模块位于 lib/。
"""
