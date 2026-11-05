"""LLM 接入配置 —— 本地持久化的 Provider / API Key / 模型 / 解释器模式 / 回答风格。

用户经 /settings 页填入的配置持久化到 data/settings.json（已 gitignore）；
未在页面配置时回落到环境变量（ANTHROPIC_API_KEY / MINGLI_INTERPRETER / MINGLI_MODEL）。

本项目只支持「远程 API 接入」——不下载、不运行任何本地部署模型。可算者交给
确定性引擎、可释者交给规则库，LLM 仅是可选解释/综合/对话插槽。
Provider 抽象：anthropic（原生 Messages API）/ openai-compatible（含 DeepSeek 等，
经 base_url 适配）/ 自定义 OpenAI 兼容端点。
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

_DEFAULT_MODEL_ANTHROPIC = "claude-opus-4-8"
_default_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "settings.json",
)

# 支持的 provider 与其默认端点/模型（openai-compatible 覆盖 DeepSeek 等兼容网关）
PROVIDERS: dict[str, dict[str, str]] = {
    "mimo": {"label": "小米 MiMo", "base_url": "https://api.xiaomimimo.com/v1",
             "default_model": "mimo-v2.6-flash"},
    "anthropic": {"label": "Anthropic", "base_url": "", "default_model": "claude-opus-4-8"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
                 "default_model": "deepseek-chat"},
    "openai-compatible": {"label": "OpenAI 兼容", "base_url": "",
                          "default_model": ""},
}

# 回答风格（玄师对话/解读的长度与深度倾向；只影响 prompt，不影响计算）
STYLES: dict[str, str] = {
    "concise": "简洁",
    "standard": "标准",
    "research": "深入研究",
}


def _settings_path() -> str:
    """配置文件位置；测试/部署可经 MINGLI_SETTINGS_FILE 重定向。"""
    return os.environ.get("MINGLI_SETTINGS_FILE", _default_path)


def load() -> dict:
    """读取已保存的配置；缺失/损坏 → 空 dict，绝不因配置问题拖垮应用。"""
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d: dict) -> None:
    path = _settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def clear() -> None:
    """清除已保存的配置（回到仅环境变量状态）。"""
    with contextlib.suppress(OSError):
        os.remove(_settings_path())


def api_key() -> str | None:
    """有效 API Key：页面保存的优先，否则环境变量。"""
    saved = (load() or {}).get("api_key")
    if saved:
        return saved
    key_file = (load() or {}).get("api_key_file")
    if key_file and provider() == "mimo":
        try:
            content = Path(key_file).read_text(encoding="utf-8-sig")
            match = re.search(r"(?im)^\s*Mimo\s+API\s+Key\s*[:：=]\s*(\S+)\s*$", content)
            return match.group(1).strip("\"'`") if match else None
        except OSError:
            return None
    if provider() == "mimo":
        return os.environ.get("MIMO_API_KEY")
    return os.environ.get("ANTHROPIC_API_KEY")


def has_key() -> bool:
    return bool(api_key())


def provider() -> str:
    """LLM Provider：页面保存的优先，默认 anthropic。"""
    return (load() or {}).get("provider") or os.environ.get("MINGLI_PROVIDER", "anthropic")


def base_url() -> str | None:
    """自定义端点（OpenAI 兼容协议）；anthropic 原生走 SDK 默认。"""
    saved = (load() or {}).get("base_url")
    if saved:
        return saved.rstrip("/")
    p = PROVIDERS.get(provider(), {})
    return p.get("base_url") or None


def model() -> str:
    """当前模型：页面保存的优先，否则 MINGLI_MODEL，否则按 provider 默认。"""
    saved = (load() or {}).get("model")
    if saved:
        return saved
    env = os.environ.get("MINGLI_MODEL")
    if env:
        return env
    return str(PROVIDERS.get(provider(), {}).get("default_model") or _DEFAULT_MODEL_ANTHROPIC)


def interpreter() -> str:
    """解释器模式：页面保存的优先，否则 MINGLI_INTERPRETER，默认 rule-engine。"""
    saved = (load() or {}).get("interpreter")
    if saved:
        return saved
    return os.environ.get("MINGLI_INTERPRETER", "rule-engine")


def style() -> str:
    """回答风格：页面保存优先；只影响对话/解读的行文倾向，不影响计算。"""
    s = (load() or {}).get("style")
    return s if s in STYLES else "standard"
