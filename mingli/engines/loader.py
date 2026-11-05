"""引擎加载 shim —— 以 importlib 稳定别名加载 xuan-shu/scripts 下现有脚本。

原则（第二原则：Calculator 与 LLM 分离）：
- 不复制算法、不改写逻辑，直接 import 原脚本模块；CLI 与程序共用同一份代码，
  golden 测试保证两条路径输出一致。
- 脚本目录只读。未来脚本自身的重构（main() 拆纯函数）在本目录的包装层消化。

每个 loader 返回 (module, engine_name, version_tag)。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "xuan-shu", "scripts")

# 逻辑名 → 脚本文件名
_ENGINE_FILES = {
    "paipan": "paipan.py",
    "liuyao": "liuyao.py",
    "daliuren": "daliuren.py",
    "xiaoliuren": "xiaoliuren.py",
    "qigua": "qigua.py",
    "tarot": "tarot.py",
    "lunar_convert": "lunar_convert.py",
    "common": "common.py",
}

_cache: dict[str, Any] = {}


def load_engine(name: str) -> Any:
    """按逻辑名加载 xuan-shu/scripts 脚本为模块（带缓存）。

    模块以 mingli_engine_<name> 别名注册进 sys.modules，避免与用户环境
    其他同名模块冲突；scripts 目录加入 sys.path 以支持脚本间的
    `from common import ...` 相对引用。
    """
    if name in _cache:
        return _cache[name]
    if name not in _ENGINE_FILES:
        raise KeyError(f"未知引擎: {name}")
    path = os.path.join(SCRIPTS_DIR, _ENGINE_FILES[name])
    if not os.path.exists(path):
        raise FileNotFoundError(f"引擎脚本缺失: {path}")
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    spec = importlib.util.spec_from_file_location(f"mingli_engine_{name}", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - spec 由合法路径构造
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _cache[name] = module
    return module


ENGINE_VERSIONS: dict[str, str] = {}


def engine_version(name: str) -> str:
    """返回引擎脚本的指纹版本（mtime+size），用于 session 可追溯。"""
    path = os.path.join(SCRIPTS_DIR, _ENGINE_FILES[name])
    st = os.stat(path)
    return f"{int(st.st_mtime)}-{st.st_size}"
