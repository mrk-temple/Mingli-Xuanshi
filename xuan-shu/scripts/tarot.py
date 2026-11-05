#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tarot.py —— 塔罗抽牌（确定性算法部分：只负责"抽到哪几张牌"，不做解读）。

用法:
    python3 scripts/tarot.py --spread single                  # 单张
    python3 scripts/tarot.py --spread three                   # 三张（过去-现在-未来）
    python3 scripts/tarot.py --spread celtic                  # 凯尔特十字（10 张）
    python3 scripts/tarot.py --spread three --seed 42         # 固定种子（可复现/测试）
    python3 scripts/tarot.py --spread celtic --no-reversals   # 不抽逆位（全部按正位读）

原理:
    - 78 张牌（RWS 韦特体系，8=力量、11=正义），大阿卡纳 22 + 小阿卡纳 56（4 花色×14）
    - Fisher-Yates 洗牌 + secrets 密码学随机（给定 --seed 时用 random.Random 可复现）
    - 不放回抽牌（同一副牌内不重复）；每张牌独立 50/50 正逆位（--no-reversals 关闭）
    - 输出含每张牌的正逆位关键词提示（大阿卡纳逐张、小阿卡纳按花色主题+数字位阶+宫廷角色）；
      完整牌义与解读流程见 references/tarot-guide.md 与 references/tarot-meanings.md
    - 本脚本只输出"事实"；吉凶倾向与建议是解读（LLM 按 references 执行）

设计声明（元素对应）:
    - 西方四元素为牌的本位：权杖=火、圣杯=水、宝剑=风、星币=土（牌库字段原样保留）
    - 东学五行映射为后天 syncretic 对应，版本声明见 references/tarot-guide.md（不在本脚本硬编码）
