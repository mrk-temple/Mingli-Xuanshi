"""引擎确定性测试 —— 同输入同输出、边界日期、节气、时区/子时、seed 复现、非法输入。

对照基准：xuan-shu/scripts CLI 输出（golden 快照 + 已知正确值）。
"""
from __future__ import annotations

import pytest

from mingli.engines import bazi, daliuren, liuyao, meihua, tarot, xiaoliuren, yijing

# ---------------------------------------------------------------------------
# 八字
# ---------------------------------------------------------------------------

class TestBazi:
    def test_known_chart(self):
        """1985-08-11 15 时：乙丑 甲申 壬午 戊申（与 paipan.py CLI 交叉核对）。"""
        r = bazi.bazi_calculate(1985, 8, 11, 15)
        assert r["siZhu"] == "乙甲壬戊 丑申午申"
        assert r["columns"][2]["gan"] == "壬"
        assert r["columns"][2]["shiShen"] == "日主"
        assert r["nayinYear"] == "海中金"   # 乙丑纳音（修正后的正确值）

    def test_deterministic(self):
        a = bazi.bazi_calculate(1990, 6, 15, 8, gender="男")
        b = bazi.bazi_calculate(1990, 6, 15, 8, gender="男")
        assert a["siZhu"] == b["siZhu"]
        assert a["daYun"]["steps"] == b["daYun"]["steps"]

    def test_lichun_boundary(self):
        """立春前后年柱不同（以本引擎=Meeus 近似立春为基准，约 2024-02-03 08h）。"""
        before = bazi.bazi_calculate(2024, 2, 2, 10)   # 立春前 → 癸卯年
        after = bazi.bazi_calculate(2024, 2, 4, 10)    # 立春后 → 甲辰年
        assert before["columns"][0]["gan"] == "癸"
        assert after["columns"][0]["gan"] == "甲"

    def test_zishi_no_day_rollover(self):
        """23 点为子时初；本引擎不跨日换日（与 paipan.py 一致），日柱按当日。"""
        d1 = bazi.bazi_calculate(2000, 1, 1, 22)   # 亥时
        d2 = bazi.bazi_calculate(2000, 1, 1, 23)   # 子时初
        assert d1["columns"][3]["zhi"] == "亥"
        assert d2["columns"][3]["zhi"] == "子"
        # 日柱相同（跨子时不换日）
        assert d1["columns"][2]["gan"] == d2["columns"][2]["gan"]
        assert d1["columns"][2]["zhi"] == d2["columns"][2]["zhi"]

    def test_term_warning_near_jieqi(self):
        """出生时刻贴近起算节气 → 警告必须出现（config 阈值 1 天）。"""
        r = bazi.bazi_calculate(2024, 2, 3, 12)  # 贴近脚本近似立春（约 02-03 08:32）
        assert any("边界" in w or "复核" in w for w in r.get("warnings", []))

    def test_longitude_correction(self):
        fix = bazi.bazi_calculate(1990, 1, 1, 3, longitude=80.0)
        # 默认东八区未修正；西部经度修正会推后真太阳时，可能改变时柱
        assert fix["longitude"] == 80.0
        assert "trueSolarTimeApplied" in fix and fix["trueSolarTimeApplied"]

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            bazi.bazi_calculate(1800, 1, 1, 0)
        with pytest.raises(ValueError):
            bazi.bazi_calculate(2000, 13, 1, 0)
        with pytest.raises(ValueError):
            bazi.bazi_calculate(2000, 1, 1, 24)

    def test_dayun_direction(self):
        """阳年男顺排、阴年男逆排。1985 乙丑（阴年）男命应逆排。"""
        r = bazi.bazi_calculate(1985, 8, 11, 15, gender="男")
        assert r["daYun"]["forward"] is False


# ---------------------------------------------------------------------------
# 六爻
# ---------------------------------------------------------------------------

