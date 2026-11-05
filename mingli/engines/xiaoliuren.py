"""小六壬引擎包装 —— 复用 xuan-shu/scripts/xiaoliuren.py 的宫位表与算法。"""
from __future__ import annotations

from typing import Any

from mingli.engines.loader import load_engine


def _resolve_lunar(y: int, m: int, d: int, h: int) -> tuple[int, int, int]:
    """公历 → 农历三数（与 xiaoliuren.py lunar_from_solar 一致）。"""
    try:
        from lunar_python import Solar
    except ImportError as e:
        raise RuntimeError("缺少依赖 lunar_python：请 pip install lunar_python，或自报农历三数") from e
    solar = Solar.fromYmdHms(y, m, d, h, 0, 0)
    lunar = solar.getLunar()
    lm = lunar.getMonth()
    if lm < 0:
        lm = -lm
    return lm, lunar.getDay(), lunar.getTimeZhiIndex() + 1


def xiaoliuren_calculate(
    *,
    numbers: list[int] | None = None,
    lunar: list[int] | None = None,
    solar: list[int] | None = None,
    sum_mode: bool = False,
) -> dict[str, Any]:
    """小六壬起课 → 结构化结果。算法与 xiaoliuren.py 完全一致。"""
    xlr = load_engine("xiaoliuren")
    if solar is not None:
        if len(solar) != 4:
            raise ValueError("公历起课需要 年 月 日 时 四个数")
        m, d, h = _resolve_lunar(*solar)
        src = f"公历 {solar} → 农历 {m}月{d}日 时辰序{h}"
        mode = "solar"
    elif lunar is not None or numbers is not None:
        vals = lunar if lunar is not None else numbers
        assert vals is not None and len(vals) == 3  # noqa: S101 - 上方分支已限定
        m, d, h = vals
        if not (1 <= m <= 12 and 1 <= d <= 30 and 1 <= h <= 12):
            raise ValueError("输入越界：月 1-12，日 1-30，时辰 1-12（子=1…亥=12）")
        src = f"农历 {m}月{d}日 时辰序{h}" if lunar is not None else f"报数 {m} {d} {h}"
        mode = "lunar" if lunar is not None else "numbers"
    else:
        raise ValueError("必须提供起课输入：numbers / lunar / solar")

    month_p = (m - 1) % 6 + 1
    day_p = (m + d - 2) % 6 + 1
    final_p = xlr.palace(m, d, h, sum_mode)

    def palace_info(idx: int) -> dict[str, Any]:
        name, finger, zhi, shen, wx, level, nums_str, duanci = xlr.PALACES[idx]
        return {"name": name, "finger": finger, "zhi": zhi, "liushen": shen,
                "wuxing": wx, "jixiong": level, "zhuShu": nums_str, "duanci": duanci}

    return {
        "qiKeSource": src,
        "mode": mode,
        "algorithm": "总数累加法变体" if sum_mode else "古法（月上起日、日上起时）",
        "sumMode": sum_mode,
        "yueGong": palace_info(month_p),
        "riGong": palace_info(day_p),
        "duanGong": palace_info(final_p),
    }
