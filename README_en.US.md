<div align="center">

# QQ DUMP

An ultra-fast NTQQ database key extraction, decryption, and chat history export tool for Android. Adhering to the KISS principle and Unix philosophy, it features I/O strategies optimized for mobile flash storage to minimize read/write wear.

[English](./README_en.US.md) | [简体中文](./README.md)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Shell Check](https://img.shields.io/badge/ShellCheck-passing-success)

</div>

## Dependencies

- Root Access
- sqlcipher binary
- python

qq-dump utilizes Termux binaries. Enter Termux and use the following command to install dependencies:

```bash
pkg install -y sqlcipher git coreutils python
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

**`dumpkey` is used to retrieve account information and keys.**

```bash
qq-dump key [--raw]
```

`--raw`: Get machine-readable raw data, typically for piping operations.

---

**`dumpdb` is used to decrypt the database; it relies on `./dumpkey` to obtain the key.**

```bash
qq-dump db [--raw] [--use-disk] [path=db_output/]
```

`--raw`: Simplify output, typically for piping operations.

`--use-disk`: Use disk for reading/writing temporary files, defaults to /tmp (tmpfs).

`PATH`: Specify a new output path; ensure that the directory exists. Defaults to `db_output/`.

> [!TIP]
> If you aim for faster speeds, you can directly specify the output directory as /tmp.

> [!NOTE]
> If `./db_list.txt` in the script directory exists and is not empty, only the databases specified in the list will be decrypted.
> Default files are `nt_msg.db` and `profile_info.db`, listed one filename per line.

---

**`dumpchat` is used to export human-readable chat logs, relying on `./dumpdb` and Python scripts in `chat_export`.**

```bash
qq-dump chat <OUTDIR>
```

This command internally invokes ./dumpdb --raw /tmp. Intermediate files reside entirely in memory, ensuring ultra-fast performance.

QQ DUMP embeds the Python scripts from [miniyu157/QQRootFastDecrypt](https://github.com/miniyu157/QQRootFastDecrypt). I modified parts of the argument parsing, but further optimization and adaptation have not yet been done.

Although the QQRootFastDecrypt repository is archived, its `export_chats.py` has very high completeness. It was generated entirely by an LLM, which makes maintenance difficult.

The signature "KlxPiao" in `chat_export/LICENSE` is my other pen name.

---

### Aliases

- db = database
- key = k

## Credits

The decryption algorithm concept is derived from [QQBackup/QQDecrypt](https://github.com/QQBackup/QQDecrypt/).

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.
See the [LICENSE](LICENSE) file for details.

Copyright (C) 2025 Yumeka <miniyu157@163.com>
