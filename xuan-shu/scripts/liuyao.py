#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""liuyao.py —— 六爻纳甲（文王课/铜钱卦）起卦与装卦（确定性算法部分）。

用法:
    python3 scripts/liuyao.py --coins 2 3 2 1 3 0         # 铜钱摇卦：6 次摇卦结果，自下而上（初爻→上爻），每爻报"背"的个数 0-3
    python3 scripts/liuyao.py --coins 2 3 2 1 3 0 --zi-as-yang   # 流派变体：字面为阳（默认字=阴、背=阳）
    python3 scripts/liuyao.py --numbers 3 7               # 报数起卦：上=3%8 下=7%8 动=(3+7)%6；三数时第三数定动爻
    python3 scripts/liuyao.py --time 6 3 9 7              # 农历时间起卦：年支序 月 日 时辰序（先天卦数取卦）
    python3 scripts/liuyao.py --random --seed 42          # 脚本模拟摇卦（默认密码学真随机，--seed 可复现）
    python3 scripts/liuyao.py --coins 2 3 2 1 3 0 --date 2026 8 11   # 指定起卦日期（默认今天：定日干支/月建）

装卦内容（全部由本脚本计算，禁止人工复算）:
    卦名与卦宫（八宫卦序查表）→ 世应 → 纳甲（干支）→ 六亲（以卦宫五行为"我"）→
    六神（按起卦日天干）→ 动爻与变卦（变爻纳支按变卦、六亲仍以本卦宫为"我"）→
    旬空（起卦日干支所在旬）→ 月建与月破 → 各爻对月建旺相休囚死 → 缺六亲的伏神

约定声明（流派分歧已显式选择，详见 references/liuyao-guide.md）:
    - 铜钱阴阳：默认字=阴、背=阳（主流）；--zi-as-yang 切换"字=阳"流派
    - 报数/时间起卦用先天卦数（乾1 兑2 离3 震4 巽5 坎6 艮7 坤8），余 0 取 8（动爻余 0 取 6）
    - 六神按起卦日天干起（甲乙青龙、丙丁朱雀、戊勾陈、己螣蛇、庚辛白虎、壬癸玄武）
