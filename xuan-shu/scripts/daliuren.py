#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daliuren.py —— 大六壬起课排盘（确定性算法部分：天地盘/四课/三传/贵神）。

用法:
    python3 scripts/daliuren.py --datetime 2026 8 11 15        # 公历起课时间（日干支/占时/月将自动计算）
    python3 scripts/daliuren.py --manual 甲子 午 亥            # 手工起课：日干支 占时支 月将支（古籍课例复算用）
    python3 scripts/daliuren.py --manual 乙丑 午 亥

实现范围（规则依据 references/daliuren-guide.md 引《六壬大全》等）:
    日干支/时支/月将（公历模式自动）→ 天地盘（月将加占时）→ 四课（十干寄宫）→
    九宗门发三传（贼克/比用/涉害/遥克/昴星/别责/八专/伏吟/返吟）→
    贵人十二天将（昼贵夜贵+顺逆布）→ 三传六亲/遁干/旬空 → 课体

存疑处已按主流实现并在输出/注释标注（涉害计数流派、八专中末传、返吟驿马取法、
贵人昼夜分界），详见 references/daliuren-guide.md 存疑清单——断课时不要超出本脚本输出。
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (TIAN_GAN, DI_ZHI, GAN_WUXING, ZHI_WUXING, GAN_YINYANG,
                    SHENG, KE, jdn, day_ganzhi, hour_zhi, xunkong, solar_longitude)

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 十干寄宫（地支序 0-11）
JIGONG = {"甲": 2, "乙": 4, "丙": 5, "丁": 7, "戊": 5, "己": 7, "庚": 8, "辛": 10, "壬": 11, "癸": 1}
# 十二神将（中气黄经 → 月将）：(黄经, 月将支序, 将名)
ZHONGQI = [(0, 10, "河魁"), (30, 9, "从魁"), (60, 8, "传送"), (90, 7, "小吉"),
           (120, 6, "胜光"), (150, 5, "太乙"), (180, 4, "天罡"), (210, 3, "太冲"),
           (240, 2, "功曹"), (270, 1, "大吉"), (300, 0, "神后"), (330, 11, "登明")]
# 贵人：日干 → (昼贵支序, 夜贵支序)
GUIREN = {"甲": (1, 7), "戊": (1, 7), "庚": (1, 7), "乙": (0, 8), "己": (0, 8),
          "丙": (11, 9), "丁": (11, 9), "壬": (3, 5), "癸": (3, 5), "辛": (6, 2)}
# 十二天将顺行顺序
TIANJIANG = ["贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
             "天空", "白虎", "太常", "玄武", "太阴", "天后"]
# 三刑（自刑取本身）
XING = {2: 5, 5: 8, 8: 2, 1: 10, 10: 7, 7: 1, 0: 3, 3: 0, 4: 4, 6: 6, 9: 9, 11: 11}
# 三合局（顺行序）与驿马
SANHE = [[8, 0, 4], [2, 6, 10], [5, 9, 1], [11, 3, 7]]  # 申子辰 / 寅午戌 / 巳酉丑 / 亥卯未
YIMA = {8: 2, 0: 2, 4: 2, 2: 8, 6: 8, 10: 8, 5: 11, 9: 11, 1: 11, 11: 5, 3: 5, 7: 5}
MENG, ZHONG, JI = {2, 8, 5, 11}, {0, 6, 3, 9}, {4, 10, 1, 7}  # 四孟/四仲/四季
# 五合：干序 → 合干序
WUHE = {0: 5, 5: 0, 1: 6, 6: 1, 2: 7, 7: 2, 3: 8, 8: 3, 4: 9, 9: 4}


def yuejiang_by_longitude(L):
    """太阳视黄经 → 月将（中气分界）。"""
    Ln = L % 360.0
    for lam, zhi, name in reversed(ZHONGQI):
        if Ln >= lam - 1e-9:
            return zhi, name
    return ZHONGQI[-1][1], ZHONGQI[-1][2]  # 理论不可达


def liuqin_dl(day_wx, other_wx):
    """六壬六亲（以日干五行为"我"）。"""
    if other_wx == day_wx:
        return "兄弟"
    if SHENG[other_wx] == day_wx:
        return "父母"
    if SHENG[day_wx] == other_wx:
        return "子孙"
    if KE[other_wx] == day_wx:
        return "官鬼"
    return "妻财"


