<div align="center">

# QQ DUMP

极速的 Android 端 NTQQ 数据库密钥提取与解密工具。遵循 KISS 原则与 Unix 哲学, 针对移动端闪存优化 I/O 策略, 最小化读写磨损。

[English](./README_en.US.md) | [简体中文](./README.md)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Shell Check](https://img.shields.io/badge/ShellCheck-passing-success)

</div>

## 依赖

- Root 权限
- sqlcipher 二进制文件

qq-dump 会使用 termux 的二进制文件, 进入 Termux 使用以下命令补全依赖

```bash
pkg install -y sqlcipher git coreutils
```

## 安装

你需要一款终端模拟器, 例如 [termux/termux-app](https://github.com/termux/termux-app/releases)

```bash
git clone https://github.com/miniyu157/qq-dump.git ~/.local/bin/qq-dump-bin
```

```bash
ln -s ~/.local/bin/qq-dump-bin/qq-dump ~/.local/bin/qq-dump
```

> 如果指定了其它软链接名称, 则下文用法中替换为你的自定义名称

> [!NOTE]
> 确保 `~/.local/bin` 位于 PATH 环境变量中

> [!TIP]
> qq-dump 会尝试自动更新, 若想要禁用更新, 新建一个 `.dev` 空文件在 qq-dump 根目录即可

## 用法

```
qq-dump key [--raw]
```

**`qq-dump key` 命令用于获取账号信息与密钥,
加上 `--raw` 选项即可得到机器可读的原始数据, 通常用于管道操作**

---

**`qq-dump db` 命令用于解密数据库, 依赖 `./dumpkey` 获取密钥**

```
qq-dump db [--use-disk] [path=db_output/]
```

默认会将文件输出到脚本所在文件夹的 `db_output/`,
可以使用参数指定一个新的路径, 需要确保那个路径存在

如果脚本所在文件夹的 `./db_list.txt` 存在且非空, 则仅解密列表中指定的数据库,
默认有 nt_msg.db 和 profile_info.db, 每行一个文件名

临时文件使用 /tmp (tmpfs) 以获得更快的读写速度,
使用 `--use-disk` 选项即可使用磁盘进行读写临时文件

---

**别名**

- db = database
- key = k

## 关于从数据库中提取人类可读的文本

我的另一个仓库 [miniyu157/QQRootFastDecrypt](https://github.com/miniyu157/QQRootFastDecrypt) 虽然已经归档, 它是 100% 由 LLM 编写的, 其中的 `export_chats.py` 完成度非常高, 并且难以维护

我不知道应该怎样将它与 qq-dump 配合, 如果你有想法, 请告诉我或者提交 issues。谢谢!

## 致谢

解密算法思路源自 [QQBackup/QQDecrypt](https://github.com/QQBackup/QQDecrypt/)。

## 许可证

本项目采用 **GNU General Public License v3.0 (GPLv3)** 进行授权。
详见 [LICENSE](LICENSE) 文件。

Copyright (C) 2025 Yumeka <miniyu157@163.com>
