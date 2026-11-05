"""paipan 引擎包装 —— 八字排盘（复用 xuan-shu/scripts/paipan.py 的全部公式）。

策略：脚本 main() 是 argparse+print 流程，本包装直接调用其模块级函数
（term_time_after / ten_god / da_yun / jd_to_date 等）组装结构化 dict，
并用 capture_cli() 复跑一次 CLI 拿原样文本作 rawText——两条路径同一份代码。
"""
from __future__ import annotations

import contextlib
import io
import math
from typing import Any

from mingli.engines.loader import load_engine


def capture_cli(argv: list[str]) -> tuple[str, int]:
    """以子进程等价方式运行脚本 CLI，捕获 stdout 与退出码。

    用 runpy 直接执行 __main__（与命令行运行同一入口），stdout 重定向捕获；
    SystemExit(0) 视为成功，其他退出码如实返回。
    """
    import sys as _sys

    old_argv = _sys.argv
    buf = io.StringIO()
    code = 0
    _sys.argv = argv
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            mod = load_engine(argv[0].rsplit("/", 1)[-1].removesuffix(".py"))
            # 直接调用 main；argparse 错误会 SystemExit(2)
            try:
                mod.main()
            except SystemExit as e:  # noqa: TRY302 - CLI 语义保留
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        _sys.argv = old_argv
    return buf.getvalue(), code


