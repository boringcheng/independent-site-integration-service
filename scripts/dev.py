#!/usr/bin/env python
"""跨平台任务入口，替代 Makefile。

用法：
    python scripts/dev.py check      # lint + format 检查 + 类型检查 + 测试
    python scripts/dev.py test
    python scripts/dev.py lint
    python scripts/dev.py up         # 启动 MySQL / Redis
    python scripts/dev.py down
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def docker_compose(*args: str) -> list[str]:
    docker = shutil.which("docker")
    if docker is None:
        sys.exit("未找到 docker，请先启动 Docker Desktop")
    return [docker, "compose", "-f", "docker-compose.dev.yml", *args]


def cmd_install() -> None:
    run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"])


def cmd_lint() -> None:
    run([sys.executable, "-m", "ruff", "check", "."])


def cmd_format() -> None:
    run([sys.executable, "-m", "ruff", "format", "."])


def cmd_format_check() -> None:
    run([sys.executable, "-m", "ruff", "format", "--check", "."])


def cmd_typecheck() -> None:
    run([sys.executable, "-m", "mypy", "app"])


def cmd_test() -> None:
    run([sys.executable, "-m", "pytest", *sys.argv[2:]])


def cmd_check() -> None:
    cmd_lint()
    cmd_format_check()
    cmd_typecheck()
    cmd_test()


COMMANDS = {
    "install": cmd_install,
    "lint": cmd_lint,
    "format": cmd_format,
    "format-check": cmd_format_check,
    "typecheck": cmd_typecheck,
    "test": cmd_test,
    "check": cmd_check,
    "up": lambda: run(docker_compose("up", "-d")),
    "down": lambda: run(docker_compose("down")),
    "ps": lambda: run(docker_compose("ps")),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="项目任务入口")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="透传给底层命令")
    args = parser.parse_args()
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
