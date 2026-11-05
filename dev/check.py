#!/usr/bin/env python3
"""开发质量门 —— 一键跑 ruff / mypy / pytest / 应用冒烟。

用法（仓库根目录）：
    python dev/check.py

每项失败即退出；全部通过打印 GATE PASSED。
"""
from __future__ import annotations

import subprocess
import sys

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文/符号乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

STEPS: list[tuple[str, list[str]]] = [
    ("ruff", ["python", "-m", "ruff", "check", "mingli", "tests"]),
    ("mypy", ["python", "-m", "mypy", "mingli"]),
    ("pytest", ["python", "-m", "pytest", "tests/", "-q"]),
    ("smoke", ["python", "dev/smoke.py"]),
]


def main() -> int:
    failed = False
    for name, cmd in STEPS:
        print(f"\n=== {name} ===")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"  ✗ {name} FAILED")
            failed = True
        else:
            print(f"  ✓ {name} passed")
    if failed:
        print("\nGATE FAILED — 修复后重跑 dev/check.py")
        return 1
    print("\nGATE PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
