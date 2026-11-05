"""梅花易数引擎包装 —— 复用 xuan-shu/scripts/qigua.py 的纯函数。"""
from __future__ import annotations

from typing import Any

from mingli.engines.loader import load_engine


def _resolve_lunar(y: int, m: int, d: int, h: int) -> tuple[int, int, int, int]:
    """公历 → 农历四数（年支序 月 日 时辰序）。依赖 lunar_python，与 qigua.py --solar 一致。"""
    try:
        from lunar_python import Solar
    except ImportError as e:
        raise RuntimeError("缺少依赖 lunar_python：请 pip install lunar_python，或改用农历输入") from e
    solar = Solar.fromYmdHms(y, m, d, h, 0, 0)
    lunar = solar.getLunar()
    yz = lunar.getYearZhiIndex() + 1
    lm = lunar.getMonth()
    if lm < 0:
        lm = -lm  # 闰月按同月数计（邵雍法惯例）
    hz = lunar.getTimeZhiIndex() + 1
    return yz, lm, lunar.getDay(), hz


def meihua_calculate(
    *,
    numbers: list[int] | None = None,
    lunar: list[int] | None = None,
    solar: list[int] | None = None,
) -> dict[str, Any]:
    """梅花起卦 → 结构化结果。算法与 qigua.py 完全一致。"""
    qg = load_engine("qigua")
    if numbers is not None:
        nums = numbers
        if len(nums) not in (2, 3):
            raise ValueError("报数起卦需要 2 或 3 个数")
        upper = qg.mod8(nums[0])
        lower = qg.mod8(nums[1])
        moving = qg.mod6(nums[2]) if len(nums) == 3 else qg.mod6(nums[0] + nums[1])
        src = f"报数起卦 {nums}"
        mode = "numbers"
    elif solar is not None:
        if len(solar) != 4:
            raise ValueError("公历起卦需要 年 月 日 时 四个数")
        y, m, d, h = _resolve_lunar(*solar)
        base = y + m + d
        upper = qg.mod8(base)
        lower = qg.mod8(base + h)
        moving = qg.mod6(base + h)
        src = f"公历 {solar} → 农历数(年支序{y} 月{m} 日{d} 时辰序{h})"
        mode = "solar"
    else:
        if not lunar or len(lunar) != 4:
            raise ValueError("农历起卦需要 年支数 月 日 时辰数")
        y, m, d, h = lunar
        base = y + m + d
        upper = qg.mod8(base)
        lower = qg.mod8(base + h)
        moving = qg.mod6(base + h)
        src = f"农历 年支数{y} 月{m} 日{d} 时辰数{h}"
        mode = "lunar"

    lines = qg.build_lines(upper, lower)
    iu, il_ = qg.inter_gua(lines)
    cu, cl_ = qg.change_gua(lines, moving)
    body, use = qg.ti_yong(moving, upper, lower)
    body_elem = qg.TRIGRAMS[body][1]
    use_elem = qg.TRIGRAMS[use][1]

    return {
        "qiGuaSource": src,
        "mode": mode,
        "benGua": {"upper": upper, "lower": lower,
                   "upperName": qg.TRIGRAMS[upper][0], "lowerName": qg.TRIGRAMS[lower][0],
                   "name": qg.gua_name(upper, lower)},
        "huGua": {"name": qg.gua_name(iu, il_), "upper": iu, "lower": il_,
                  "upperWuxing": qg.TRIGRAMS[iu][1], "lowerWuxing": qg.TRIGRAMS[il_][1]},
        "bianGua": {"name": qg.gua_name(cu, cl_), "upper": cu, "lower": cl_,
                    "upperWuxing": qg.TRIGRAMS[cu][1], "lowerWuxing": qg.TRIGRAMS[cl_][1]},
        "movingLine": moving,
        "tiYong": {
            "body": {"trigram": qg.TRIGRAMS[body][0], "wuxing": body_elem},
            "use": {"trigram": qg.TRIGRAMS[use][0], "wuxing": use_elem},
            "shengKe": qg.shengke(body_elem, use_elem),
        },
    }