class TestLiuyao:
    def test_coins_deterministic(self):
        a = liuyao.liuyao_calculate(mode="coins", coins=[2, 3, 2, 1, 3, 0])
        b = liuyao.liuyao_calculate(mode="coins", coins=[2, 3, 2, 1, 3, 0])
        assert a["benGua"]["name"] == b["benGua"]["name"]

    def test_coins_moving_lines(self):
        """背数 3 = 老阳动；0 = 老阴动；1/2 静。"""
        r = liuyao.liuyao_calculate(mode="coins", coins=[3, 0, 1, 2, 1, 2])
        moving = [yao["position"] for yao in r["benGua"]["lines"] if yao["moving"]]
        assert moving == [1, 2]

    def test_seed_reproducible(self):
        a = liuyao.liuyao_calculate(mode="random", seed=42)
        b = liuyao.liuyao_calculate(mode="random", seed=42)
        assert [yao["najia"] for yao in a["benGua"]["lines"]] == [
            yao["najia"] for yao in b["benGua"]["lines"]]
        assert a["qiGuaSource"] == b["qiGuaSource"]

    def test_numbers_gua(self):
        """报数 3 7 → 上离(dong=0→3)下艮(7) 火山旅；动爻 (3+7)%6=4。"""
        r = liuyao.liuyao_calculate(mode="numbers", numbers=[3, 7])
        assert r["benGua"]["name"] == "火山旅"
        assert r["benGua"]["lines"][3]["moving"] is True

    def test_invalid_coins(self):
        with pytest.raises(ValueError):
            liuyao._cast_lines(coins=[1, 2, 3, 4, 5, 6])  # 4 越界
        with pytest.raises(ValueError):
            liuyao._cast_lines(coins=[1, 2])

    def test_shiying_pairing(self):
        """世应永远相隔三位。"""
        r = liuyao.liuyao_calculate(mode="numbers", numbers=[1, 1])
        shi = r["benGua"]["shiYao"]
        ying = r["benGua"]["yingYao"]
        assert abs(shi - ying) == 3


# ---------------------------------------------------------------------------
# 梅花
# ---------------------------------------------------------------------------

class TestMeihua:
    def test_numbers(self):
        r = meihua.meihua_calculate(numbers=[3, 7])
        assert r["benGua"]["name"] == "火山旅"   # 上离下艮
        assert r["movingLine"] == 4              # (3+7)%6

    def test_lunar(self):
        r = meihua.meihua_calculate(lunar=[6, 3, 9, 7])
        assert r["movingLine"] in range(1, 7)

    def test_ti_yong_rule(self):
        """动爻在下卦（≤3）→ 用=下卦体=上卦；>3 反之。"""
        r = meihua.meihua_calculate(numbers=[3, 7])
        if r["movingLine"] <= 3:
            assert r["tiYong"]["use"]["trigram"] == r["benGua"]["lowerName"]
        else:
            assert r["tiYong"]["use"]["trigram"] == r["benGua"]["upperName"]

    def test_solar_requires_dep_or_error(self):
        try:
            meihua.meihua_calculate(solar=[2026, 8, 11, 15])
        except RuntimeError as e:
            assert "lunar_python" in str(e)

    def test_invalid(self):
        with pytest.raises(ValueError):
            meihua.meihua_calculate(numbers=[1])
        with pytest.raises(ValueError):
            meihua.meihua_calculate(lunar=[1, 2])


# ---------------------------------------------------------------------------
# 小六壬
# ---------------------------------------------------------------------------

class TestXiaoliuren:
    def test_gufa_formula(self):
        """古法断宫 = (m+d+h-3)%6+1。3+5+6=14 → (14-3)%6+1=6 空亡。"""
        r = xiaoliuren.xiaoliuren_calculate(lunar=[3, 5, 6])
        assert r["duanGong"]["name"] == "空亡"
        assert r["yueGong"]["name"] == "速喜"   # 3 月
        assert r["riGong"]["name"] == "大安"     # 3+5=8 → (8-2)%6+1=1

    def test_sum_mode_offset(self):
        g = xiaoliuren.xiaoliuren_calculate(lunar=[3, 5, 6], sum_mode=False)
        s = xiaoliuren.xiaoliuren_calculate(lunar=[3, 5, 6], sum_mode=True)
        assert s["sumMode"] and not g["sumMode"]
        # 两法相差固定 2 位
        names = list(load_palaces())
        gi = names.index(g["duanGong"]["name"])
        si = names.index(s["duanGong"]["name"])
        assert (si - gi) % 6 == 2

    def test_invalid_range(self):
        with pytest.raises(ValueError):
            xiaoliuren.xiaoliuren_calculate(lunar=[0, 5, 6])
        with pytest.raises(ValueError):
            xiaoliuren.xiaoliuren_calculate(lunar=[3, 31, 6])
        with pytest.raises(ValueError):
            xiaoliuren.xiaoliuren_calculate(lunar=[3, 5, 13])

    def test_solar_requires_dep_or_error(self):
        try:
            xiaoliuren.xiaoliuren_calculate(solar=[2026, 8, 11, 15])
        except RuntimeError as e:
            assert "lunar_python" in str(e)


def load_palaces():
    from mingli.engines.loader import load_engine
    return [load_engine("xiaoliuren").PALACES[i][0] for i in range(1, 7)]  # 有序宫名


