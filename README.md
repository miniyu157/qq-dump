# qq-dump

极速的 Android 端 NTQQ 数据库密钥提取与解密工具。遵循 KISS 原则与 Unix 哲学，针对移动端闪存优化 I/O 策略 ，最小化读写磨损。

## 依赖

  * Root 权限
  * /data/data/com.termux/files/usr/sqlcipher

若没有 sqlcipher, 进入 Termux 使用以下命令安装

```bash
pkg install -y sqlcipher
```

### 🚀 安装

你需要一款终端软件，例如 [termux/termux-app](https://github.com/termux/termux-app/releases)

```bash
git clone https://github.com/miniyu157/qq-dump.git ~/.local/bin/qq-dump-bin
```

```bash
ln -s ~/.local/bin/qq-dump-bin/qq-dump ~/.local/bin/qq-dump
```

> [!NOTE]
> 确保 `~/.local/bin` 位于 PATH 环境变量中

## 用法

查看人类可读的账号信息与密钥:

```bash
qq-dump k

# 等同于
# qq-dump key
```

获取机器可读的原始数据:

```bash
qq-dump k core

# 等同于
# qq-dump key core
```

批量解密并导出数据库:

默认导出在脚本所在文件夹的 `db_output/`, 可以使用参数指定一个新的路径, 确保那个路径存在

```bash
qq-dump db [db_output/]

# 等同于
qq-dump database [db_output/]
```

> [!NOTE]
> 若 `db_list.txt` 存在且非空, 仅导出列表中指定的数据库, 默认有 nt_msg.db 和 profile_info.db。

## 致谢

解密算法思路源自 [QQBackup/QQDecrypt](https://github.com/QQBackup/QQDecrypt/)。

## 许可证

本项目采用 **GNU General Public License v3.0 (GPLv3)** 进行授权。
详见 [LICENSE](LICENSE) 文件。

Copyright (C) 2025 Yumeka <miniyu157@163.com>