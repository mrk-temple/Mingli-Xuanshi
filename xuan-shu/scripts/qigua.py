#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qigua.py —— 梅花易数起卦与装卦（确定性算法部分）。

用法:
    python3 scripts/qigua.py --numbers 3 7            # 报数起卦：上=3%8 下=7%8 动=(3+7)%6
    python3 scripts/qigua.py --numbers 3 7 5          # 第三个数定动爻
    python3 scripts/qigua.py --lunar 6 3 9 7          # 农历起卦：年支数 月 日 时辰数

输出（文本，可作后续解读的唯一事实依据）:
    本卦 / 互卦 / 变卦 / 动爻 / 体用 / 五行生克结论

注意: 起卦结果必须由本脚本计算，不许 LLM 心算替代。农历换算不在本脚本范围。
"""
import argparse
import sys

try:  # xuan-shu 移植补丁：Windows 控制台/管道编码统一为 UTF-8（算法与原版一致）
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 先天八卦数 → (卦名, 五行, 自下而上三爻)
TRIGRAMS = {
    1: ("乾", "金", (1, 1, 1)),
    2: ("兑", "金", (1, 1, 0)),
    3: ("离", "火", (1, 0, 1)),
    4: ("震", "木", (1, 0, 0)),
    5: ("巽", "木", (0, 1, 1)),
    6: ("坎", "水", (0, 1, 0)),
    7: ("艮", "土", (0, 0, 1)),
    8: ("坤", "土", (0, 0, 0)),
}
LINES_TO_NUM = {lines: num for num, (_, _, lines) in TRIGRAMS.items()}

# 六十四卦名：上卦数 → [下卦数 1..8 对应的卦名]
HEXAGRAM_NAMES = {
    1: ["乾为天", "天泽履", "天火同人", "天雷无妄", "天风姤", "天水讼", "天山遁", "天地否"],
    2: ["泽天夬", "兑为泽", "泽火革", "泽雷随", "泽风大过", "泽水困", "泽山咸", "泽地萃"],
    3: ["火天大有", "火泽睽", "离为火", "火雷噬嗑", "火风鼎", "火水未济", "火山旅", "火地晋"],
    4: ["雷天大壮", "雷泽归妹", "雷火丰", "震为雷", "雷风恒", "雷水解", "雷山小过", "雷地豫"],
    5: ["风天小畜", "风泽中孚", "风火家人", "风雷益", "巽为风", "风水涣", "风山渐", "风地观"],
    6: ["水天需", "水泽节", "水火既济", "水雷屯", "水风井", "坎为水", "水山蹇", "水地比"],
    7: ["山天大畜", "山泽损", "山火贲", "山雷颐", "山风蛊", "山水蒙", "艮为山", "山地剥"],
    8: ["地天泰", "地泽临", "地火明夷", "地雷复", "地风升", "地水师", "地山谦", "坤为地"],
}

# 五行相生: 木→火→土→金→水→木
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# 五行相克: 木→土→水→火→金→木
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def mod8(x):
    r = x % 8
    return 8 if r == 0 else r


def mod6(x):
    r = x % 6
    return 6 if r == 0 else r


def gua_name(upper, lower):
    return HEXAGRAM_NAMES[upper][lower - 1]


def format_gua(upper, lower):
    return f"{gua_name(upper, lower)}（上{TRIGRAMS[upper][0]}下{TRIGRAMS[lower][0]}）"


def build_lines(upper, lower):
    """全局六爻（自下而上）: 下卦三爻 + 上卦三爻。"""
    return list(TRIGRAMS[lower][2]) + list(TRIGRAMS[upper][2])


def inter_gua(lines):
    """互卦: 下互 = 第 2,3,4 爻；上互 = 第 3,4,5 爻。"""
    lower = LINES_TO_NUM[tuple(lines[1:4])]
    upper = LINES_TO_NUM[tuple(lines[2:5])]
    return upper, lower


def change_gua(lines, moving):
    """变卦: 动爻阴阳互变。"""
    flipped = list(lines)
    flipped[moving - 1] = 1 - flipped[moving - 1]
    lower = LINES_TO_NUM[tuple(flipped[0:3])]
    upper = LINES_TO_NUM[tuple(flipped[3:6])]
    return upper, lower


def ti_yong(moving, upper, lower):
    """体用: 动爻所在卦为用卦，另一卦为体卦。"""
    if moving <= 3:
        return upper, lower  # 动在下卦 → 用=下，体=上
    return lower, upper      # 动在上卦 → 用=上，体=下


def shengke(body_elem, use_elem):
    """体用五行生克结论。"""
    if SHENG[use_elem] == body_elem:
        return "用生体 → 吉（事来助我，得力）"
    if KE[use_elem] == body_elem:
        return "用克体 → 凶（事不利我，受制）"
    if SHENG[body_elem] == use_elem:
        return "体生用 → 泄气（我生其事，耗力）"
    if KE[body_elem] == use_elem:
        return "体克用 → 费力（我制其事，劳而有成）"
    return "比和 → 平（势均力敌，各安其位）"


def main():
    ap = argparse.ArgumentParser(description="梅花易数起卦（确定性算法）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--numbers", nargs="+", type=int, metavar="N",
                   help="报数起卦：两数或三数")
    g.add_argument("--lunar", nargs=4, type=int, metavar=("YEAR", "MONTH", "DAY", "HOUR"),
                   help="农历起卦：年支数 月 日 时辰数")
    g.add_argument("--solar", nargs=4, type=int, metavar=("Y", "M", "D", "H"),
                   help="公历起卦：公历年月日时，内部经 lunar_python 转农历（年支序+月+日=上卦，加时辰=下卦与动爻）")
    args = ap.parse_args()

    if args.lunar:
        y, m, d, h = args.lunar
        base = y + m + d
        upper = mod8(base)
        lower = mod8(base + h)
        moving = mod6(base + h)
    elif args.solar:
        try:
            from lunar_python import Solar
            solar = Solar.fromYmdHms(args.solar[0], args.solar[1], args.solar[2], args.solar[3], 0, 0)
            lunar = solar.getLunar()
            y = lunar.getYearZhiIndex() + 1
            m = lunar.getMonth()
            if m < 0:
                m = -m  # 闰月按同月数计（邵雍法惯例）
            d = lunar.getDay()
            h = lunar.getTimeZhiIndex() + 1
        except ImportError:
            print("缺少依赖 lunar_python: 请先 pip install lunar_python（或改用 --lunar 自报农历）", file=sys.stderr)
            sys.exit(1)
        base = y + m + d
        upper = mod8(base)
        lower = mod8(base + h)
        moving = mod6(base + h)
    else:
        nums = args.numbers
        if len(nums) not in (2, 3):
            print("报数起卦需要 2 或 3 个数", file=sys.stderr)
            sys.exit(1)
        upper = mod8(nums[0])
        lower = mod8(nums[1])
        moving = mod6(nums[2]) if len(nums) == 3 else mod6(nums[0] + nums[1])

    lines = build_lines(upper, lower)
    iu, il = inter_gua(lines)
    cu, cl = change_gua(lines, moving)
    body, use = ti_yong(moving, upper, lower)
    body_elem = TRIGRAMS[body][1]
    use_elem = TRIGRAMS[use][1]

    print("梅花易数起卦结果（由脚本计算，勿人工复算）")
    print(f"本卦: {format_gua(upper, lower)}")
    print(f"互卦: {format_gua(iu, il)}")
    print(f"变卦: {format_gua(cu, cl)}")
    print(f"动爻: 第 {moving} 爻")
    print(f"体卦: {TRIGRAMS[body][0]}（{body_elem}）  用卦: {TRIGRAMS[use][0]}（{use_elem}）")
    print(f"体用生克: {shengke(body_elem, use_elem)}")


if __name__ == "__main__":
    main()