"""
import argparse
import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (TIAN_GAN, DI_ZHI, SHENG, KE, jdn, day_ganzhi, xunkong,
                    year_month_ganzhi, zhi_wuxing)

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 八经卦: 名称, 先天数, 五行, (内卦纳支三序), (外卦纳支三序), 内卦天干, 外卦天干, (三爻 0/1 自下而上)
TRIGRAM = {
    1: ("乾", 1, "金", (0, 2, 4), (6, 8, 10), "甲", "壬", (1, 1, 1)),
    2: ("兑", 2, "金", (5, 3, 1), (11, 9, 7), "丁", "丁", (1, 1, 0)),
    3: ("离", 3, "火", (3, 1, 11), (9, 7, 5), "己", "己", (1, 0, 1)),
    4: ("震", 4, "木", (0, 2, 4), (6, 8, 10), "庚", "庚", (1, 0, 0)),
    5: ("巽", 5, "木", (1, 11, 9), (7, 5, 3), "辛", "辛", (0, 1, 1)),
    6: ("坎", 6, "水", (2, 4, 6), (8, 10, 0), "戊", "戊", (0, 1, 0)),
    7: ("艮", 7, "土", (4, 6, 8), (10, 0, 2), "丙", "丙", (0, 0, 1)),
    8: ("坤", 8, "土", (7, 5, 3), (1, 11, 9), "乙", "癸", (0, 0, 0)),
}
LINES_TO_NUM = {v[7]: k for k, v in TRIGRAM.items()}

# 八宫卦序: (上卦先天数, 下卦先天数) → (卦名, 宫名, 世爻位)
# 宫序: 本宫世6, 一世世1, 二世世2, 三世世3, 四世世4, 五世世5, 游魂世4, 归魂世3
_PALACES = [
    ("乾", [(1, 1, "乾为天", 6), (1, 5, "天风姤", 1), (1, 7, "天山遁", 2), (1, 8, "天地否", 3),
            (5, 8, "风地观", 4), (7, 8, "山地剥", 5), (3, 8, "火地晋", 4), (3, 1, "火天大有", 3)]),
    ("坎", [(6, 6, "坎为水", 6), (6, 2, "水泽节", 1), (6, 4, "水雷屯", 2), (6, 3, "水火既济", 3),
            (2, 3, "泽火革", 4), (4, 3, "雷火丰", 5), (8, 3, "地火明夷", 4), (8, 6, "地水师", 3)]),
    ("艮", [(7, 7, "艮为山", 6), (7, 3, "山火贲", 1), (7, 1, "山天大畜", 2), (7, 2, "山泽损", 3),
            (3, 2, "火泽睽", 4), (1, 2, "天泽履", 5), (5, 2, "风泽中孚", 4), (5, 7, "风山渐", 3)]),
    ("震", [(4, 4, "震为雷", 6), (4, 8, "雷地豫", 1), (4, 6, "雷水解", 2), (4, 5, "雷风恒", 3),
            (8, 5, "地风升", 4), (6, 5, "水风井", 5), (2, 5, "泽风大过", 4), (2, 4, "泽雷随", 3)]),
    ("巽", [(5, 5, "巽为风", 6), (5, 1, "风天小畜", 1), (5, 3, "风火家人", 2), (5, 4, "风雷益", 3),
            (1, 4, "天雷无妄", 4), (3, 4, "火雷噬嗑", 5), (7, 4, "山雷颐", 4), (7, 5, "山风蛊", 3)]),
    ("离", [(3, 3, "离为火", 6), (3, 7, "火山旅", 1), (3, 5, "火风鼎", 2), (3, 6, "火水未济", 3),
            (7, 6, "山水蒙", 4), (5, 6, "风水涣", 5), (1, 6, "天水讼", 4), (1, 3, "天火同人", 3)]),
    ("坤", [(8, 8, "坤为地", 6), (8, 4, "地雷复", 1), (8, 2, "地泽临", 2), (8, 1, "地天泰", 3),
            (4, 1, "雷天大壮", 4), (2, 1, "泽天夬", 5), (6, 1, "水天需", 4), (6, 8, "水地比", 3)]),
    ("兑", [(2, 2, "兑为泽", 6), (2, 6, "泽水困", 1), (2, 8, "泽地萃", 2), (2, 7, "泽山咸", 3),
            (6, 7, "水山蹇", 4), (8, 7, "地山谦", 5), (4, 7, "雷山小过", 4), (4, 2, "雷泽归妹", 3)]),
]
HEX_MAP = {}          # (upper, lower) -> (name, palace, shi)
PALACE_WUXING = {"乾": "金", "坎": "水", "艮": "土", "震": "木",
                 "巽": "木", "离": "火", "坤": "土", "兑": "金"}
PALACE_FIRST = {}     # palace -> (upper, lower) 首卦
for pal, rows in _PALACES:
    for i, (u, l, name, shi) in enumerate(rows):
        HEX_MAP[(u, l)] = (name, pal, shi)
    PALACE_FIRST[pal] = (rows[0][0], rows[0][1])

# 六神（按日干）与顺排顺序
LIUSHEN_START = ["青龙", "青龙", "朱雀", "朱雀", "勾陈", "螣蛇", "白虎", "白虎", "玄武", "玄武"]  # 甲..癸
LIUSHEN_ORDER = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]

LIUQIN_DEFS = ("父母", "兄弟", "子孙", "妻财", "官鬼")


def liuqin(palace_wx, zhi_wx):
    """六亲：以卦宫五行为"我"：生我父母、我生子孙、克我官鬼、我克妻财、同兄弟。"""
    if zhi_wx == palace_wx:
        return "兄弟"
    if SHENG[zhi_wx] == palace_wx:
        return "父母"
    if SHENG[palace_wx] == zhi_wx:
        return "子孙"
    if KE[zhi_wx] == palace_wx:
        return "官鬼"
    return "妻财"  # KE[palace_wx] == zhi_wx


def waxiang(zhi_wx, month_wx):
    """爻对月建的旺相休囚死。"""
    if zhi_wx == month_wx:
        return "旺"
    if SHENG[month_wx] == zhi_wx:
        return "相"
    if SHENG[zhi_wx] == month_wx:
        return "休"
    if KE[zhi_wx] == month_wx:
        return "囚"
    return "死"  # KE[month_wx] == zhi_wx


def najia_lines(lines):
    """六爻纳甲：返回每爻 (天干, 地支序)。天干按该爻所在经卦之纳甲（内/外），地支按纳支。"""
    lower = LINES_TO_NUM[tuple(lines[0:3])]
    upper = LINES_TO_NUM[tuple(lines[3:6])]
    out = []
    for pos in range(6):  # pos 0=初爻 .. 5=上爻
        if pos < 3:
            tri = lower
            inner = True
            k = pos
        else:
            tri = upper
            inner = False
            k = pos - 3
        name, _, _, inzhi, outzhi, ingan, outgan, _ = TRIGRAM[tri]
        zhi = inzhi[k] if inner else outzhi[k]
        gan = ingan if inner else outgan
        out.append((gan, zhi))
    return out, lower, upper


def main():
    ap = argparse.ArgumentParser(description="六爻纳甲起卦与装卦（确定性算法）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--coins", nargs=6, type=int, metavar="N",
                   help="铜钱摇卦：6 次摇卦每爻'背'的个数 0-3（自下而上：第 1 次=初爻）")
    g.add_argument("--numbers", nargs="+", type=int, metavar="N", help="报数起卦：2 或 3 个数")
    g.add_argument("--time", nargs=4, type=int, metavar=("YZ", "M", "D", "H"),
                   help="农历时间起卦：年支序 月 日 时辰序（先天卦数取卦）")
    g.add_argument("--random", action="store_true", help="脚本模拟摇卦")
    ap.add_argument("--zi-as-yang", action="store_true",
                    help="流派变体：字面为阳（默认字=阴、背=阳）")
    ap.add_argument("--seed", type=int, help="固定随机种子（--random 可复现）")
    ap.add_argument("--date", nargs=3, type=int, metavar=("Y", "M", "D"),
                    help="起卦公历日期（默认今天；定日干支/月建）")
    args = ap.parse_args()

    # ---- 起卦 → 六爻 (0 阴 1 阳) + 动爻集合 ----
    if args.coins:
        lines, moving = [], []
        for i, nbei in enumerate(args.coins):
            if not 0 <= nbei <= 3:
                print("每爻'背'的个数须为 0-3", file=sys.stderr)
                sys.exit(1)
            # 以"阳面数"定爻：1 阳=少阳(静)、2 阳=少阴(静)、3 阳=老阳(动)、0 阳=老阴(动)
            # 默认字=阴、背=阳 → 阳面数=背数；--zi-as-yang 字=阳 → 阳面数=字数=3-背数
            nyang = (3 - nbei) if args.zi_as_yang else nbei
            lines.append(1 if nyang in (1, 3) else 0)
            if nyang in (0, 3):
                moving.append(i + 1)
        src = f"铜钱摇卦 背数(初→上)={args.coins}" + (" [字=阳变体]" if args.zi_as_yang else " [字=阴、背=阳]")
    elif args.numbers:
        nums = args.numbers
        if len(nums) not in (2, 3):
            print("报数起卦需要 2 或 3 个数", file=sys.stderr)
            sys.exit(1)
        upper = nums[0] % 8 or 8
        lower = nums[1] % 8 or 8
        dong = (nums[2] if len(nums) == 3 else nums[0] + nums[1]) % 6 or 6
        lines = list(TRIGRAM[lower][7]) + list(TRIGRAM[upper][7])
        moving = [dong]
        src = f"报数 {nums} → 上{TRIGRAM[upper][0]} 下{TRIGRAM[lower][0]} 动第{dong}爻"
    elif args.time:
        yz, m, d, h = args.time
        base = yz + m + d
        upper = base % 8 or 8
        lower = (base + h) % 8 or 8
        dong = (base + h) % 6 or 6
        lines = list(TRIGRAM[lower][7]) + list(TRIGRAM[upper][7])
        moving = [dong]
        src = f"农历时间 年支序{yz} 月{m} 日{d} 时辰序{h} → 上{TRIGRAM[upper][0]} 下{TRIGRAM[lower][0]} 动第{dong}爻"
    else:  # --random：模拟三枚铜钱摇 6 次（每枚字/背各 1/2，保持真实概率分布）
        rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
        tosses = [sum(rng.randrange(2) for _ in range(3)) for _ in range(6)]  # 每爻背数 0-3
        lines, moving = [], []
        for nbei in tosses:
            nyang = 3 - nbei if args.zi_as_yang else nbei
            lines.append(1 if nyang in (1, 3) else 0)
            if nyang in (0, 3):
                moving.append(len(lines))
        src = f"脚本模拟摇卦 背数(初→上)={tosses} [随机源: {'seed=' + str(args.seed) if args.seed is not None else 'secrets'}]"

    # ---- 起卦日期 → 日干支/月建（默认今天） ----
    if args.date:
        ty, tm, td = args.date
        if not (1900 <= ty <= 2100):
            print("date 年份须在 1900-2100", file=sys.stderr)
            sys.exit(1)
    else:
        today = datetime.date.today()
        ty, tm, td = today.year, today.month, today.day
    dgan, dzhi = day_ganzhi(ty, tm, td)
    jd = float(jdn(ty, tm, td)) + 0.5
    _, _, _, month_zhi = year_month_ganzhi(jd)
    empty = xunkong(dgan, dzhi)
    month_wx = zhi_wuxing(month_zhi)
    po = (month_zhi + 6) % 12

    # ---- 装卦 ----
    najia, lower, upper = najia_lines(lines)
    gua_name, palace, shi = HEX_MAP[(upper, lower)]
    ying = ((shi - 1 + 3) % 6) + 1
    pw = PALACE_WUXING[palace]

    flipped = list(lines)
    for mv in moving:
        flipped[mv - 1] = 1 - flipped[mv - 1]
    bian_lower = LINES_TO_NUM[tuple(flipped[0:3])]
    bian_upper = LINES_TO_NUM[tuple(flipped[3:6])]
    bian_name, _, _ = HEX_MAP[(bian_upper, bian_lower)]
    bian_najia, _, _ = najia_lines(flipped)

    print("六爻纳甲装卦结果（由脚本计算，勿人工复算）")
    print(f"起卦: {src}")
    print(f"本卦: {gua_name}（{palace}宫·{pw}）  世爻: 第{shi}爻  应爻: 第{ying}爻" +
          (f"  动爻: {moving}" if moving else ""))
    print(f"变卦: {bian_name}" + ("" if moving else "（无动爻，不变）"))
    print(f"起卦日: {ty}-{tm:02d}-{td:02d}  日干支: {TIAN_GAN[dgan]}{DI_ZHI[dzhi]}  "
          f"月建: {DI_ZHI[month_zhi]}({month_wx})  月破: {DI_ZHI[po]}  旬空: {DI_ZHI[empty[0]]}{DI_ZHI[empty[1]]}")
    print("-" * 64)
    print(f"{'爻位':<4}{'纳甲':<6}{'六亲':<5}{'六神':<5}{'世应':<6}{'动':<4}{'旺衰':<5}{'标记':<12}变爻")
    liuqing_set = set()
    for pos in range(6):
        yao = pos + 1
        gan, zhi = najia[pos]
        qin = liuqin(pw, zhi_wuxing(zhi))
        liuqing_set.add(qin)
        shen = LIUSHEN_ORDER[(LIUSHEN_ORDER.index(LIUSHEN_START[dgan]) + pos) % 6]
        sw = "世" if yao == shi else ("应" if yao == ying else "")
        dong = "动" if yao in moving else ""
        wx_state = waxiang(zhi_wuxing(zhi), month_wx)
        marks = []
        if zhi in empty:
            marks.append("旬空")
        if zhi == po:
            marks.append("月破")
        if zhi == month_zhi:
            marks.append("值月建")
        if zhi == dzhi:
            marks.append("值日辰")
        bian = ""
        if yao in moving:
            bgan, bzhi = bian_najia[pos]
            bqin = liuqin(pw, zhi_wuxing(bzhi))
            bian = f"{bgan}{DI_ZHI[bzhi]}（{bqin}）"
        print(f"{yao:<4}{gan}{DI_ZHI[zhi]:<4}{qin:<5}{shen:<5}{sw:<6}{dong:<4}{wx_state:<5}"
              f"{' '.join(marks):<12}{bian}")
    # 伏神：本卦缺的六亲，从本宫首卦取该六亲之爻
    missing = [q for q in LIUQIN_DEFS if q not in liuqing_set]
    if missing:
        fu, fl = PALACE_FIRST[palace]
        fu_lines = list(TRIGRAM[fl][7]) + list(TRIGRAM[fu][7])
        fu_najia, _, _ = najia_lines(fu_lines)
        for q in missing:
            for pos in range(6):
                fgan, fzhi = fu_najia[pos]
                if liuqin(pw, zhi_wuxing(fzhi)) == q:
                    print(f"伏神: {q}——本宫首卦{pos + 1}爻 {fgan}{DI_ZHI[fzhi]}（本卦无{q}爻，取用时可参）")
                    break
    print("-" * 64)
    print("[注] 旺衰为爻对月建之旺相休囚死（月建为提纲、日辰为主宰）；断卦规则见 references/liuyao-guide.md")


if __name__ == "__main__":
    main()