def xing_zhuan(chuan):
    """中末传刑转：中=刑(初)，末=刑(中)。"""
    return XING[chuan]


def main():
    ap = argparse.ArgumentParser(description="大六壬起课排盘（确定性算法）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--datetime", nargs=4, type=int, metavar=("Y", "M", "D", "H"),
                   help="公历起课时间（年月日时，24 小时制）")
    g.add_argument("--manual", nargs=3, metavar=("GANZHI", "HOUR_ZHI", "YUEJIANG"),
                   help="手工起课：日干支(如 甲子) 占时支 月将支")
    args = ap.parse_args()

    if args.datetime:
        y, m, d, h = args.datetime
        if not (1900 <= y <= 2100) or not (0 <= h <= 23):
            print("输入越界：年份 1900-2100，时 0-23", file=sys.stderr)
            sys.exit(1)
        dgan, dzhi = day_ganzhi(y, m, d)
        hz = hour_zhi(h)
        L = solar_longitude(float(jdn(y, m, d)) + h / 24.0)
        yj, yj_name = yuejiang_by_longitude(L)
        src = f"公历 {y}年{m}月{d}日{h}时"
    else:
        gz, hz_s, yj_s = args.manual
        if gz[0] not in TIAN_GAN or gz[1] not in DI_ZHI or hz_s not in DI_ZHI or yj_s not in DI_ZHI:
            print("手工输入格式：日干支(如 甲子) 占时支(如 午) 月将支(如 亥)", file=sys.stderr)
            sys.exit(1)
        dgan, dzhi = TIAN_GAN.index(gz[0]), DI_ZHI.index(gz[1])
        hz = DI_ZHI.index(hz_s)
        yj = DI_ZHI.index(yj_s)
        yj_name = dict((DI_ZHI[z], n) for _, z, n in ZHONGQI)[yj_s]
        src = f"手工起课 {gz}日 {hz_s}时 月将{yj_s}（{yj_name}）"

    dgan_c = TIAN_GAN[dgan]
    dzhi_c = DI_ZHI[dzhi]
    day_wx = GAN_WUXING[dgan]

    # ---- 天地盘：天盘[x] = (月将 + x - 占时) mod 12 ----
    tp = [(yj + x - hz) % 12 for x in range(12)]

    # ---- 四课 ----
    jg = JIGONG[dgan_c]
    k1 = tp[jg]           # 干上神
    k2 = tp[k1]           # 干阴神
    k3 = tp[dzhi]         # 支上神
    k4 = tp[k3]           # 支阴神
    kes = [("一课", k1, jg), ("二课", k2, k1), ("三课", k3, dzhi), ("四课", k4, k3)]

    def ke_rel(up, down):
        """返回 '贼'(下贼上) / '克'(上克下) / ''"""
        if KE[ZHI_WUXING[down]] == ZHI_WUXING[up]:
            return "贼"
        if KE[ZHI_WUXING[up]] == ZHI_WUXING[down]:
            return "克"
        return ""

    rels = [ke_rel(up, dn) for _, up, dn in kes]
    zai = [i for i in range(4) if rels[i] == "贼"]
    ke = [i for i in range(4) if rels[i] == "克"]

    # ---- 九宗门发三传 ----
    fuyin = (yj == hz)
    fanyin = (yj == (hz + 6) % 12)
    kt = ""        # 课体
    chuan = []     # 三传（地支序）
    note = ""      # 存疑/流派注记

    # 涉害数（主流流派 a）：上神临地盘位 P，顺行归本家，数途中被上神所克之地支
    def shehai(up, p):
        cnt = 0
        k = (up - p) % 12
        for i in range(1, k):
            if KE[ZHI_WUXING[up]] == ZHI_WUXING[(p + i) % 12]:
                cnt += 1
        return cnt

    def xuchuan(first):
        return [first, tp[first], tp[tp[first]]]

    if fuyin:
        # 伏吟：天盘[x]=x。有克(干与寄宫相克)用克发传；无克阳日取干上、阴日取支上；中末取刑
        gk = ke_rel(jg, jg) or (KE[day_wx] == ZHI_WUXING[jg] or KE[ZHI_WUXING[jg]] == day_wx)
        if gk:
            c1 = jg
            kt = "伏吟课（有克发用）"
        else:
            c1 = jg if GAN_YINYANG[dgan] == 0 else dzhi
            kt = "伏吟课·自任" if GAN_YINYANG[dgan] == 0 else "伏吟课·自信"
        c2, c3 = xing_zhuan(c1), xing_zhuan(xing_zhuan(c1))
        chuan = [c1, c2, c3]
    elif fanyin:
        # 返吟：天盘[x]=冲(x)。有克按贼克/比用/涉害；无克取驿马，中=支上，末=干上
        zai = [i for i in range(4) if rels[i] == "贼"]
        ke = [i for i in range(4) if rels[i] == "克"]
        if zai or ke:
            if len(zai) == 1:
                chuan = xuchuan(kes[zai[0]][1]); kt = "返吟课·重审"
            elif len(zai) >= 2:
                chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
                kt = f"返吟课·{kt}"
            elif len(ke) == 1:
                chuan = xuchuan(kes[ke[0]][1]); kt = "返吟课·元首"
            else:
                chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
                kt = f"返吟课·{kt}"
        else:
            c1 = YIMA[dzhi]  # 驿马支本身（主流；流派分歧见 guide 存疑清单）
            chuan = [c1, k3, k1]
            kt = "返吟课（无克取马）"
            note = "返吟无克初传取驿马支本身（通行说；另有取驿马所临上神者，见 daliuren-guide 存疑清单）"
    elif len(zai) == 1:
        # 恰一课下贼上 → 重审（贼课优先于克课，无论是否另有上克下）
        chuan = xuchuan(kes[zai[0]][1]); kt = "重审课"
    elif len(zai) >= 2:
        # 下贼上多课 → 比用/涉害（先于上克下）
        chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
    elif len(ke) == 1:
        chuan = xuchuan(kes[ke[0]][1]); kt = "元首课"
    elif len(ke) >= 2:
        chuan, kt = _jiuzongfa(zai, ke, kes, dgan, tp, shehai)
    else:
        # 无上下克 → 八专（先于遥克，五日：癸丑甲寅丁未己未庚申）→ 遥克 → 别责 → 昴星
        if jg == dzhi:
            # 八专：干支同位（日干寄宫=日支），四课只得两课（干上=支上、干阴=支阴），只论上下克、不看遥克
            if GAN_YINYANG[dgan] == 0:
                c1 = tp[tp[k1]]  # 阳日：干之阳神（干上）连身顺数第三位
            else:
                p = tp.index(k4)
                c1 = (p - 2) % 12  # 阴日：支之阴神（第四课上神）连身逆数第三位
            chuan = [c1, k1, k1]
            kt = "八专课"
            note = "八专日只论上下克、不看遥克（六壬大全卷七）；中末俱取干上神"
        else:
            yao_shen = [i for i in range(4) if KE[ZHI_WUXING[kes[i][1]]] == day_wx]   # 神克日→蒿矢
            yao_ri = [i for i in range(4) if KE[day_wx] == ZHI_WUXING[kes[i][1]]]     # 日克神→弹射
            if yao_shen or yao_ri:
                cand = yao_shen if yao_shen else yao_ri
                kt = "遥克课·蒿矢" if yao_shen else "遥克课·弹射"
                bi = [i for i in cand if (kes[i][1] in (0, 2, 4, 6, 8, 10)) == (GAN_YINYANG[dgan] == 0)]
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
                # 别责：四课不备（一课=四课 或 二课=三课，四课只得三课），无克无遥
                if GAN_YINYANG[dgan] == 0:
                    c1 = tp[JIGONG[TIAN_GAN[WUHE[dgan]]]]  # 阳日：干合神（五合干寄宫）之上神
                else:
                    # 阴日：日支所在三合局"前一位"（顺行下一位：申→子→辰→申 等）之上神
                    for ju in SANHE:
                        if dzhi in ju:
                            nxt = ju[(ju.index(dzhi) + 1) % 3]
                            break
                    c1 = tp[nxt]
                chuan = [c1, k1, k1]
                kt = "别责课"
            else:
                # 昴星：四课无克无遥且课备
                if GAN_YINYANG[dgan] == 0:
                    c1 = tp[9]  # 阳日：地盘酉位之上神（虎视）
                    chuan = [c1, k3, k1]
                    kt = "昴星课·虎视"
                else:
                    p = tp.index(9)  # 阴日：天盘酉所临之地盘支（冬蛇掩目）
                    chuan = [p, k1, k3]
                    kt = "昴星课·冬蛇掩目"

    # ---- 贵人十二天将 ----
    day_gui, night_gui = GUIREN[dgan_c]
    is_day = hz in (3, 4, 5, 6, 7, 8)  # 占时卯至申为昼
    gui_zhi = day_gui if is_day else night_gui
    gui_pos = tp.index(gui_zhi)
    shun = gui_pos in (11, 0, 1, 2, 3, 4)  # 贵临亥至辰顺布，巳至戌逆布
    jiang_at = {}
    for i, name in enumerate(TIANJIANG):
        pos = (gui_pos + i) % 12 if shun else (gui_pos - i) % 12
        jiang_at[pos] = name

    # ---- 输出 ----
    print("大六壬起课结果（由脚本计算，勿人工复算）")
    print(f"起课: {src}")
    print(f"日干支: {dgan_c}{dzhi_c}（日干{dgan_c}·{day_wx}）  月将: {yj_name}({DI_ZHI[yj]})  占时: {DI_ZHI[hz]}时  旬空: "
          f"{DI_ZHI[xunkong(dgan, dzhi)[0]]}{DI_ZHI[xunkong(dgan, dzhi)[1]]}")
    print("天地盘（地盘/天盘）:")
    print("  地盘: " + " ".join(f"{DI_ZHI[x]:<2}" for x in range(12)))
    print("  天盘: " + " ".join(f"{DI_ZHI[tp[x]]:<2}" for x in range(12)))
    print("四课:")
    for (name, up, dn), rel in zip(kes, rels):
        tag = {"贼": "下贼上", "克": "上克下"}.get(rel, "无克")
        print(f"  {name}: {DI_ZHI[up]}（{ZHI_WUXING[up]}）/ {DI_ZHI[dn]}（{ZHI_WUXING[dn]}） → {tag}")
    print(f"课体: {kt}")
    if chuan:
        qins = [liuqin_dl(day_wx, ZHI_WUXING[c]) for c in chuan]
        print("三传:")
        for i, (c, q) in enumerate(zip(chuan, qins)):
            label = ["初传", "中传", "末传"][i]
            print(f"  {label}: {DI_ZHI[c]}（{ZHI_WUXING[c]}·六亲{q}）")
    else:
        print("三传: 未定")
    print(f"贵人十二天将（{('昼贵' if is_day else '夜贵')}·{DI_ZHI[gui_zhi]}临地盘{DI_ZHI[gui_pos]}·{'顺' if shun else '逆'}布）:")
    print("  " + " ".join(f"{DI_ZHI[x]}:{jiang_at[x]}" for x in range(12)))
    if note:
        print(f"[注] {note}")
    print("[注] 断课规则（三传吉凶/课体主题/六亲取用）见 references/daliuren-guide.md")


