"""六爻引擎包装 —— 复用 xuan-shu/scripts/liuyao.py 的装卦逻辑。

脚本 main() 内联了完整装卦流程；本包装按同一算法顺序调用其模块级
数据表与函数（TRIGRAM / HEX_MAP / najia_lines / liuqin / waxiang）组装结构化结果。
"""
from __future__ import annotations

import datetime
import random
from typing import Any

from mingli.engines.loader import load_engine


def _cast_lines(
    coins: list[int] | None = None,
    numbers: list[int] | None = None,
    time_input: list[int] | None = None,
    use_random: bool = False,
    seed: int | None = None,
    zi_as_yang: bool = False,
) -> tuple[list[int], list[int], str]:
    """起卦 → (六爻 0/1 自下而上, 动爻列表, 来源描述)。算法同 liuyao.py main()。"""
    ly = load_engine("liuyao")
    if coins is not None:
        if len(coins) != 6 or any(not 0 <= n <= 3 for n in coins):
            raise ValueError("铜钱摇卦需要 6 个数，每爻'背'的个数 0-3（自下而上）")
        lines, moving = [], []
        for i, nbei in enumerate(coins):
            nyang = (3 - nbei) if zi_as_yang else nbei
            lines.append(1 if nyang in (1, 3) else 0)
            if nyang in (0, 3):
                moving.append(i + 1)
        src = f"铜钱摇卦 背数(初→上)={coins}" + (" [字=阳变体]" if zi_as_yang else " [字=阴、背=阳]")
        return lines, moving, src
    if numbers is not None:
        nums = numbers
        if len(nums) not in (2, 3):
            raise ValueError("报数起卦需要 2 或 3 个数")
        upper = nums[0] % 8 or 8
        lower = nums[1] % 8 or 8
        dong = (nums[2] if len(nums) == 3 else nums[0] + nums[1]) % 6 or 6
        lines = list(ly.TRIGRAM[lower][7]) + list(ly.TRIGRAM[upper][7])
        src = f"报数 {nums} → 上{ly.TRIGRAM[upper][0]} 下{ly.TRIGRAM[lower][0]} 动第{dong}爻"
        return lines, [dong], src
    if time_input is not None:
        yz, m, d, h = time_input
        base = yz + m + d
        upper = base % 8 or 8
        lower = (base + h) % 8 or 8
        dong = (base + h) % 6 or 6
        lines = list(ly.TRIGRAM[lower][7]) + list(ly.TRIGRAM[upper][7])
        src = f"农历时间 年支序{yz} 月{m} 日{d} 时辰序{h} → 上{ly.TRIGRAM[upper][0]} 下{ly.TRIGRAM[lower][0]} 动第{dong}爻"
        return lines, [dong], src
    if use_random:
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        tosses = [sum(rng.randrange(2) for _ in range(3)) for _ in range(6)]
        lines, moving = [], []
        for nbei in tosses:
            nyang = 3 - nbei if zi_as_yang else nbei
            lines.append(1 if nyang in (1, 3) else 0)
            if nyang in (0, 3):
                moving.append(len(lines))
        rand_src = f"seed={seed}" if seed is not None else "secrets"
        src = f"脚本模拟摇卦 背数(初→上)={tosses} [随机源: {rand_src}]"
        return lines, moving, src
    raise ValueError("必须提供起卦方式：coins / numbers / time / random")


