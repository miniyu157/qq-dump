#!/usr/bin/env sh
# shellcheck shell=sh

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Yumeka <miniyu157@163.com>

# Description: A POSIX-compliant loading animation function
# Author: Yumeka <miniyu157@163.com>
# Usage: loading <PID>

loading() (
    _pid=$1
    _show=$2

    _delay=0.1

    trap 'printf "\r\033[K\033[?25h"; exit' INT TERM EXIT

    set -- ⠁⠀ ⠋⠀ ⠟⠁ ⠞⠁ ⡕⠉ ⣕⠝ ⢐⡴ ⢀⡴ ⠀⣠ ⠀⢀

    printf '\033[?25l'

    while kill -0 "$_pid" 2> /dev/null; do
        for _frame; do
            kill -0 "$_pid" 2> /dev/null || break
            printf '\r%s %s' "$_frame" "$_show"
            sleep "$_delay"
        done
    done
    printf '\r\033[K\033[?25h'
)
