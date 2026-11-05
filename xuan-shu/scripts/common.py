#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common.py —— xuan-shu 各排盘脚本共用的干支/节气/五行基础（无 CLI，被 import）。

与 paipan.py 同源的确定性公式：儒略日、太阳视黄经（Meeus 简化式）、
干支纪时（五虎遁/五鼠遁）、旬空、五行生克。1900-2100 年有效。
"""
import math
import sys

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TIAN_GAN = "甲乙丙丁戊己庚辛壬癸"
DI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_WUXING = "木木火火土土金金水水"
ZHI_WUXING = "水土木木土火火土金金土水"
GAN_YINYANG = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
ZHI_YINYANG = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
HUTUN = [2, 4, 6, 8, 0]   # 五虎遁：年干%5 → 寅月天干
SHUTUN = [0, 2, 4, 6, 8]  # 五鼠遁：日干%5 → 子时天干
JIE_LAMBDA = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
JIE_ZHI = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1]  # 立春起十二节对应月支

# 五行生克
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 地支六冲
CHONG = {i: (i + 6) % 12 for i in range(12)}


def jdn(y, m, d):
    """公历 → 儒略日（正午制，格里高利历 1900-2100 精确）。"""
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def solar_longitude(jd):
    """太阳视黄经（度，单调递增不取模）。Meeus 简化式，精度约 ±0.01°。"""
    jd += 0.5  # 子夜制换算
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M)
         + 0.000289 * math.sin(3 * M))
    return L0 + C - 0.0057


def term_time_after(year, target_lambda):
    """year 年内太阳视黄经到达 target_lambda 的时刻（儒略日，二分 1 分钟精度）。"""
    lo = jdn(year, 1, 1) - 1.0
    hi = jdn(year, 12, 31) + 1.0
    r0 = solar_longitude(lo)
    cross = target_lambda + 360.0 * math.ceil((r0 - target_lambda) / 360.0)
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if solar_longitude(mid) < cross:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def jd_to_date(jd):
    """儒略日(正午制) → 公历(年, 月, 日)。标准格里高利算法，1900-2100 可用。"""
    jd += 0.5
    z = int(jd)
    a = z
    if z >= 2299161:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e)
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    return year, month, day


def year_month_ganzhi(jd):
    """儒略日 → (年干序, 年支序, 月干序, 月支序)。立春分年柱、十二节分月柱。"""
    y, _, _ = jd_to_date(jd)
    lichun_this = term_time_after(y, 315.0)
    if jd < lichun_this:
        year_gan = (y - 1 + 6) % 10
        year_zhi = (y - 1 - 4) % 12
    else:
        year_gan = (y + 6) % 10
        year_zhi = (y - 4) % 12
    terms = [term_time_after(y, lam) for lam in JIE_LAMBDA]
    if jd < terms[0]:
        xiaohan_this = term_time_after(y, 285.0)
        if jd < xiaohan_this:
            month_zhi, offset = 0, 10
        else:
            month_zhi, offset = 1, 11
        month_gan = (HUTUN[year_gan % 5] + offset) % 10
    else:
        lichun_next = term_time_after(y + 1, 315.0)
        for i in range(12):
            nxt = terms[i + 1] if i < 11 else lichun_next
            if terms[i] <= jd < nxt:
                month_zhi = JIE_ZHI[i]
                month_gan = (HUTUN[year_gan % 5] + i) % 10
                break
    return year_gan, year_zhi, month_gan, month_zhi


def day_ganzhi(y, m, d):
    """公历年月日 → (日干序, 日支序)。与 paipan.py 同日柱公式。"""
    seq = (jdn(y, m, d) + 49) % 60
    return seq % 10, seq % 12


def hour_zhi(h):
    """24 小时制 → 时支序（23 点起为子时初）。"""
    return ((h + 1) // 2) % 12


def hour_gan(day_gan, hour_zhi_idx):
    """五鼠遁：日干 → 时干。"""
    return (SHUTUN[day_gan % 5] + hour_zhi_idx) % 10


def xunkong(day_gan_idx, day_zhi_idx):
    """旬空：返回两个空亡地支序（0-11）。s=(支-干) mod 12 为旬首支序。"""
    s = (day_zhi_idx - day_gan_idx) % 12
    return (s + 10) % 12, (s + 11) % 12


def zhi_wuxing(z):
    return ZHI_WUXING[z]