def liuyao_calculate(
    *,
    mode: str | None = None,
    date: tuple[int, int, int] | None = None,
    coins: list[int] | None = None,
    numbers: list[int] | None = None,
    time_input: list[int] | None = None,
    use_random: bool = False,
    seed: int | None = None,
    zi_as_yang: bool = False,
) -> dict[str, Any]:
    """六爻装卦 → 结构化结果。装卦算法与 liuyao.py 完全一致。

    mode 为 "coins"/"numbers"/"time"/"random" 时按 mode 分发；
    不传 mode 时沿用旧签名（显式传 coins/numbers/time_input/use_random）。
    """
    ly = load_engine("liuyao")
    common = load_engine("common")

    if mode == "random":
        use_random = True
        coins = numbers = time_input = None
    elif mode == "coins":
        use_random, numbers, time_input = False, None, None
    elif mode == "numbers":
        use_random, coins, time_input = False, None, None
    elif mode == "time":
        use_random, coins, numbers = False, None, None
    lines, moving, src = _cast_lines(coins, numbers, time_input, use_random, seed, zi_as_yang)

    # 起卦日期 → 日干支/月建（默认今天）
    if date is not None:
        ty, tm_, td = date
        if not (1900 <= ty <= 2100):
            raise ValueError("date 年份须在 1900-2100")
    else:
        today = datetime.date.today()
        ty, tm_, td = today.year, today.month, today.day
    dgan, dzhi = common.day_ganzhi(ty, tm_, td)
    jd = float(common.jdn(ty, tm_, td)) + 0.5
    _, _, _, month_zhi = common.year_month_ganzhi(jd)
    empty = common.xunkong(dgan, dzhi)
    month_wx = common.zhi_wuxing(month_zhi)
    po = (month_zhi + 6) % 12

    najia, lower_tri, upper_tri = ly.najia_lines(lines)
    gua_name, palace, shi = ly.HEX_MAP[(upper_tri, lower_tri)]
    ying = ((shi - 1 + 3) % 6) + 1
    pw = ly.PALACE_WUXING[palace]

    flipped = list(lines)
    for mv in moving:
        flipped[mv - 1] = 1 - flipped[mv - 1]
    bian_lower = ly.LINES_TO_NUM[tuple(flipped[0:3])]
    bian_upper = ly.LINES_TO_NUM[tuple(flipped[3:6])]
    bian_name = ly.HEX_MAP[(bian_upper, bian_lower)][0]
    bian_najia, _, _ = ly.najia_lines(flipped)

    def line_dict(pos: int) -> dict[str, Any]:
        yao = pos + 1
        gan, zhi = najia[pos]
        qin = ly.liuqin(pw, common.zhi_wuxing(zhi))
        shen = ly.LIUSHEN_ORDER[(ly.LIUSHEN_ORDER.index(ly.LIUSHEN_START[dgan]) + pos) % 6]
        wx_state = ly.waxiang(common.zhi_wuxing(zhi), month_wx)
        marks = []
        if zhi in empty:
            marks.append("旬空")
        if zhi == po:
            marks.append("月破")
        if zhi == month_zhi:
            marks.append("值月建")
        if zhi == dzhi:
            marks.append("值日辰")
        bian = None
        if yao in moving:
            bgan, bzhi = bian_najia[pos]
            bqin = ly.liuqin(pw, common.zhi_wuxing(bzhi))
            bian = {"ganZhi": bgan + pp_zhi(bzhi), "liuqin": bqin}
        return {
            "position": yao,
            "najia": gan + pp_zhi(zhi),
            "zhiWuxing": common.zhi_wuxing(zhi),
            "liuqin": qin,
            "liushen": shen,
            "role": "世" if yao == shi else ("应" if yao == ying else ""),
            "moving": yao in moving,
            "wangShuai": wx_state,
            "marks": marks,
            "bianYao": bian,
        }

    def pp_zhi(z: int) -> str:
        return load_engine("common").DI_ZHI[z]

    # 伏神：本卦缺的六亲从本宫首卦取
    liuqing_set = {line_dict(p)["liuqin"] for p in range(6)}
    fushen = []
    missing = [q for q in ly.LIUQIN_DEFS if q not in liuqing_set]
    if missing:
        fu, fl = ly.PALACE_FIRST[palace]
        fu_lines = list(ly.TRIGRAM[fl][7]) + list(ly.TRIGRAM[fu][7])
        fu_najia, _, _ = ly.najia_lines(fu_lines)
        for q in missing:
            for pos in range(6):
                fgan, fzhi = fu_najia[pos]
                if ly.liuqin(pw, load_engine("common").zhi_wuxing(fzhi)) == q:
                    fushen.append({
                        "liuqin": q,
                        "position": pos + 1,
                        "najia": fgan + load_engine("common").DI_ZHI[fzhi],
                    })
                    break

    return {
        "qiGuaSource": src,
        "date": f"{ty}-{tm_:02d}-{td:02d}",
        "dayGanZhi": load_engine("common").TIAN_GAN[dgan] + load_engine("common").DI_ZHI[dzhi],
        "yueJian": {"zhi": load_engine("common").DI_ZHI[month_zhi], "wuxing": month_wx},
        "yuePo": load_engine("common").DI_ZHI[po],
        "xunKong": [load_engine("common").DI_ZHI[e] for e in empty],
        "benGua": {"name": gua_name, "palace": palace, "palaceWuxing": pw,
                   "shiYao": shi, "yingYao": ying,
                   "lines": [line_dict(p) for p in range(6)]},
        "bianGua": {"name": bian_name, "changed": bool(moving)},
        "fuShen": fushen,
    }
