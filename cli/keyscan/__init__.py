"""PC (Windows/Linux) 下从已登录 QQ 进程内存提取 NTQQ 主库 raw_key 的内部实现。

对 cli/get_keys.py 暴露扫描账号密钥的能力；get_keys.py 负责参数解析、按操作系统
选择后端与 JSON 组装，本包只提供数据与进程后端。各子模块职责:
  verify  第 1 页 HMAC 校验与算法探测，纯 hashlib/hmac，不碰 AES
  scan    锚点/簇候选收集与排序，纯数据函数，可用假内存测试

进程枚举与内存读取的后端 (process_windows / process_linux) 另按需导入，
导入代价与操作系统绑定，由 get_keys.py 按操作系统选择，不在此处汇总。
"""

__all__ = ["scan", "verify"]
