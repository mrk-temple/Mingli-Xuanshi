"""易经义理引擎 —— 无随机计算；按卦名/爻位检索义理规则。

义理线（yijing-yili.md）的定位是"可独立成知"：概念问答、决策启发、解卦框架。
作为体系接入时 calculate() 接受卦名/问题文本，输出结构化的卦象事实（六爻阴阳、
上下卦），interpret() 走"先判位 → 再察时 → 后看谦"框架并强制出处。
"""
from __future__ import annotations

from typing import Any

from mingli.engines.loader import load_engine


# 六十四卦名 → (上卦先天数, 下卦先天数) 反查表
def _name_to_trigrams() -> dict[str, tuple[int, int]]:
    qg = load_engine("qigua")
    out: dict[str, tuple[int, int]] = {}
    for up in range(1, 9):
        for low in range(1, 9):
            out[qg.gua_name(up, low)] = (up, low)
    return out


def yijing_calculate(*, gua_name: str) -> dict[str, Any]:
    """给定六十四卦名，输出卦象结构化事实（无占筮成分）。"""
    qg = load_engine("qigua")
    table = _name_to_trigrams()
    if gua_name not in table:
        known = "、".join(sorted(table)[:6])
        raise ValueError(f"未知卦名: {gua_name}（须为六十四卦名之一，如 {known}…）")
    up, low = table[gua_name]
    lines = qg.build_lines(up, low)
    iu, il_ = qg.inter_gua(lines)
    return {
        "guaName": gua_name,
        "upper": {"num": up, "name": qg.TRIGRAMS[up][0], "wuxing": qg.TRIGRAMS[up][1],
                  "xiang": _trigram_xiang(qg.TRIGRAMS[up][0])},
        "lower": {"num": low, "name": qg.TRIGRAMS[low][0], "wuxing": qg.TRIGRAMS[low][1],
                  "xiang": _trigram_xiang(qg.TRIGRAMS[low][0])},
        "lines": lines,  # 自下而上 0/1
        "huGua": {"upper": iu, "lower": il_, "name": qg.gua_name(iu, il_)},
    }


_XIANG = {"乾": "健", "坤": "顺", "震": "动", "巽": "入", "坎": "陷", "离": "丽", "艮": "止", "兑": "说"}


def _trigram_xiang(name: str) -> str:
    return _XIANG.get(name, "")
