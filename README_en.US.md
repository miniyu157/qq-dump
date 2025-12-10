<div align="center">

# QQ DUMP

An ultra-fast NTQQ database key extraction and decryption tool for Android. Adhering to the KISS principle and Unix philosophy, it features I/O strategies optimized for mobile flash storage to minimize read/write wear.

[English](./README_en.US.md) | [简体中文](./README.md)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Shell Check](https://img.shields.io/badge/ShellCheck-passing-success)

</div>

## Dependencies

- Root Access
- sqlcipher binary

qq-dump utilizes Termux binaries. Enter Termux and use the following command to install dependencies:

```bash
pkg install -y sqlcipher git coreutils
```

## Installation

You need a terminal emulator, such as [termux/termux-app](https://github.com/termux/termux-app/releases).

```bash
git clone https://github.com/miniyu157/qq-dump.git ~/.local/bin/qq-dump-bin
```

```bash
ln -s ~/.local/bin/qq-dump-bin/qq-dump ~/.local/bin/qq-dump
```

> If a different symlink name is specified, replace it with your custom name in the usage examples below.

> [!NOTE]
> Ensure `~/.local/bin` is in your PATH environment variable.

> [!TIP]
> qq-dump attempts to update automatically. To disable updates, simply create an empty `.dev` file in the root directory of qq-dump.

## Usage

**The `qq-dump key` command is used to retrieve account information and keys.
Adding the `core` argument yields machine-readable raw data, typically for piping operations.**

Example:

```bash
qq-dump key
```

```bash
qq-dump key core
```

---

**The `qq-dump db` command is used to decrypt the database; it relies on `./dumpkey` to obtain the key.**

By default, files are output to `db_output/` in the script's directory.
You can specify a new path as an argument; ensure that the path exists.

If `./db_list.txt` in the script's directory exists and is not empty, only the databases specified in the list will be decrypted.
Default files are `nt_msg.db` and `profile_info.db`, listed one filename per line.

Example:

```bash
qq-dump db
```

```bash
qq-dump db /sdcard/_qqdb
```

---

**Aliases**

- db = database
- key = k

## About Extracting Human-Readable Text from Databases

Although my other repository [miniyu157/QQRootFastDecrypt](https://github.com/miniyu157/QQRootFastDecrypt) is now archived, it was written 100% by LLMs. The included `export_chats.py` is highly functional but difficult to maintain.

I am unsure how to best integrate it with `qq-dump`. If you have any ideas, please let me know or submit an issue. Thank you!

## Credits

The decryption algorithm concept is derived from [QQBackup/QQDecrypt](https://github.com/QQBackup/QQDecrypt/).

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.
See the [LICENSE](LICENSE) file for details.

Copyright (C) 2025 Yumeka <miniyu157@163.com>