def bazi_calculate(
    year: int, month: int, day: int, hour: int,
    gender: str | None = None,
    today: tuple[int, int, int] | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """八字排盘 → 结构化结果。公式全部来自 paipan.py 模块级函数。"""
    pp = load_engine("paipan")
    common = load_engine("common")

    if not (1900 <= year <= 2100) or not (1 <= month <= 12) or not (1 <= day <= 31) or not (0 <= hour <= 23):
        raise ValueError("输入越界：年份须在 1900-2100，月 1-12，日 1-31，时 0-23")

    # 真实日历校验：jdn() 对越界日（如 2 月 31 日）会静默滚动到下月，
    # 排出不存在的日期的盘——必须在此拦截（仅拒收，不改变合法输入的任何输出）。
    import datetime as _dt
    try:
        _dt.date(year, month, day)
    except ValueError:
        raise ValueError(f"日期不存在：{year}-{month:02d}-{day:02d}") from None

    warnings: list[str] = []
    jd = float(pp.jdn(year, month, day)) + (hour / 24.0)
    fix_min = 0.0
    if longitude is not None:
        n = pp.jdn(year, month, day) - pp.jdn(year, 1, 1) + 1
        b = 2 * math.pi * (n - 81) / 364
        eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        fix_min = (longitude - 120.0) * 4 + eot
        jd += fix_min / (24 * 60)

    # 年柱（立春分界）
    lichun_this = pp.term_time_after(year, 315.0)
    if jd < lichun_this:
        year_gan = (year - 1 + 6) % 10
        year_zhi = (year - 1 - 4) % 12
    else:
        year_gan = (year + 6) % 10
        year_zhi = (year - 4) % 12

    # 月柱（十二节）
    terms = [pp.term_time_after(year, lam) for lam in pp.JIE_LAMBDA]
    if jd < terms[0]:
        xiaohan_this = pp.term_time_after(year, 285.0)
        if jd < xiaohan_this:
            month_zhi, offset = 0, 10
        else:
            month_zhi, offset = 1, 11
        month_gan = (pp.HUTUN[year_gan % 5] + offset) % 10
    else:
        lichun_next = pp.term_time_after(year + 1, 315.0)
        month_zhi = month_gan = -1
        for i in range(12):
            nxt = terms[i + 1] if i < 11 else lichun_next
            if terms[i] <= jd < nxt:
                month_zhi = pp.JIE_ZHI[i]
                month_gan = (pp.HUTUN[year_gan % 5] + i) % 10
                break
        assert month_gan >= 0  # noqa: S101 - 十二节区间必覆盖年内时刻

    # 日柱 / 时柱
    day_seq = (int(pp.jdn(year, month, day)) + 49) % 60
    day_gan, day_zhi = day_seq % 10, day_seq % 12
    hour_zhi_idx = ((hour + 1) // 2) % 12
    hour_gan = (pp.SHUTUN[day_gan % 5] + hour_zhi_idx) % 10

    gan6 = [year_gan, month_gan, day_gan, hour_gan]
    zhi6 = [year_zhi, month_zhi, day_zhi, hour_zhi_idx]
    pillars = ["year", "month", "day", "hour"]
    pillar_cn = ["年柱", "月柱", "日柱", "时柱"]

    columns = []
    for i in range(4):
        tg = "日主" if i == 2 else pp.ten_god(day_gan, gan6[i])
        columns.append({
            "pillar": pillars[i],
            "pillarCn": pillar_cn[i],
            "gan": pp.TIAN_GAN[gan6[i]],
            "ganWuxing": pp.GAN_WUXING[gan6[i]],
            "ganYinyang": "阳" if pp.GAN_YINYANG[gan6[i]] == 0 else "阴",
            "shiShen": tg,
            "zhi": pp.DI_ZHI[zhi6[i]],
            "zhiWuxing": pp.ZHI_WUXING[zhi6[i]],
            "zhiYinyang": "阳" if pp.ZHI_YINYANG[zhi6[i]] == 0 else "阴",
            "cangGan": pp.CANG_GAN[pp.DI_ZHI[zhi6[i]]],
        })

    from collections import Counter
    c_main = Counter(pp.GAN_WUXING[g] for g in gan6)
    c_main.update(pp.ZHI_WUXING[z] for z in zhi6)
    c_hidden = Counter(pp.GAN_WUXING[g] for g in gan6)
    for z in zhi6:
        c_hidden.update(pp.GAN_WUXING[pp.TIAN_GAN.index(ch)] for ch in pp.CANG_GAN[pp.DI_ZHI[z]])

    # 年柱纳音：60 甲子序号//2 查 30 纳音。与修复后的 paipan.py 同式
    # （原式在癸年越界且多数干支算错，见 paipan.py 内注释）。
    nayin_seq = ((year_gan * 6 - year_zhi * 5) % 60) // 2

    result: dict[str, Any] = {
        "solar": {"year": year, "month": month, "day": day, "hour": hour},
        "trueSolarTimeApplied": longitude is not None,
        "longitude": longitude,
        "eotMinutes": round(fix_min, 1),
        "siZhu": "".join(pp.TIAN_GAN[g] for g in gan6) + " " + "".join(pp.DI_ZHI[z] for z in zhi6),
        "columns": columns,
        "nayinYear": pp.NAYIN[nayin_seq],
        "wuxingMain": {w: c_main.get(w, 0) for w in ["木", "火", "土", "金", "水"]},
        "wuxingHidden": {w: c_hidden.get(w, 0) for w in ["木", "火", "土", "金", "水"]},
        "yueLing": {
            "zhi": pp.DI_ZHI[month_zhi],
            "jieIndex": common.JIE_ZHI.index(month_zhi) + 1,
            "dangLingWuxing": pp.ZHI_WUXING[month_zhi],
        },
    }

    # 大运
    if gender:
        forward, yun_years, yun_months, qiyun_jd, steps = pp.da_yun(
            year_gan, month_gan, month_zhi, jd, gender, terms)
        qy, qm, _ = pp.jd_to_date(qiyun_jd)
        today_jd = float(pp.jdn(*today)) + 0.5 if today else None
        dayun = []
        for i, (g, z) in enumerate(steps):
            s0 = qiyun_jd + i * 10 * 365.25
            s1 = s0 + 10 * 365.25
            y0, m0, _ = pp.jd_to_date(s0)
            y1, m1, _ = pp.jd_to_date(s1)
            dayun.append({
                "index": i + 1,
                "ganZhi": pp.TIAN_GAN[g] + pp.DI_ZHI[z],
                "startYm": f"{y0}.{m0}",
                "endYm": f"{y1}.{m1}",
                "current": bool(today_jd and s0 <= today_jd < s1),
            })
        result["daYun"] = {
            "gender": gender,
            "forward": forward,
            "qiyunYears": yun_years,
            "qiyunMonths": yun_months,
            "qiyunDate": f"{qy}-{qm:02d}",
            "steps": dayun,
        }
    else:
        result["daYun"] = None

    # 节气边界提醒（阈值同 config.yaml 默认 1 天）
    tol = 1.0
    jie_names = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                 "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
    for i, t in enumerate(terms):
        if abs(jd - t) <= tol:
            warnings.append(f"出生时刻距{jie_names[i]}节 {abs(jd - t) * 24:.0f} 小时，边界请复核时辰")
    if abs(jd - lichun_this) <= tol:
        warnings.append(f"出生时刻距立春 {abs(jd - lichun_this) * 24:.0f} 小时，年柱边界请复核")

    result["warnings"] = warnings
    return result
