"""终端渲染。sheet 定义共用的数据结构；dispatch 按输出形式调度 show2d、showkv、showjson；
tip 向 stderr 输出末尾提示。

除 sheet 外均依赖 rich，由调用方按模块导入。
"""
