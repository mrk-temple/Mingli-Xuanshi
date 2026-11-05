"""pytest 全局 fixture —— 隔离运行状态，避免开发机残留污染测试。

- LLM 配置（data/settings.json）：每个测试指向独立的临时路径，确保「无 key →
  降级」「有 key → 生效」的判定只取决于本测试设置，而非开发机遗留的配置文件。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGLI_SETTINGS_FILE", str(tmp_path / "settings.json"))