# ---------------------------------------------------------------------------
# 大六壬
# ---------------------------------------------------------------------------

class TestDaliuren:
    def test_datetime_basic(self):
        r = daliuren.daliuren_calculate(datetime_input=[2026, 8, 11, 15])
        assert len(r["tianDiPan"]["tianPan"]) == 12
        assert len(r["siKe"]) == 4
        assert len(r["sanChuan"]) == 3
        assert r["keTi"]

    def test_manual_matches_cli_example(self):
        """手工课例（daliuren.py --manual 甲子 午 亥）应有完整结构。"""
        r = daliuren.daliuren_calculate(manual=("甲子", "午", "亥"))
        assert r["dayGanZhi"] == "甲子"
        assert r["zhanShi"] == "午"
        assert r["yueJiang"]["zhi"] == "亥"

    def test_fuyin_detection(self):
        """月将==占时 → 伏吟课。"""
        r = daliuren.daliuren_calculate(manual=("甲子", "亥", "亥"))
        assert "伏吟" in r["keTi"]

    def test_fanyin_detection(self):
        """月将==占时+6 → 返吟课。"""
        r = daliuren.daliuren_calculate(manual=("甲子", "亥", "巳"))
        assert "返吟" in r["keTi"]

    def test_deterministic(self):
        a = daliuren.daliuren_calculate(datetime_input=[2026, 8, 11, 15])
        b = daliuren.daliuren_calculate(datetime_input=[2026, 8, 11, 15])
        assert a == b

    def test_invalid(self):
        with pytest.raises(ValueError):
            daliuren.daliuren_calculate(datetime_input=[1800, 1, 1, 0])
        with pytest.raises(ValueError):
            daliuren.daliuren_calculate(manual=("洋子", "午", "亥"))


# ---------------------------------------------------------------------------
# 塔罗
# ---------------------------------------------------------------------------

class TestTarot:
    def test_seed_reproducible(self):
        a = tarot.tarot_calculate(spread="three", seed=42)
        b = tarot.tarot_calculate(spread="three", seed=42)
        assert a["cards"] == b["cards"]

    def test_no_replacement(self):
        """同一副牌内不重复。"""
        r = tarot.tarot_calculate(spread="celtic", seed=7)
        ids = [c["cardId"] for c in r["cards"]]
        assert len(ids) == len(set(ids)) == 10

    def test_spread_sizes(self):
        assert len(tarot.tarot_calculate(spread="single")["cards"]) == 1
        assert len(tarot.tarot_calculate(spread="three")["cards"]) == 3
        assert len(tarot.tarot_calculate(spread="celtic")["cards"]) == 10

    def test_no_reversals_flag(self):
        r = tarot.tarot_calculate(spread="three", seed=42, no_reversals=True)
        assert all(not c["reversed"] for c in r["cards"])

    def test_position_order_preserved(self):
        """牌阵顺序与 SPREADS 定义一致（洗牌不改变位置标签顺序）。"""
        r = tarot.tarot_calculate(spread="celtic", seed=1)
        labels = [c["position"] for c in r["cards"]]
        assert labels[0] == "现状/核心"
        assert labels[-1] == "最终结果"

    def test_deck_integrity(self):
        """78 张 RWS：22 大阿卡纳 + 56 小阿卡纳。"""
        from mingli.engines.loader import load_engine
        deck = load_engine("tarot").build_deck()
        assert len(deck) == 78
        majors = [c for c in deck if c[0].startswith("MAJ")]
        assert len(majors) == 22
        # 8=力量 11=正义（RWS 版本声明）
        by_id = {c[0]: c for c in deck}
        assert by_id["MAJ08"][1] == "力量"
        assert by_id["MAJ11"][1] == "正义"

    def test_invalid_spread(self):
        with pytest.raises(ValueError):
            tarot.tarot_calculate(spread="horseshoe")


# ---------------------------------------------------------------------------
# 易经义理
# ---------------------------------------------------------------------------

class TestYijing:
    def test_known_hexagram(self):
        r = yijing.yijing_calculate(gua_name="地山谦")
        assert r["guaName"] == "地山谦"
        assert len(r["lines"]) == 6

    def test_all_64_names_resolve(self):
        from mingli.engines.loader import load_engine
        qg = load_engine("qigua")
        for up in range(1, 9):
            for low in range(1, 9):
                name = qg.gua_name(up, low)
                r = yijing.yijing_calculate(gua_name=name)
                assert r["guaName"] == name

    def test_invalid_name(self):
        with pytest.raises(ValueError):
            yijing.yijing_calculate(gua_name="不存在卦")
