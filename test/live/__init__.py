"""实机层: 读取本机真实的 QQ 数据与进程，是 QQ 更新后唯一的回归信号。

默认全部跳过，设置 QQDUMP_TEST_LIVE=1 后运行；直接调用 cli 脚本，不读写密钥缓存，输出在临时目录。"""

import support  # noqa: F401  导入即把仓库根目录加入 sys.path
