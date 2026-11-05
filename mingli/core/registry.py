"""SystemRegistry —— 体系注册/发现中心（design.md §4 术数插件化）。

- 所有 Provider 在 import 时注册；registry_data.yaml 登记尚未实现的
  planned / knowledge-only 体系，保证 UI 如实呈现全貌。
- get() 只返回 active 体系的可运行实例；describe_all() 返回含 planned 的全表。
"""
from __future__ import annotations

from typing import Any

import yaml

from mingli.core.models import SystemStatus
from mingli.systems.base import SystemProvider

_REGISTRY_FILE = None  # 延迟定位


_REQUIRED_ATTRS = ("id", "name", "region", "category", "status", "strengths", "limitations")
_REQUIRED_METHODS = ("input_schema", "validate_input", "calculate", "interpret", "recommend_for")


def _check_provider(provider: SystemProvider) -> None:
    """校验 Provider 协议成员齐全（不用 isinstance + runtime_checkable，
    因其对带默认体的协议方法会误判缺失）。"""
    missing = [a for a in _REQUIRED_ATTRS if getattr(provider, a, None) is None]
    missing += [m for m in _REQUIRED_METHODS if not callable(getattr(provider, m, None))]
    if missing:
        raise TypeError(f"{provider!r} 缺少 SystemProvider 成员: {missing}")


class SystemRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, SystemProvider] = {}
        self._planned: list[dict[str, Any]] = []   # 未实现体系的诚实登记

    # ---- 注册 ----

    def register(self, provider: SystemProvider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"体系 id 重复: {provider.id}")
        _check_provider(provider)
        self._providers[provider.id] = provider

    def register_planned(self, entry: dict[str, Any]) -> None:
        """登记 planned/knowledge-only 体系：{id,name,region,category,status,note}。"""
        if entry["status"] == "active":
            raise ValueError("active 体系必须以 Provider 实例注册，不得只写 YAML")
        self._planned.append(entry)

    # ---- 查询 ----

    def get(self, system_id: str) -> SystemProvider:
        try:
            return self._providers[system_id]
        except KeyError:
            raise KeyError(f"体系未注册或不可运行: {system_id}") from None

    def active_providers(self) -> list[SystemProvider]:
        return sorted(self._providers.values(), key=lambda p: p.name)

    def describe_all(self) -> list[dict[str, Any]]:
        """全部体系（含 planned）的展示信息，UI 总览页用。"""
        rows = [
            {
                "id": p.id,
                "name": p.name,
                "region": p.region,
                "category": p.category,
                "status": p.status,
                "strengths": p.strengths,
                "limitations": p.limitations,
                "runnable": True,
            }
            for p in self.active_providers()
        ]
        rows.extend({**e, "runnable": False} for e in self._planned)
        order = {"active": 0, "knowledge-only": 1, "planned": 2}
        return sorted(rows, key=lambda r: (order[r["status"]], r["name"]))

    def status_of(self, system_id: str) -> SystemStatus | None:
        if system_id in self._providers:
            return "active"
        for e in self._planned:
            if e["id"] == system_id:
                return e["status"]
        return None

    def load_planned_yaml(self, path: str) -> int:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        n = 0
        for e in data.get("systems", []):
            if e.get("enabled"):
                continue
            self.register_planned(
                {
                    "id": e["id"],
                    "name": e["name"],
                    "region": e.get("region", "east"),
                    "category": e.get("category", []),
                    "status": e.get("status", "planned"),
                    "strengths": e.get("strengths", ""),
                    "limitations": e.get("limitations", ""),
                    "note": e.get("note", ""),
                }
            )
            n += 1
        return n
