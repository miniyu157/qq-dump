# qq-dump

极速的 Android 端 NTQQ 数据库密钥提取与解密工具。遵循 KISS 原则与 Unix 哲学, 针对移动端闪存优化 I/O 策略, 最小化读写磨损。

## 依赖

  * Root 权限
  * sqlcipher 二进制文件

qq-dump 会使用 termux 的二进制文件, 若没有 sqlcipher, 进入 Termux 使用以下命令安装

```bash
pkg install -y sqlcipher
```

### 安装

你需要一款终端软件, 例如 [termux/termux-app](https://github.com/termux/termux-app/releases)

```bash
git clone https://github.com/miniyu157/qq-dump.git ~/.local/bin/qq-dump-bin
```

```bash
ln -s ~/.local/bin/qq-dump-bin/qq-dump ~/.local/bin/qq-dump
```

> [!NOTE]
> 确保 `~/.local/bin` 位于 PATH 环境变量中

> [!TIP]
> qq-dump 会尝试自动更新, 若想要禁用更新, 新建一个 `.dev` 空文件在 qq-dump 根目录即可

## 用法

**`qq-dump key` 命令用于获取账号信息与密钥, 
加上 `core` 参数即可获取机器可读的原始数据, 通常用于管道操作**

示例:

```bash
qq-dump key
```

```bash
qq-dump key core
```

**`qq-dump db` 命令用于解密数据库, 依赖 `./dumpkey` 获取密钥**

默认会将文件输出到脚本所在文件夹的 `db_output/`, 
可以使用参数指定一个新的路径, 需要确保那个路径存在

如果脚本所在文件夹的 `./db_list.txt` 存在且非空, 则仅解密列表中指定的数据库, 
默认有 nt_msg.db 和 profile_info.db

示例:

```bash
qq-dump db
```

```bash
qq-dump db /sdcard/_qqdb
```

**别名**

db = database
key = k

## 致谢

解密算法思路源自 [QQBackup/QQDecrypt](https://github.com/QQBackup/QQDecrypt/)。

## 许可证

本项目采用 **GNU General Public License v3.0 (GPLv3)** 进行授权。
详见 [LICENSE](LICENSE) 文件。

Copyright (C) 2025 Yumeka <miniyu157@163.com>