def _jiuzongfa(zai, ke, kes, dgan, tp, shehai):
    """比用/涉害共用：候选课 → 取与日干相比者 → 涉害深浅 → 孟仲季。返回 (三传, 课体)。"""
    cand = zai if zai else ke
    yang = GAN_YINYANG[dgan] == 0
    bi = [i for i in cand if (kes[i][1] in (0, 2, 4, 6, 8, 10)) == yang]
    if len(bi) == 1:
        first = kes[bi[0]][1]
        return [first, tp[first], tp[tp[first]]], "知一课"
    group = bi if bi else cand  # 俱比或俱不比 → 涉害
    scores = [shehai(kes[i][1], kes[i][2]) for i in group]
    mx = max(scores)
    top = [group[i] for i, s in enumerate(scores) if s == mx]
    if len(top) == 1:
        first = kes[top[0]][1]
        return [first, tp[first], tp[tp[first]]], "涉害课"
    for pool, name in ((MENG, "涉害课·见机"), (ZHONG, "涉害课·察微"), (JI, "涉害课·缀瑕")):
        hit = [i for i in top if kes[i][2] in pool]  # 取"上神所临之地盘位"在孟/仲/季者
        if len(hit) == 1:
            first = kes[hit[0]][1]
            return [first, tp[first], tp[tp[first]]], name
        if hit:
            top = hit
    first = kes[top[0]][1]
    return [first, tp[first], tp[tp[first]]], "涉害课"


if __name__ == "__main__":
    main()
