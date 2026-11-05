"""大六壬引擎包装 —— 复用 xuan-shu/scripts/daliuren.py 的起课逻辑。"""
from __future__ import annotations

from typing import Any

from mingli.engines.loader import load_engine


def daliuren_calculate(
    *,
    datetime_input: list[int] | None = None,
    manual: tuple[str, str, str] | None = None,
) -> dict[str, Any]:
    """大六壬起课 → 结构化结果。

    daliuren.py 的核心排盘逻辑在 main() 内联，本包装按同一算法顺序
    调用其模块级数据表与函数复现（天地盘→四课→九宗门→贵神），
    并保留课体与流派注记。
    """
    dlr = load_engine("daliuren")
    common = load_engine("common")

    note = ""
    if datetime_input is not None:
        y, m, d, h = datetime_input
        if not (1900 <= y <= 2100) or not (0 <= h <= 23):
            raise ValueError("输入越界：年份 1900-2100，时 0-23")
        dgan, dzhi = common.day_ganzhi(y, m, d)
        hz = common.hour_zhi(h)
        L = common.solar_longitude(float(common.jdn(y, m, d)) + h / 24.0)
        yj, yj_name = dlr.yuejiang_by_longitude(L)
        src = f"公历 {y}年{m}月{d}日{h}时"
    else:
        if not manual:
            raise ValueError("必须提供公历时间或手工三要素")
        gz, hz_s, yj_s = manual
        if (gz[0] not in common.TIAN_GAN or gz[1] not in common.DI_ZHI
                or hz_s not in common.DI_ZHI or yj_s not in common.DI_ZHI):
            raise ValueError("手工输入格式：日干支(如 甲子) 占时支(如 午) 月将支(如 亥)")
        dgan = common.TIAN_GAN.index(gz[0])
        dzhi = common.DI_ZHI.index(gz[1])
        hz = common.DI_ZHI.index(hz_s)
        yj = common.DI_ZHI.index(yj_s)
        yj_name = dict((common.DI_ZHI[z], n) for _, z, n in dlr.ZHONGQI)[yj_s]
        src = f"手工起课 {gz}日 {hz_s}时 月将{yj_s}（{yj_name}）"

    TIAN_GAN, DI_ZHI = common.TIAN_GAN, common.DI_ZHI
    GAN_WUXING, ZHI_WUXING = common.GAN_WUXING, common.ZHI_WUXING
    KE = common.KE
    day_wx = GAN_WUXING[dgan]
    jg = dlr.JIGONG[TIAN_GAN[dgan]]

    # 天地盘：天盘[x] = (月将 + x - 占时) mod 12
    tp = [(yj + x - hz) % 12 for x in range(12)]

    # 四课
    k1, k2, k3, k4 = tp[jg], tp[tp[jg]], tp[dzhi], tp[tp[dzhi]]
    kes = [("一课", k1, jg), ("二课", k2, k1), ("三课", k3, dzhi), ("四课", k4, k3)]

    def ke_rel(up: int, dn: int) -> str:
        if KE[ZHI_WUXING[dn]] == ZHI_WUXING[up]:
            return "贼"
        if KE[ZHI_WUXING[up]] == ZHI_WUXING[dn]:
            return "克"
        return ""

    rels = [ke_rel(up, dn) for _, up, dn in kes]
    zai = [i for i in range(4) if rels[i] == "贼"]
    ke = [i for i in range(4) if rels[i] == "克"]

    def shehai(up: int, p: int) -> int:
        cnt = 0
        k = (up - p) % 12
        for i in range(1, k):
            if KE[ZHI_WUXING[up]] == ZHI_WUXING[(p + i) % 12]:
                cnt += 1
        return cnt

    def xuchuan(first: int) -> list[int]:
        return [first, tp[first], tp[tp[first]]]

    fuyin = (yj == hz)
    fanyin = (yj == (hz + 6) % 12)
    kt = ""
    chuan: list[int] = []

    if fuyin:
        gk = ke_rel(jg, jg) or (KE[day_wx] == ZHI_WUXING[jg] or KE[ZHI_WUXING[jg]] == day_wx)
        if gk:
            c1 = jg
            kt = "伏吟课（有克发用）"
        else:
            c1 = jg if common.GAN_YINYANG[dgan] == 0 else dzhi
            kt = "伏吟课·自任" if common.GAN_YINYANG[dgan] == 0 else "伏吟课·自信"
        chuan = [c1, dlr.xing_zhuan(c1), dlr.xing_zhuan(dlr.xing_zhuan(c1))]
    elif fanyin:
        if zai or ke:
            if len(zai) == 1:
                chuan = xuchuan(kes[zai[0]][1])
                kt = "返吟课·重审"
            elif len(zai) >= 2:
                chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
                kt = f"返吟课·{kt}"
            elif len(ke) == 1:
                chuan = xuchuan(kes[ke[0]][1])
                kt = "返吟课·元首"
            else:
                chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
                kt = f"返吟课·{kt}"
        else:
            c1 = dlr.YIMA[dzhi]
            chuan = [c1, k3, k1]
            kt = "返吟课（无克取马）"
            note = "返吟无克初传取驿马支本身（通行说；另有取驿马所临上神者，见 daliuren-guide 存疑清单）"
    elif len(zai) == 1:
        chuan = xuchuan(kes[zai[0]][1])
        kt = "重审课"
    elif len(zai) >= 2:
        chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
    elif len(ke) == 1:
        chuan = xuchuan(kes[ke[0]][1])
        kt = "元首课"
    elif len(ke) >= 2:
        chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
    else:
        if jg == dzhi:
            if common.GAN_YINYANG[dgan] == 0:
                c1 = tp[tp[k1]]
            else:
                p = tp.index(k4)
                c1 = (p - 2) % 12
            chuan = [c1, k1, k1]
            kt = "八专课"
            note = "八专日只论上下克、不看遥克（六壬大全卷七）；中末俱取干上神"
        else:
            yao_shen = [i for i in range(4) if KE[ZHI_WUXING[kes[i][1]]] == day_wx]
            yao_ri = [i for i in range(4) if KE[day_wx] == ZHI_WUXING[kes[i][1]]]
            if yao_shen or yao_ri:
                cand = yao_shen if yao_shen else yao_ri
                kt = "遥克课·蒿矢" if yao_shen else "遥克课·弹射"
                bi = [i for i in cand if (kes[i][1] in (0, 2, 4, 6, 8, 10)) == (common.GAN_YINYANG[dgan] == 0)]
                if len(bi) == 1:
                    first = kes[bi[0]][1]
                elif len(bi) == 0:
                    first = kes[cand[0]][1]
                    note = "遥克多课上神俱不比，取先见课"
                else:
                    first = kes[bi[0]][1]
                    note = "遥克多课相比仍两课，取先见课"
                chuan = xuchuan(first)
            elif (k1 == k4) or (k2 == k3):
                if common.GAN_YINYANG[dgan] == 0:
                    c1 = tp[dlr.JIGONG[TIAN_GAN[dlr.WUHE[dgan]]]]
                else:
                    nxt = dzhi
                    for ju in dlr.SANHE:
                        if dzhi in ju:
                            nxt = ju[(ju.index(dzhi) + 1) % 3]
                            break
                    c1 = tp[nxt]
                chuan = [c1, k1, k1]
                kt = "别责课"
            else:
                if common.GAN_YINYANG[dgan] == 0:
                    c1 = tp[9]
                    chuan = [c1, k3, k1]
                    kt = "昴星课·虎视"
                else:
                    p = tp.index(9)
                    chuan = [p, k1, k3]
                    kt = "昴星课·冬蛇掩目"

    # 贵人十二天将
    day_gui, night_gui = dlr.GUIREN[TIAN_GAN[dgan]]
    is_day = hz in (3, 4, 5, 6, 7, 8)
    gui_zhi = day_gui if is_day else night_gui
    gui_pos = tp.index(gui_zhi)
    shun = gui_pos in (11, 0, 1, 2, 3, 4)
    jiang_at: dict[int, str] = {}
    for i, name in enumerate(dlr.TIANJIANG):
        pos = (gui_pos + i) % 12 if shun else (gui_pos - i) % 12
        jiang_at[pos] = name

    empty = common.xunkong(dgan, dzhi)
    qins = [dlr.liuqin_dl(day_wx, ZHI_WUXING[c]) for c in chuan]

    return {
        "qiKeSource": src,
        "dayGanZhi": TIAN_GAN[dgan] + DI_ZHI[dzhi],
        "dayGanWuxing": day_wx,
        "yueJiang": {"name": yj_name, "zhi": DI_ZHI[yj]},
        "zhanShi": DI_ZHI[hz],
        "isDay": is_day,
        "guiRenType": "昼贵" if is_day else "夜贵",
        "xunKong": [DI_ZHI[e] for e in empty],
        "tianDiPan": {
            "diPan": [DI_ZHI[x] for x in range(12)],
            "tianPan": [DI_ZHI[tp[x]] for x in range(12)],
        },
        "siKe": [
            {"name": name, "up": DI_ZHI[up], "upWuxing": ZHI_WUXING[up],
             "down": DI_ZHI[dn], "downWuxing": ZHI_WUXING[dn], "relation": rel}
            for (name, up, dn), rel in zip(kes, rels, strict=True)
        ],
        "keTi": kt,
        "sanChuan": [
            {"label": label, "zhi": DI_ZHI[c], "wuxing": ZHI_WUXING[c], "liuqin": q}
            for label, c, q in zip(["初传", "中传", "末传"], chuan, qins, strict=True)
        ] if chuan else [],
        "tianJiang": {
            "guiZhi": DI_ZHI[gui_zhi], "guiPos": DI_ZHI[gui_pos], "shun": shun,
            "map": [{"zhi": DI_ZHI[x], "jiang": jiang_at.get(x, "")} for x in range(12)],
        },
        "note": note,
    }