"""
import argparse
import random
import secrets
import sys

try:  # Windows 控制台/管道编码统一为 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 大阿卡纳：编号, 中文名, 英文名, 正位关键词, 逆位关键词
MAJOR = [
    (0, "愚者", "The Fool", "新开始、纯真、冒险、自由", "鲁莽、停滞、犹豫不决"),
    (1, "魔术师", "The Magician", "意志力、创造力、显化、资源在手", "操纵、潜能未用、口是心非"),
    (2, "女祭司", "The High Priestess", "直觉、潜意识、内省、秘而未宣", "忽视直觉、秘密、表层化"),
    (3, "皇后", "The Empress", "丰饶、滋养、母性、感官富足", "依赖、创造力受阻、失衡"),
    (4, "皇帝", "The Emperor", "权威、结构、秩序、掌控", "专制、僵化、滥用权力"),
    (5, "教皇", "The Hierophant", "传统、导师、信仰、制度", "反叛、非正统、教条"),
    (6, "恋人", "The Lovers", "爱、结合、价值观抉择", "失衡、疏离、错误选择"),
    (7, "战车", "The Chariot", "意志、胜利、前进、自律", "失控、方向迷失、原地打转"),
    (8, "力量", "Strength", "勇气、耐心、以柔克刚", "自我怀疑、软弱、内耗"),
    (9, "隐士", "The Hermit", "内省、独处、寻求真理", "孤立、逃避、故步自封"),
    (10, "命运之轮", "Wheel of Fortune", "转机、周期、命运流转", "时运不济、抗拒变化"),
    (11, "正义", "Justice", "公平、因果、真相、平衡", "不公、逃避责任、偏颇"),
    (12, "倒吊人", "The Hanged Man", "换位思考、牺牲、以退为进", "无谓牺牲、拖延、卡住"),
    (13, "死神", "Death", "结束、转变、重生", "抗拒改变、停滞、拖泥带水"),
    (14, "节制", "Temperance", "平衡、调和、耐心、中道", "失衡、过度、急躁"),
    (15, "恶魔", "The Devil", "束缚、欲望、沉迷、阴影", "解脱、觉醒、挣脱枷锁"),
    (16, "高塔", "The Tower", "骤变、崩塌、真相震醒", "勉强维持、推迟的崩塌"),
    (17, "星星", "The Star", "希望、疗愈、灵感、指引", "失望、失去信心、迷茫"),
    (18, "月亮", "The Moon", "幻觉、不安、潜意识浮现", "真相浮出、焦虑缓解"),
    (19, "太阳", "The Sun", "喜悦、成功、活力、光明", "暂时的阴霾、过度乐观"),
    (20, "审判", "Judgement", "觉醒、召唤、重生、复盘评估", "自我怀疑、拒绝召唤"),
    (21, "世界", "The World", "完成、圆满、整合、闭环", "未竟之事、闭环未合"),
]

# 小阿卡纳：花色 → (中文, 英文, 西方元素, 主题关键词)
SUITS = {
    "wands": ("权杖", "Wands", "火", "行动、激情、意志、创造力、事业冲劲"),
    "cups": ("圣杯", "Cups", "水", "情感、关系、直觉、潜意识、爱"),
    "swords": ("宝剑", "Swords", "风", "思想、理智、沟通、冲突、真相（偏冷/锋锐）"),
    "pentacles": ("星币", "Pentacles", "土", "物质、金钱、身体、工作、稳定"),
}
SUIT_ORDER = ["wands", "cups", "swords", "pentacles"]

# 数字位阶通用骨架（Ace=1..10）
RANK_THEMES = {
    1: "新开始、纯粹潜力的种子",
    2: "平衡、二元、结合或抉择",
    3: "成长、初结果实、协作",
    4: "稳定、结构、休整",
    5: "冲突、动荡、挑战、失落",
    6: "和谐、修复、给予与获得",
    7: "评估、坚持、内省",
    8: "行动、移动、掌控（花色分化明显：权杖8=快进，宝剑8=束缚，圣杯8=离开，星币8=技艺打磨）",
    9: "接近完成、满足或焦虑（圣杯9=愿望达成，宝剑9=噩梦焦虑）",
    10: "完成、满溢、终结与轮回",
}
RANK_NAMES = {1: "Ace", **{n: str(n) for n in range(2, 11)}}

# 宫廷牌：角色 → (中文, 英文, 含义)
COURT = [
    ("page", "侍从", "Page", "学徒、消息、好奇心、学习的开端"),
    ("knight", "骑士", "Knight", "行动、追求、冲劲、极端化（该花色的行动者）"),
    ("queen", "王后", "Queen", "内在掌控、滋养、成熟的阴性能量"),
    ("king", "国王", "King", "外在掌控、权威、成熟的阳性能量"),
]

# 牌阵：name → [(位置标签, 位置含义)]
SPREADS = {
    "single": [("核心指引", "聚焦问题 / 当日主题 / 一句话指引")],
    "three": [
        ("过去", "事情的来路与已形成的因"),
        ("现在", "当前的状态与能量焦点"),
        ("未来", "按现有趋势的走向"),
    ],
    "celtic": [
        ("现状/核心", "问题的核心"),
        ("眼前的挑战", "横跨之牌：助力或阻力"),
        ("根基/潜意识", "深层动因"),
        ("较远的过去", "远因"),
        ("目标/理想", "有意识的目标与最佳可能走向"),
        ("近期未来", "即将展开的势"),
        ("你的态度", "自我视角"),
        ("外部环境", "他人影响"),
        ("希望与恐惧", "内心的渴望与担忧"),
        ("最终结果", "综合趋势"),
    ],
}


def build_deck():
    """78 张牌: [ (牌id, 中文全名, 英文全名, 组别, 元素/花色, 正位提示, 逆位提示) ]"""
    deck = []
    for num, zh, en, up, rev in MAJOR:
        deck.append((f"MAJ{num:02d}", zh, en, "大阿卡纳", "—", up, rev))
    for suit in SUIT_ORDER:
        szh, sen, elem, theme = SUITS[suit]
        for n in range(1, 11):
            deck.append((f"{suit.upper()}{n:02d}", f"{szh}{RANK_NAMES[n]}", f"{RANK_NAMES[n]} of {sen}",
                         "小阿卡纳", elem, theme + "；数字位阶：" + RANK_THEMES[n], "能量受阻/内在化，或主题过度"))
        for role, czh, cen, cmeaning in COURT:
            deck.append((f"{suit.upper()}{role.upper()}", f"{szh}{czh}", f"{cen} of {sen}",
                         "小阿卡纳", elem, cmeaning, "该特质过度或受抑"))
    return deck


def main():
    ap = argparse.ArgumentParser(description="塔罗抽牌（确定性算法，不含解读）")
    ap.add_argument("--spread", choices=sorted(SPREADS), required=True, help="牌阵：single/three/celtic")
    ap.add_argument("--seed", type=int, help="固定随机种子（可复现；默认密码学真随机）")
    ap.add_argument("--no-reversals", action="store_true", help="不抽逆位（所有牌按正位读）")
    args = ap.parse_args()

    deck = build_deck()
    positions = SPREADS[args.spread]
    n = len(positions)
    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()

    # Fisher-Yates 洗牌（原位洗、无偏）
    for i in range(len(deck) - 1, 0, -1):
        j = rng.randrange(i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    picked = deck[:n]  # 不放回：前 n 张
    rnd_src = f"seed={args.seed}" if args.seed is not None else "secrets 密码学随机"

    print(f"塔罗抽牌结果（由脚本抽取，勿人工复抽）  [牌阵: {args.spread} / 随机源: {rnd_src}]")
    if args.no_reversals:
        print("[无逆位模式] 全部按正位解读")
    for (label, meaning), card in zip(positions, picked):
        cid, zh, en, group, elem, up, rev = card
        if args.no_reversals:
            orient, hint = "正位", up
        else:
            orient, hint = ("逆位", rev) if rng.random() < 0.5 else ("正位", up)
        print(f"{label}（{meaning}）: {zh} {en}（{orient}） [{group}{'·元素' + elem if elem != '—' else ''}]")
        print(f"  关键词提示: {hint}")
    if not args.seed:
        print("[注] 结果每次运行不同；如需复核同一结果，可加 --seed N 重放")


if __name__ == "__main__":
    main()
