"""本项目的应用层: cli/ 脚本调用、数据库补全流程与表现约定。

scripts 负责构造 cli/ 子进程命令行，是否经 sudo 执行由调用方指定；
accounts 是 key、db 与数据库补全共用的前置步骤: 确定平台与数据根目录、做前置校验，不通过时退出进程，并封装取密钥时的密钥缓存与扫描 QQ 进程内存失败后的交互提权重跑；
key_cache 决定密钥缓存的位置并记入新取得的密钥，会写仓库下的 .cache/keys.json 或调用方指定的文件；
databases 组合 scripts 与交互选择，为子命令补全缺省的数据库路径；
env 读取环境变量与仓库根目录的 .env；
integrations 接入外部项目，负责配置改写与启动子进程；
ansi、utils、output 为主题配色、风格化消息、依赖检查，以及 JSON 输出。

ansi 在导入时读取 stdout 与 stderr 的 TTY 状态，utils 的检查函数在依赖缺失时退出进程。
通用且无副作用的模块位于 lib/。
"""
