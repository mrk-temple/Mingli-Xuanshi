"""会话持久化 —— JSON 文件存储（design.md §5.3）。

每 session 一个 JSON 文件，含完整 question/calculation/interpretation/disclaimer，
保证历史记录可复查、可追溯（第十原则）。存储目录默认 ./data/sessions。
"""
from __future__ import annotations

import contextlib
import glob
import json
import os

from mingli.core.models import (
    ChartProfile,
    ChatThread,
    DivinationSession,
    Experiment,
)

_DATA_DIR = os.environ.get("MINGLI_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")
EXPERIMENTS_DIR = os.path.join(_DATA_DIR, "experiments")
PROFILES_DIR = os.path.join(_DATA_DIR, "profiles")
CHATS_DIR = os.path.join(_DATA_DIR, "chats")


def _ensure(d: str) -> None:
    os.makedirs(d, exist_ok=True)


class SessionStore:
    def __init__(self, root: str | None = None) -> None:
        self.root = root or SESSIONS_DIR
        _ensure(self.root)

    def save(self, session: DivinationSession) -> str:
        path = os.path.join(self.root, f"{session.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, session_id: str) -> DivinationSession:
        path = os.path.join(self.root, f"{session_id}.json")
        with open(path, encoding="utf-8") as f:
            return DivinationSession.model_validate(json.load(f))

    def list_all(self) -> list[DivinationSession]:
        """按创建时间倒序。"""
        out: list[DivinationSession] = []
        for path in sorted(glob.glob(os.path.join(self.root, "*.json")), reverse=True):
            try:
                with open(path, encoding="utf-8") as f:
                    out.append(DivinationSession.model_validate(json.load(f)))
            except (json.JSONDecodeError, ValueError):
                continue  # 损坏文件跳过，不阻塞列表
        return sorted(out, key=lambda s: s.createdAt, reverse=True)


class ExperimentStore:
    def __init__(self, root: str | None = None) -> None:
        self.root = root or EXPERIMENTS_DIR
        _ensure(self.root)

    def save(self, exp: Experiment) -> str:
        path = os.path.join(self.root, f"{exp.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(exp.model_dump(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, exp_id: str) -> Experiment:
        path = os.path.join(self.root, f"{exp_id}.json")
        with open(path, encoding="utf-8") as f:
            return Experiment.model_validate(json.load(f))

    def list_all(self) -> list[Experiment]:
        out: list[Experiment] = []
        for path in glob.glob(os.path.join(self.root, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    out.append(Experiment.model_validate(json.load(f)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(out, key=lambda e: e.lockedAt, reverse=True)

    def stats(self) -> dict[str, object]:
        """命中统计（design.md §9.2）。只统计已判定实验；样本量如实展示。

        注意：这是用户个人样本统计，不代表体系有效性（UI 必须带此声明）。
        """
        exps = [e for e in self.list_all() if e.verdict is not None]
        n = len(exps)
        counts: dict[str, int] = {}
        by_system: dict[str, dict[str, int]] = {}
        for e in exps:
            verdict = str(e.verdict)   # 已过滤 None；转 str 供计数键用
            counts[verdict] = counts.get(verdict, 0) + 1
            slot = by_system.setdefault(e.systemId, {})
            slot[verdict] = slot.get(verdict, 0) + 1
        return {
            "n": n,
            "verdictCounts": {v: counts.get(v, 0) for v in [
                "exact-hit", "partial-hit", "direction-hit", "timing-hit", "miss", "ambiguous", "no-outcome"]},
            "bySystem": by_system,
            "note": "以上为个人实验样本，不构成对任何术数体系有效性的科学评价。",
        }


class ProfileStore:
    """个人命盘库（ChartProfile 的 JSON 存储），与 session/experiment 同款约定。"""

    def __init__(self, root: str | None = None) -> None:
        self.root = root or PROFILES_DIR
        _ensure(self.root)

    def save(self, p: ChartProfile) -> str:
        path = os.path.join(self.root, f"{p.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p.model_dump(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, profile_id: str) -> ChartProfile:
        path = os.path.join(self.root, f"{profile_id}.json")
        with open(path, encoding="utf-8") as f:
            return ChartProfile.model_validate(json.load(f))

    def list_all(self) -> list[ChartProfile]:
        out: list[ChartProfile] = []
        for path in glob.glob(os.path.join(self.root, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    out.append(ChartProfile.model_validate(json.load(f)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(out, key=lambda p: p.createdAt, reverse=True)

    def delete(self, profile_id: str) -> None:
        path = os.path.join(self.root, f"{profile_id}.json")
        with contextlib.suppress(OSError):
            os.remove(path)


class ChatStore:
    """玄师对话线程（ChatThread 的 JSON 存储）。一个 session 可有多个讨论串。"""

    def __init__(self, root: str | None = None) -> None:
        self.root = root or CHATS_DIR
        _ensure(self.root)

    def save(self, t: ChatThread) -> str:
        path = os.path.join(self.root, f"{t.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(t.model_dump(), f, ensure_ascii=False, indent=2)
        return path

    def load(self, thread_id: str) -> ChatThread:
        path = os.path.join(self.root, f"{thread_id}.json")
        with open(path, encoding="utf-8") as f:
            return ChatThread.model_validate(json.load(f))

    def list_all(self) -> list[ChatThread]:
        out: list[ChatThread] = []
        for path in glob.glob(os.path.join(self.root, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    out.append(ChatThread.model_validate(json.load(f)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(out, key=lambda t: t.createdAt, reverse=True)

    def for_session(self, session_id: str) -> list[ChatThread]:
        return [t for t in self.list_all() if t.sessionId == session_id]

    def delete(self, thread_id: str) -> None:
        path = os.path.join(self.root, f"{thread_id}.json")
        with contextlib.suppress(OSError):
            os.remove(path)
