#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lunar_convert.py —— 公历 → 农历换算工具(基于 lunar_python)。

用法:
    python3 scripts/lunar_convert.py 2026 8 11 20        # 公历年月日时
    python3 scripts/lunar_convert.py 2026 8 11 20 --longitude 116.4   # 指定经度,给真太阳时参考

用途:
    - 梅花易数农历起卦(qigua.py --lunar)前,把用户的公历时间换成农历年月日时
    - 八字排盘临界时刻(节气边界)复核
    - 真太阳时参考:经度修正 + 均时差由 lunar_python 内置,输出修正后时刻与四柱比对

输出: 农历年月日时(含年支序/时辰序,可直接喂 qigua --lunar)、当天节气、真太阳时四柱对比。
依赖: lunar_python(pip install lunar_python)。未安装时明确报错,不由 LLM 心算替代。
"""
import argparse
import datetime
import math
import sys

try:  # xuan-shu 移植补丁：Windows 控制台/管道编码统一为 UTF-8（算法与原版一致）
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from lunar_python import Solar
except ImportError:
    print("缺少依赖 lunar_python: 请先 pip install lunar_python", file=sys.stderr)
    sys.exit(1)

MONTH_CN = "正二三四五六七八九十冬腊"


def eot_minutes(y, m, d):
    """均时差近似公式(分钟): 真太阳时 - 平太阳时。±1~2 分钟精度,时辰判定够用。"""
    n = (datetime.date(y, m, d) - datetime.date(y, 1, 1)).days + 1
    b = 2 * math.pi * (n - 81) / 364
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def true_solar_time(y, m, d, h, lon):
    """真太阳时修正: 经度差(东八区120°基准)×4 分钟 + 均时差。返回修正后 datetime。"""
    offset = (lon - 120.0) * 4 + eot_minutes(y, m, d)
    return datetime.datetime(y, m, d, h, 0) + datetime.timedelta(minutes=offset), offset


def main():
    ap = argparse.ArgumentParser(description="公历→农历换算(供梅花起卦与排盘复核)")
    ap.add_argument("args", nargs="+", type=int, help="公历年 月 日 [时]")
    ap.add_argument("--longitude", type=float, help="出生地经度(东经为正),用于真太阳时参考")
    args = ap.parse_args()

    if not 3 <= len(args.args) <= 4:
        print("用法: lunar_convert.py 年 月 日 [时]", file=sys.stderr)
        sys.exit(1)
    y, m, d = args.args[:3]
    h = args.args[3] if len(args.args) == 4 else 12
    if not (1900 <= y <= 2100) or not (1 <= m <= 12) or not (0 <= h <= 23):
        print("输入越界: 年份须在 1900-2100,月 1-12,日 1-31,时 0-23", file=sys.stderr)
        sys.exit(1)

    solar = Solar.fromYmdHms(y, m, d, h, 0, 0)
    lunar = solar.getLunar()

    year_zhi_seq = lunar.getYearZhiIndex() + 1     # 1=子 ... 12=亥
    hour_zhi_seq = lunar.getTimeZhiIndex() + 1     # 1=子 ... 12=亥
    lunar_month = lunar.getMonth()
    if lunar_month < 0:
        lunar_month = -lunar_month
        leap = "闰"
    else:
        leap = ""

    print("公历→农历换算(lunar_python)")
    print(f"公历: {y}年{m}月{d}日 {h}时")
    print(f"农历: {lunar.getYearInGanZhi()}年{leap}{MONTH_CN[lunar_month-1]}月{lunar.getDayInChinese()}")
    print(f"梅花起卦用数: 年支序{year_zhi_seq}({lunar.getYearZhi()}) 月{lunar_month} 日{lunar.getDay()} 时辰序{hour_zhi_seq}({lunar.getTimeZhi()})")
    jq = lunar.getJieQi()
    if jq:
        print(f"当天节气: {jq}")

    # 四柱参考(平太阳时)
    ec = lunar.getEightChar()
    print(f"四柱(平太阳时): {ec.getYear()} {ec.getMonth()} {ec.getDay()} {ec.getTime()}")
    if args.longitude:
        dt, offset = true_solar_time(y, m, d, h, args.longitude)
        s2 = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
        l2 = s2.getLunar()
        ec2 = l2.getEightChar()
        print(f"四柱(真太阳时参考,经度{args.longitude}°,修正{offset:+.1f}分钟 → {dt.strftime('%Y-%m-%d %H:%M')}): "
              f"{ec2.getYear()} {ec2.getMonth()} {ec2.getDay()} {ec2.getTime()}")
        print("[提示] 若两行四柱不同,时辰正处于边界,请复核出生时刻;paipan.py --longitude 做同一修正")


if __name__ == "__main__":
    main()
