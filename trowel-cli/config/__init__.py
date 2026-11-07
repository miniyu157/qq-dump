"""读取 CWD 下的 .trowel 与 TROWEL_ 环境变量。

dotfile 给出工作区与别名，并按它们解析命令行输入的数据库名称；
catalog 列出工作区与 CWD 中可用的数据库，以及数据库中的表与表别名。
load_config 在配置错误时退出进程。
"""
