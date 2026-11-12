# 测试

```bash
python -m unittest discover -s test -t test          # 全部 (实机层默认跳过)
python -m unittest discover -s test/unit -t test     # 只跑某一层
QQDUMP_TEST_LIVE=1 python -m unittest discover -s test/live -t test   # 实机层
```

只用标准库，不需要安装任何包。需要 `sqlcipher` 的用例在缺少它 (或它无法运行) 时显示为带原因的跳过。

## 一条测试要满足什么

一条测试是一条可以被证伪的断言: 被测行为坏了，它必须失败；它失败时，读者应能从名字与消息看出哪条承诺被破坏。
为此，结构上有四条规则，编写与 review 时逐条对照。

1. **只测公开接口。** 模块只调用 `__all__` 中的名字；脚本 (`cli/*.py`、`main.py`、启动器) 的接口是命令行，只经子进程按参数、输出与退出码判定。不调用下划线开头的名字，不断言实现细节，重构内部不应打断测试。
2. **判定基准独立于实现。** 期望值只来自规范与标准向量、第三方工具 (真实的 sqlcipher、标准库 sqlite3)、文档写明的公式或手写的字面量，不从被测模块借用表或函数。每个测试模块的 docstring 写明它用的基准。
3. **替身只放在三类边界。** 函数参数与注入的对象；运行环境 (环境变量、PATH、当前目录、`sys.platform`、`os.geteuid`、终端探测)；其他模块的公开接口。项目自己的私有函数不替换。组件层里被替身代替的接口，契约层必须有真实运行的用例为它背书 (`support/records.py` 的字段由 `contract/test_app_scripts.py` 与真实输出比对)。
4. **跳过与未覆盖必须可见。** 缺少前提时跳过并写明原因，不静默通过；前提以实际运行工具为准。没有测到的部分登记在下方清单。测出的缺陷按正确行为编写用例，用 `support.requires.known_issue` 在缺陷存在的环境里标为预期失败，并登记在下方；修复后标记自动失效，用例转为必须通过。

## 层级

层级按边界划分，看一个用例碰了什么就能判断它属于哪一层。

| 层级 | 目录 | 允许 | 不允许 |
| --- | --- | --- | --- |
| 数据 | `unit/` | 纯函数调用 | 文件、子进程、任何替身 |
| 组件 | `component/` | 临时目录、sqlite、本机回环端口、规则 3 的替身 | 启动项目的脚本进程 |
| 契约 | `contract/` | 真实启动项目的脚本、主程序与启动器；替换运行环境 | 替换项目内的任何名字 |
| 实机 | `live/` | 本机真实的 QQ 数据与进程 | 默认运行 |

契约层不触发真实的内存扫描: 合成的 windows 与 linux 数据在同一系统上会让 `get_keys.py` 去扫描真实的 QQ 进程，所以只用「账号全部由缓存命中」「缺少 settings.db」或「另一系统的布局」三类数据，扫描路径在组件层用假进程后端测。主程序一律带 `-E` 与临时的 `-k` 运行，不读开发者的环境配置，也不写仓库的 `.cache/keys.json`。

其余目录:

- `support/`: 构造器与运行辅助，不是测试。构造器按外部规范独立实现，充当判定基准。
- `manual/`: 手动工具。`choose.py`、`confirm.py` 在真实终端里试用交互组件；`make_root.py` 生成 `test/root/` 供手动试用各命令 (`./qqdump -E -r test/root key`)，与自动化测试共用 `support/` 的定义。

## 判定基准

| 对象 | 基准 |
| --- | --- |
| protobuf 解析 | 编码文档中的字节示例；`support/wire.py` 编码器 |
| AES 解密 | FIPS-197 附录 C.3 与 SP 800-38A 的标准向量 |
| 页 HMAC 与算法探测 | `support/qqnt.py` 按 SQLCipher 页格式构造的库 |
| login.db 与 WAL 合并 | 标准库 sqlite3 写入的行 = 解密后读出的行 |
| Android 密钥 | 文档公式用 hashlib 直接计算，契约层再用它实际解密 |
| 数据库解密 | 写入的行 = 导出库经标准库 sqlite3 读出的行 |
| 好友与主人信息 | `support/profile.py` 中手写的期望记录 |
| WebUI | HTTP 状态码、响应头与手写的期望数据 |
| 实机 | 取到的密钥让真实的库通过 SQLite 完整性检查 |

构造器自身也须被检验: `unit/test_support.py` 用标准向量检验 AES 加密与 protobuf 编码；`support/qqnt.py` 构造的库在契约层由真实 sqlcipher 解开，`support/roots.py` 写出的 login.db 由 `get_keys.py` 读出，两者互为验证。

## 实机层

| 变量 | 作用 |
| --- | --- |
| `QQDUMP_TEST_LIVE=1` | 对本机真实的 QQ 取密钥，并用它解密一个库做完整性检查。windows 与 linux 须 QQ 正在运行并已登录；Linux 读进程内存通常须 root，无权时跳过并给出命令 |
| `QQDUMP_TEST_LIVE_BIG=1` | 另外解密一个超过 1 GiB 的库，验证锁页迁移；需要 openssl，临时目录所在的盘须有约两倍于该库的空间 |

实机层只调用 cli 脚本，不读写密钥缓存，解密输出在临时目录，结束后删除。

## 未覆盖

| 部分 | 原因 |
| --- | --- |
| 超过 1 GiB 的库的锁页迁移 | 合成数据须超过 1 GiB 且符合 QQ 的页布局，代价过高；只在实机层验证 |
| QQ 进程内存的真实布局 | 只能在实机层验证 |
| 交互式选择与确认、数据库补全流程、WebUI 的启动交互 | 需要真实终端；用 `manual/` 的工具手动试用 |
| 真实的提权 | 只验证经 sudo 执行的命令行与提示 (假 sudo，POSIX)，不执行真实的 sudo |
| 头像的网络请求、依赖补全、t28 集成、legacy-cli、scripts/table2d | 本轮范围之外 |

## 已知问题

测试发现、尚未修复的缺陷。前两项有对应的预期失败用例，修复后用例会自动转为必须通过。

1. **sqlcipher 打不开含非 ASCII 字符的路径 (部分 Windows 构建)。** `decrypt_db.py` 把临时文件路径作为命令行参数交给 sqlcipher，这些构建按 ANSI 代码页接收参数却当作 UTF-8 解释，于是另建一个文件名乱码的库并报 `unable to open database file`。输出目录含中文时解密失败；Windows 用户名含中文时，`%TEMP%` 下的自动解密同样受影响。
   用例: `contract/test_decrypt_db_cli.py` 的 `test_output_path_with_non_ascii_characters`。
2. **主程序与 cli 脚本之间的管道没有指定编码。** `app/scripts.py` 按系统默认编码读取脚本输出的 JSON，而脚本按自己的默认编码写出。数据根目录的路径含默认编码表示不了的字符时取密钥失败: 中文 Windows (GBK) 上是 emoji 与生僻字，英文 Windows 上连中文也不行；UTF-8 环境不受影响。
   用例: `contract/test_app_scripts.py` 的 `test_data_root_with_a_chinese_name` 与 `test_data_root_with_a_name_outside_the_ansi_code_page`。
3. **WebUI 拒绝带请求体的 POST 时可能被客户端视为连接中断。** 凭据、Host 或路径不符时服务端不读请求体就回应并关闭连接，Windows 上客户端有时收到连接被重置而不是 403/404。拒绝本身是正确的，影响的是客户端能否看到状态码。现象时有时无，不适合写成预期失败的用例；`component/test_web_server.py` 中这类请求不带请求体。