def _jiuzongfa(
    zai: list[int], ke: list[int], kes: list[tuple[str, int, int]],
    dgan: int, tp: list[int], shehai,
) -> tuple[list[int], str]:
    """比用/涉害共用（与 daliuren._jiuzongfa 同算法）。返回 (三传, 课体)。"""
    common = load_engine("common")
    cand = zai if zai else ke
    yang = common.GAN_YINYANG[dgan] == 0
    bi = [i for i in cand if (kes[i][1] in (0, 2, 4, 6, 8, 10)) == yang]
    if len(bi) == 1:
        first = kes[bi[0]][1]
        return [first, tp[first], tp[tp[first]]], "知一课"
    group = bi if bi else cand
    scores = [shehai(kes[i][1], kes[i][2]) for i in group]
    mx = max(scores)
    top = [group[i] for i, s in enumerate(scores) if s == mx]
    if len(top) == 1:
        first = kes[top[0]][1]
        return [first, tp[first], tp[tp[first]]], "涉害课"
    for pool, name in ((dlr_meng(), "涉害课·见机"), (dlr_zhong(), "涉害课·察微"), (dlr_ji(), "涉害课·缀瑕")):
        hit = [i for i in top if kes[i][2] in pool]
        if len(hit) == 1:
            first = kes[hit[0]][1]
            return [first, tp[first], tp[tp[first]]], name
        if hit:
            top = hit
    first = kes[top[0]][1]
    return [first, tp[first], tp[tp[first]]], "涉害课"


def _mzh() -> tuple[set[int], set[int], set[int]]:
    dlr = load_engine("daliuren")
    return dlr.MENG, dlr.ZHONG, dlr.JI


def dlr_meng() -> set[int]:
    return _mzh()[0]


def dlr_zhong() -> set[int]:
    return _mzh()[1]


def dlr_ji() -> set[int]:
    return _mzh()[2]
