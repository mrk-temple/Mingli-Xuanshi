"""塔罗引擎包装 —— 复用 xuan-shu/scripts/tarot.py 的牌库与抽牌逻辑。"""
from __future__ import annotations

import random
from typing import Any

from mingli.engines.loader import load_engine


def tarot_calculate(
    *,
    spread: str = "three",
    seed: int | None = None,
    no_reversals: bool = False,
) -> dict[str, Any]:
    """塔罗抽牌 → 结构化结果。洗牌与正逆位判定与 tarot.py 完全一致。

    注意：tarot.py 的逆位判定发生在洗牌之后（同一 rng 流），
    本包装保持相同顺序以与 CLI --seed 复现结果一致。
    """
    tr = load_engine("tarot")
    if spread not in tr.SPREADS:
        raise ValueError(f"未知牌阵: {spread}（可选 {sorted(tr.SPREADS)}）")

    deck = tr.build_deck()
    positions = tr.SPREADS[spread]
    n = len(positions)
    rng = random.Random(seed) if seed is not None else random.SystemRandom()

    for i in range(len(deck) - 1, 0, -1):
        j = rng.randrange(i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    picked = deck[:n]
    rand_src = f"seed={seed}" if seed is not None else "secrets 密码学随机"

    cards = []
    for (label, meaning), card in zip(positions, picked, strict=True):
        cid, zh, en, group, elem, up, rev = card
        if no_reversals:
            orient, hint = "正位", up
        else:
            orient, hint = ("逆位", rev) if rng.random() < 0.5 else ("正位", up)
        cards.append({
            "position": label,
            "positionMeaning": meaning,
            "cardId": cid,
            "nameZh": zh,
            "nameEn": en,
            "orientation": orient,
            "reversed": orient == "逆位",
            "group": group,
            "element": elem if elem != "—" else None,
            "keywords": hint,
        })

    return {
        "spread": spread,
        "spreadName": {"single": "单张", "three": "三张（过去-现在-未来）",
                       "celtic": "凯尔特十字"}.get(spread, spread),
        "randomSource": rand_src,
        "seedReproducible": seed is not None,
        "noReversals": no_reversals,
        "cards": cards,
    }
