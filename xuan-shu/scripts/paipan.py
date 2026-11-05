#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paipan.py —— 八字排盘：公历生日 → 四柱干支 + 十神 + 藏干 + 五行统计 + 纳音。

用法:
    python3 scripts/paipan.py 1985 8 11 15                                  # 公历年 月 日 时（24 小时制，时省略默认 12）
    python3 scripts/paipan.py 1985 8 11 15 --gender 男                      # 加性别：输出大运全表
    python3 scripts/paipan.py 1985 8 11 15 --gender 男 --today 2026 8 11    # 加当前日期：定位当前大运
    python3 scripts/paipan.py 1985 8 11 15 --gender 男 --longitude 116.4    # 加出生地经度：真太阳时修正

原理:
    - 节气用太阳视黄经近似算法（Meeus 简化式，精度约 ±0.01°≈15 分钟）：
      立春(315°)分年柱；十二"节"分月柱
    - 日干支用儒略日 mod 60 推算；时柱按五鼠遁；月干按五虎遁
    - 默认东八区民用时，未做真太阳时/经度修正；出生时间恰在节气边界
      （±config 提醒阈值）时输出提醒，由 LLM 让用户复核

输出: 四柱 / 十神 / 藏干 / 五行统计 / 纳音 / 月令——断语阶段以本输出为唯一事实依据。
"""
import argparse
import math
import os
import sys

try:  # xuan-shu 移植补丁：Windows 控制台/管道编码统一为 UTF-8（算法与原版一致）
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TIAN_GAN = "甲乙丙丁戊己庚辛壬癸"
DI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
# 天干五行 / 地支五行
GAN_WUXING = "木木火火土土金金水水"
ZHI_WUXING = "水土木木土火火土金金土水"
# 干支阴阳（0 阳 1 阴）
GAN_YINYANG = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
ZHI_YINYANG = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
# 地支藏干（主气/中气/余气；无余气者列主气）
CANG_GAN = {
    "子": "癸", "丑": "己癸辛", "寅": "甲丙戊", "卯": "乙",
    "辰": "戊乙癸", "巳": "丙庚戊", "午": "丁己", "未": "己丁乙",
    "申": "庚壬戊", "酉": "辛", "戌": "戊辛丁", "亥": "壬甲",
}
# 60 甲子纳音（按序号 0..59，每两个一组）
NAYIN = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金",
    "山头火", "涧下水", "城头土", "白蜡金", "杨柳木",
    "泉中水", "屋上土", "霹雳火", "松柏木", "长流水",
    "沙中金", "山下火", "平地木", "壁上土", "金箔金",
    "覆灯火", "天河水", "大驿土", "钗钏金", "桑柘木",
    "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]
# 五虎遁：年干序号(0-9) → 寅月天干序号（甲己→丙 乙庚→戊 丙辛→庚 丁壬→壬 戊癸→甲）
HUTUN = [2, 4, 6, 8, 0]
# 五鼠遁：日干序号 → 子时天干序号（甲己→甲 乙庚→丙 丙辛→戊 丁壬→庚 戊癸→壬）
SHUTUN = [0, 2, 4, 6, 8]
# 十二"节"：从立春起每 30° 一个（太阳黄经 → 月支序号，立春=寅月）
JIE_LAMBDA = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
JIE_ZHI = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1]  # 寅卯辰巳午未申酉戌亥子丑


def jdn(y, m, d):
    """公历 → 儒略日（格里高利历，1900-2100 精确）。"""
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def solar_longitude(jd):
    """太阳视黄经（度，不取模——全年单调递增，二分前提）。Meeus 简化式，精度约 ±0.01°。
    注意：公式使用子夜制 Julian Date，传入的是正午制 JDN，须 +0.5 换算。"""
    jd += 0.5
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M)
         + 0.000289 * math.sin(3 * M))
    # 视黄经 = 几何黄经 - 光行差（约 -20.5″≈-0.0057°），精度提到 ~2 分钟
    return L0 + C - 0.0057


def term_time_after(year, target_lambda):
    """求 year 年内太阳视黄经到达 target_lambda 的时刻（儒略日）。
    原始黄经单调递增：对齐到当年穿越的 360k 目标值后二分到 1 分钟精度。"""
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


def ten_god(day_gan, other_gan):
    """十神：日干 vs 他干。"""
    d5, x5 = GAN_WUXING[day_gan], GAN_WUXING[other_gan]
    di, xi = GAN_YINYANG[day_gan], GAN_YINYANG[other_gan]
    same_yy = (di == xi)
    SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    if d5 == x5:
        return "比肩" if same_yy else "劫财"
    KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    if SHENG[d5] == x5:
        return "食神" if same_yy else "伤官"
    if SHENG[x5] == d5:
        return "偏印" if same_yy else "正印"
    if KE[x5] == d5:
        return "七杀" if same_yy else "正官"
    if KE[d5] == x5:
        return "偏财" if same_yy else "正财"
    raise ValueError(f"不可达: {day_gan} vs {other_gan}")


def jd_to_date(jd):
    """儒略日(正午制) → 公历(年, 月, 日)。标准格里高利算法,1900-2100 可用。"""
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


def da_yun(year_gan, month_gan, month_zhi, birth_jd, gender, terms):
    """大运排布(渊海子平《论起大运》):返回 (顺逆方向, 起运岁数, 月数, 交运时刻, 每步干支列表)。

    顺逆: 年干阳(甲丙戊庚壬)男顺女逆;年干阴(乙丁己辛癸)男逆女顺。
    起运: 顺排取出生后最近之"节",逆排取出生前最近之"节";
          距节天数 / 3 = 起运岁数(古法: 3 天=1 年, 1 天=4 个月, 1 时辰=10 天)。
    交运: 出生时刻 + 起运岁数 × 365.25 天(近似)。
    十年一步,从月柱起顺/逆推干支。
    """
    forward = (GAN_YINYANG[year_gan] == 0 and gender == "男") or (GAN_YINYANG[year_gan] == 1 and gender == "女")
    if forward:
        later = [t for t in terms if t > birth_jd]
        term_jd = min(later) if later else None  # 小寒后无更大节,取下年立春
    else:
        prev = [t for t in terms if t < birth_jd]
        term_jd = max(prev) if prev else None    # 理论不触发(大雪恒在年前),留保护
    if term_jd is None:
        term_jd = term_time_after(int(birth_jd / 365.25) + 1945, 315.0)  # 保护分支,不应走到
    total_days = abs(birth_jd - term_jd)
    years = int(total_days / 3)
    months = int((total_days - years * 3) * 4)   # 1 天 = 4 个月
    qiyun_jd = birth_jd + (total_days / 3) * 365.25
    steps = []
    for i in range(1, 9):  # 八步,八十年;第一步即月柱推一步,不重复月柱本身
        g = (month_gan + i) % 10 if forward else (month_gan - i) % 10
        z = (month_zhi + i) % 12 if forward else (month_zhi - i) % 12
        steps.append((g, z))
    return forward, years, months, qiyun_jd, steps


def load_config():
    """读取 ../config.yaml 的 term_tolerance_days（节气提醒阈值）；读不到时回退默认 1.0 天。"""
    cfg = {"term_tolerance_days": 1.0}
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.yaml")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line.startswith("term_tolerance_days:"):
                    cfg["term_tolerance_days"] = float(line.split(":", 1)[1].strip())
    except (OSError, ValueError):
        pass
    return cfg


def main():
    ap = argparse.ArgumentParser(description="八字排盘（公历→四柱+大运）")
    ap.add_argument("args", nargs="+", type=int, help="年 月 日 [时]（24 小时制）")
    ap.add_argument("--gender", choices=["男", "女"], help="性别（排大运必需）：阳年男顺女逆，阴年男逆女顺")
    ap.add_argument("--today", nargs=3, type=int, metavar=("Y", "M", "D"),
                    help="当前公历年月日，输出当前所在大运（可选）")
    ap.add_argument("--longitude", type=float, help="出生地经度（东经为正，可选）。真太阳时修正：经度差×4分钟+均时差")
    args = ap.parse_args()

    if not 2 <= len(args.args) <= 4:
        print("用法: paipan.py 年 月 日 [时]", file=sys.stderr)
        sys.exit(1)
    y, m, d = args.args[:3]
    h = args.args[3] if len(args.args) == 4 else 12
    if not (1900 <= y <= 2100) or not (1 <= m <= 12) or not (1 <= d <= 31) or not (0 <= h <= 23):
        print("输入越界：年份须在 1900-2100，月 1-12，日 1-31，时 0-23", file=sys.stderr)
        sys.exit(1)

    jd = float(jdn(y, m, d)) + (h / 24.0)
    if args.longitude is not None:
        # 真太阳时修正（东八区120°基准）：经度差×4分钟 + 均时差（±1~2分钟精度，时辰判定够用）。
        # 直接叠加到儒略日上，可正确跨日（日柱/月柱自动随之修正）。
        n = int(jdn(y, m, d)) - int(jdn(y, 1, 1)) + 1
        b = 2 * math.pi * (n - 81) / 364
        eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        fix_min = (args.longitude - 120.0) * 4 + eot
        jd += fix_min / (24 * 60)
        print(f"[真太阳时] 出生地经度 {args.longitude}°, 修正 {fix_min:+.1f} 分钟")

    # 年柱：立春（黄经 315°）为界
    lichun_this = term_time_after(y, 315.0)
    if jd < lichun_this:
        year_gan = (y - 1 + 6) % 10
        year_zhi = (y - 1 - 4) % 12
    else:
        year_gan = (y + 6) % 10
        year_zhi = (y - 4) % 12

    # 月柱：十二"节"（立春起每 30°）分月
    terms = [term_time_after(y, lam) for lam in JIE_LAMBDA]
    if jd < terms[0]:
        # 立春前：属上年末月——小寒前为子月，小寒至立春为丑月
        xiaohan_this = term_time_after(y, 285.0)
        if jd < xiaohan_this:
            month_zhi, offset = 0, 10   # 子月（大雪～小寒）
        else:
            month_zhi, offset = 1, 11   # 丑月（小寒～立春）
        month_gan = (HUTUN[year_gan % 5] + offset) % 10
    else:
        lichun_next = term_time_after(y + 1, 315.0)
        for i in range(12):
            nxt = terms[i + 1] if i < 11 else lichun_next
            if terms[i] <= jd < nxt:
                month_zhi = JIE_ZHI[i]
                month_gan = (HUTUN[year_gan % 5] + i) % 10
                break

    # 日柱
    day_seq = (int(jdn(y, m, d)) + 49) % 60
    day_gan, day_zhi = day_seq % 10, day_seq % 12

    # 时柱（23 点起为子时初；不换日，跨子时换日未内置，边界提醒）
    hour_zhi = ((h + 1) // 2) % 12
    hour_gan = (SHUTUN[day_gan % 5] + hour_zhi) % 10

    gan6 = [year_gan, month_gan, day_gan, hour_gan]
    zhi6 = [year_zhi, month_zhi, day_zhi, hour_zhi]

    # 输出
    if args.longitude is None:
        print("八字排盘（东八区民用时；未做真太阳时修正——可用 --longitude 经度修正，临界时间请人工复核）")
    else:
        print("八字排盘（已按 --longitude 做真太阳时修正；节气临界时间请人工复核）")
    print(f"公历: {y}年{m}月{d}日 {h}时")
    pillars = ["年柱", "月柱", "日柱", "时柱"]
    gans = "".join(TIAN_GAN[g] for g in gan6)
    zhis = "".join(DI_ZHI[z] for z in zhi6)
    print(f"四柱: {gans} {zhis}")
    print("      " + " ".join(pillars))
    for i, g in enumerate(gan6):
        tg = ten_god(day_gan, g)
        cg = CANG_GAN[DI_ZHI[zhi6[i]]]
        print(f"{pillars[i]}: 干{TIAN_GAN[g]}({GAN_WUXING[g]}·{'阳' if GAN_YINYANG[g]==0 else '阴'}) "
              f"{'日主' if i==2 else tg}  支{DI_ZHI[zhi6[i]]}({ZHI_WUXING[zhi6[i]]}·{'阳' if ZHI_YINYANG[zhi6[i]]==0 else '阴'}) "
              f"藏干[{cg}]")
    # 年柱纳音：60 甲子序号//2 查 30 纳音（每两个干支同一纳音）。
    # 修正：原 `((year_gan*2)%10*12+year_zhi)//2` 在癸年越界且多数干支算错
    # （如 1985 乙丑 被算成 霹雳火，实为 海中金）。
    nayin_seq = ((year_gan * 6 - year_zhi * 5) % 60) // 2
    print(f"年柱纳音: {NAYIN[nayin_seq]}")
    # 五行统计（四干 + 支主气）
    from collections import Counter
    c = Counter(GAN_WUXING[g] for g in gan6)
    c.update(ZHI_WUXING[z] for z in zhi6)
    total = sum(c.values())
    stat = " ".join(f"{w}{c.get(w, 0)}" for w in "木火土金水")
    print(f"五行统计(干支主气, 共{total}): {stat}")
    cc = Counter(GAN_WUXING[g] for g in gan6)
    for z in zhi6:
        cc.update(GAN_WUXING[TIAN_GAN.index(c)] for c in CANG_GAN[DI_ZHI[z]])
    stat2 = " ".join(f"{w}{cc.get(w, 0)}" for w in "木火土金水")
    print(f"五行统计(含藏干): {stat2}")
    # 月令信息（供断旺衰）
    print(f"月令: {DI_ZHI[month_zhi]}月（{JIE_ZHI.index(month_zhi)+1}/12 节序，当令五行 {ZHI_WUXING[month_zhi]}）")

    # 大运排布（--gender 时输出；确定性计算，禁止人工推排）
    if args.gender:
        forward, yun_years, yun_months, qiyun_jd, steps = da_yun(
            year_gan, month_gan, month_zhi, jd, args.gender, terms)
        qy, qm, _ = jd_to_date(qiyun_jd)
        print(f"大运(渊海子平《论起大运》·月柱{TIAN_GAN[month_gan]}{DI_ZHI[month_zhi]}起"
              f"{'顺' if forward else '逆'}推,十年一步):")
        print(f"  起运: 约 {yun_years} 岁 {yun_months} 个月(约 {qy} 年 {qm} 月)")
        today_jd = None
        if args.today:
            ty, tm, td = args.today
            if not (1900 <= ty <= 2100):
                print("today 越界: 年份须在 1900-2100", file=sys.stderr)
                sys.exit(1)
            today_jd = float(jdn(ty, tm, td)) + 0.5
        for i, (g, z) in enumerate(steps):
            s0 = qiyun_jd + i * 10 * 365.25
            s1 = s0 + 10 * 365.25
            y0, m0, _ = jd_to_date(s0)
            y1, m1, _ = jd_to_date(s1)
            cur = "   ← 当前" if (today_jd and s0 <= today_jd < s1) else ""
            print(f"  {i+1}. {TIAN_GAN[g]}{DI_ZHI[z]}  {y0}.{m0} – {y1}.{m1}{cur}")
    # 节气边界提醒（阈值读 config.yaml，回退 1 天）
    tol = load_config()["term_tolerance_days"]
    for i, t in enumerate(terms):
        if abs(jd - t) <= tol:
            print(f"[提醒] 出生时刻距{['立春','惊蛰','清明','立夏','芒种','小暑','立秋','白露','寒露','立冬','大雪','小寒'][i]}节 {abs(jd-t)*24:.0f} 小时，边界请复核")
    if abs(jd - lichun_this) <= tol:
        print(f"[提醒] 出生时刻距立春 {abs(jd-lichun_this)*24:.0f} 小时，年柱边界请复核")


if __name__ == "__main__":
    main()
