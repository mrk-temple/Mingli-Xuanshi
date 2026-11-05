#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xiaoliuren.py —— 小六壬（马前课）起课（确定性算法部分）。

用法:
    python3 scripts/xiaoliuren.py --lunar 3 5 6          # 农历三月初五巳时（时辰: 子=1…亥=12）
    python3 scripts/xiaoliuren.py --numbers 3 5 6        # 报三数（依次代月/日/时数）
    python3 scripts/xiaoliuren.py --numbers 8 12 9 --sum # 总数累加法变体（非主流，见下）
    python3 scripts/xiaoliuren.py --solar 2026 8 11 15   # 公历（依赖 lunar_python 转农历）

规则（古法·三步重锚，"月上起日、日上起时"）:
    - 六宫顺序: 大安(1)→留连(2)→速喜(3)→赤口(4)→小吉(5)→空亡(6)→回大安
    - 从大安起正月顺数至 m 月 → 月宫；从月宫起初一顺数至 d 日 → 日宫；从日宫起子时顺数至 h 时 → 断宫
    - 等价式: 断宫 = (m + d + h - 3) mod 6 + 1
    - 大安居寅位（"寅位起大安"与"从大安起正月"同一规则：正月即寅月）

分歧声明（显式版本选择）:
    - --sum 开启"总数累加法"变体（断宫 = (m+d+h-1) mod 6 + 1），与古法相差 2 位，默认关闭
    - 小吉五行主流作"水"，个别流派作"木"——本脚本按主流取水
    - 23 点起算与闰月归属存流派分歧，脚本不内置，由用户以 --lunar 自报农历为准

输出: 月宫/日宫/断宫落位 + 最终宫属性（五行/六神/地支/吉凶/主数）+ 通行断辞。
断辞展开与事项分类断法见 references/xiaoliuren-guide.md。
"""
import argparse
import sys

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 六宫: (序号, 宫名, 手指位, 地支, 六神, 五行, 吉凶等级, 主应之数, 断辞)
PALACES = {
    1: ("大安", "食指根", "寅", "青龙", "木", "大吉", "一、五、七",
        "大安事事昌，求财在坤方，失物去不远，宅舍保安康，行人身未动，病者主无妨，将军回田野，仔细更推详。"),
    2: ("留连", "食指中", "卯", "玄武", "水", "小凶", "二、八、十",
        "留连事难成，求谋日未明，官事只宜缓，去者未回程，失物南方见，急讨方称心，更须防口舌，人口且平平。"),
    3: ("速喜", "食指尖", "辰", "朱雀", "火", "中吉", "三、六、九",
        "速喜喜来临，求财向南行，失物申未午，逢人路上寻，官事有福德，病者无祸侵，田宅六畜吉，行人有音信。"),
    4: ("赤口", "中指尖", "巳", "白虎", "金", "小凶", "四、七、十",
        "赤口主口舌，官非切要防，失物急去寻，行人有惊慌，鸡犬多作怪，病者出西方，更须防咒诅，恐怕染瘟黄。"),
    5: ("小吉", "中指中", "午", "六合", "水", "大吉", "一、五、七",
        "小吉最吉昌，路上好商量，阴人来报喜，失物在坤方，行人立便至，交关真是强，凡事皆和合，病者祷上苍。"),
    6: ("空亡", "无名指尖", "未", "勾陈", "土", "大凶", "三、六、九",
        "空亡事不长，阴人小乘张，求财无利益，行人有灾殃，失物寻不见，官事主刑伤，病人逢暗鬼，解禳保安康。"),
}


def palace(m, d, h, sum_mode):
    """古法三步重锚: 断宫 = (m+d+h-3) mod 6 + 1；--sum 变体 = (m+d+h-1) mod 6 + 1。"""
    if sum_mode:
        return (m + d + h - 1) % 6 + 1
    return (m + d + h - 3) % 6 + 1


def lunar_from_solar(y, m, d, h):
    """公历→农历（月、日、时辰序）。依赖 lunar_python；未安装时明确报错。"""
    try:
        from lunar_python import Solar
    except ImportError:
        print("缺少依赖 lunar_python：请先 pip install lunar_python，或改用 --lunar 自报农历月日时辰",
              file=sys.stderr)
        sys.exit(1)
    solar = Solar.fromYmdHms(y, m, d, h, 0, 0)
    lunar = solar.getLunar()
    lm = lunar.getMonth()
    if lm < 0:
        lm = -lm  # 闰月按当月数计（通行"按当月月建"说）
    return lm, lunar.getDay(), lunar.getTimeZhiIndex() + 1


def main():
    ap = argparse.ArgumentParser(description="小六壬起课（确定性算法）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--lunar", nargs=3, type=int, metavar=("M", "D", "H"),
                   help="农历月 日 时辰序（子=1…亥=12）")
    g.add_argument("--numbers", nargs=3, type=int, metavar=("A", "B", "C"),
                   help="报三数，依次代月/日/时数")
    g.add_argument("--solar", nargs=4, type=int, metavar=("Y", "M", "D", "H"),
                   help="公历年月日时（内部转农历，依赖 lunar_python）")
    ap.add_argument("--sum", action="store_true",
                    help="总数累加法变体（与古法相差 2 位，非主流，默认关闭）")
    args = ap.parse_args()

    if args.solar:
        m, d, h = lunar_from_solar(*args.solar)
        src = f"公历 {args.solar[0]}年{args.solar[1]}月{args.solar[2]}日{args.solar[3]}时 → 农历 {m}月{d}日 时辰序{h}"
    else:
        m, d, h = (args.lunar or args.numbers)
        if not (1 <= m <= 12 and 1 <= d <= 30 and 1 <= h <= 12):
            print("输入越界：月 1-12，日 1-30，时辰 1-12（子=1…亥=12）", file=sys.stderr)
            sys.exit(1)
        src = f"农历 {m}月{d}日 时辰序{h}" if args.lunar else f"报数 {m} {d} {h}"

    month_p = (m - 1) % 6 + 1
    day_p = (m + d - 2) % 6 + 1
    final_p = palace(m, d, h, args.sum)
    mode = "总数累加法变体" if args.sum else "古法（月上起日、日上起时）"

    print(f"小六壬起课结果（由脚本计算，勿人工复算）  [算法: {mode}]")
    print(f"输入: {src}")
    print(f"月宫: {PALACES[month_p][0]}（{PALACES[month_p][3]}·{PALACES[month_p][4]}）")
    print(f"日宫: {PALACES[day_p][0]}（{PALACES[day_p][3]}·{PALACES[day_p][4]}）")
    name, finger, zhi, shen, wx, level, numbers, duanci = PALACES[final_p]
    print(f"断宫: {name}（{finger}·{zhi}位 | 六神{shen} | 属{wx} | {level} | 主数{numbers}）")
    print(f"断辞: {duanci}")
    print("[注] 断辞为通行本（各版本个别字词有出入）；展开解读与事项断法见 references/xiaoliuren-guide.md")


if __name__ == "__main__":
    main()
