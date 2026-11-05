"""Web 层集成测试 —— vertical slice 全链路（httpx TestClient）。"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """隔离数据目录的测试客户端。"""
    monkeypatch.setenv("MINGLI_INTERPRETER", "rule-engine")
    import mingli.web.app as webapp
    session_mod = __import__("mingli.core.session", fromlist=["SessionStore"])
    webapp._sessions = session_mod.SessionStore(root=str(tmp_path / "sessions"))
    webapp._experiments = session_mod.ExperimentStore(root=str(tmp_path / "experiments"))
    webapp._profiles = session_mod.ProfileStore(root=str(tmp_path / "profiles"))
    monkeypatch.setattr(webapp, "_chats", session_mod.ChatStore(root=str(tmp_path / "chats")))
    from fastapi.testclient import TestClient
    return TestClient(webapp.app)


class TestVerticalSlice:
    def test_home(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "命理玄师" in r.text

    def test_systems_page_honest(self, client):
        r = client.get("/systems")
        assert r.status_code == 200
        assert "奇门遁甲" in r.text and "规划中" in r.text

    def test_ask_to_recommend(self, client):
        r = client.post("/ask", data={"text": "我该不该换工作？"}, follow_redirects=False)
        assert r.status_code == 200 or r.status_code == 307
        if r.status_code == 200:
            assert "匹配" in r.text

    def test_full_slice_liuyao(self, client):
        """问题 → 推荐 → 运行六爻 → 结果页 → 报告 → 实验记录。"""
        # 1. 推荐页
        rec = client.post("/ask", data={"text": "这次面试能不能过？"})
        assert rec.status_code == 200
        # 2. 直接运行六爻（模拟摇卦带 seed）
        run = client.post("/run/liuyao", data={"q": "这次面试能不能过？", "mode": "random", "seed": "42"},
                          follow_redirects=False)
        assert run.status_code == 303, run.text[:500]
        session_url = run.headers["location"]
        # 3. 结果页
        page = client.get(session_url)
        assert page.status_code == 200
        assert "原始盘面" in page.text          # 三层结构 Tab 之一
        assert "体系局限" in page.text
        assert "不构成医疗、投资、法律" in page.text
        sid = session_url.rsplit("/", 1)[-1]
        # 4. Markdown 报告
        md = client.get(f"/session/{sid}/report.md")
        assert md.status_code == 200
        assert "推理链" in md.text
        # 5. 创建实验并判定
        lab = client.post(f"/lab/new/{sid}", data={
            "prediction": "倾向能过但有反复",
            "window_start": "2026-09-01", "window_end": "2026-09-10"}, follow_redirects=False)
        assert lab.status_code == 303
        eid = lab.headers["location"].rsplit("/", 1)[-1]
        detail = client.get(f"/lab/{eid}")
        assert "裁定规则表" in detail.text   # 判定逻辑公开
        ev = client.post(f"/lab/{eid}/evaluate", data={
            "outcome": "过了", "hit_direction": "true", "hit_timing": "true"}, follow_redirects=False)
        assert ev.status_code == 303
        final = client.get(f"/lab/{eid}")
        assert "partial-hit" in final.text

    def test_bazi_slice(self, client):
        run = client.post("/run/bazi", data={"q": "", "year": "1985", "month": "8",
                                             "day": "11", "hour": "15", "gender": "男"},
                          follow_redirects=False)
        assert run.status_code == 303
        page = client.get(run.headers["location"])
        assert "乙甲壬戊" in page.text      # 四柱天干行
        assert "海中金" in page.text        # 纳音（修正后正确值）

    def test_invalid_input_shows_errors(self, client):
        r = client.post("/run/bazi", data={"q": "", "year": "1800", "month": "13", "day": "40"})
        assert r.status_code == 400

    def test_bazi_nonexistent_date_rejected(self, client):
        """1990-2-31 曾被静默折算成 3 月 3 日排出假盘——现在必须回表单报错。"""
        r = client.post("/run/bazi", data={"q": "", "year": "1990", "month": "2", "day": "31"})
        assert r.status_code == 400
        assert "不存在" in r.text

    def test_bazi_midnight_keeps_zishi(self, client):
        """0 点（子时）出生：时柱必须是子，不得被 falsy 兜底换成 12 点午时。"""
        run = client.post("/run/bazi", data={"q": "", "year": "1990", "month": "5",
                                             "day": "12", "hour": "0", "gender": "男"},
                          follow_redirects=False)
        assert run.status_code == 303
        sid = run.headers["location"].rsplit("/", 1)[-1]
        import mingli.web.app as _webapp
        s = _webapp._sessions.load(sid)
        assert s.calculation.data["columns"][3]["zhi"] == "子"

    def test_yijing_bad_gua_name_no_500(self, client):
        """坏卦名须回表单报错（此前 validate 空实现 → calculate 抛错 → 裸 500）。"""
        r = client.post("/run/yijing", data={"q": "", "guaName": "不存在的卦"})
        assert r.status_code == 400
        assert "未知卦名" in r.text

    def test_crisis_intercepted(self, client):
        r = client.post("/ask", data={"text": "我不想活了，帮我算算什么时候解脱"})
        assert "12356" in r.text

    def test_history(self, client):
        client.post("/run/tarot", data={"q": "测测", "spread": "three", "seed": "9"},
                    follow_redirects=False)
        h = client.get("/history")
        assert h.status_code == 200
        assert "打开" in h.text

    def test_compare_slice(self, client):
        """Same Question Lab：多体系独立起局 → 收敛/分歧/不可比较。"""
        form = client.get("/compare")
        assert form.status_code == 200
        assert "多体系对照" in form.text
        r = client.post("/compare", data={
            "q": "我该不该换工作？",
            "systems": ["liuyao", "xiaoliuren", "tarot"],
            "seed": "7",
        })
        assert r.status_code == 200
        body = r.text
        # 三体系各自起局：六爻/小六壬呈吉忌极性，塔罗为象征视角
        assert "六爻纳甲" in body and "小六壬" in body and "塔罗" in body
        # 对照结构存在：收敛点 / 分歧点 / 不可比较项 三区
        assert "收敛点" in body
        assert "分歧点" in body
        assert "不可比较项" in body
        # 红线：不得生成综合概率/百分比占比（"N 术一致故 92%" 式）
        import re
        assert not re.search(r"\d+\s*%", body), "对照页不得产出百分比占比"

    def test_compare_requires_system_and_question(self, client):
        r = client.post("/compare", data={"q": "换个城市", "systems": []})
        assert r.status_code == 200  # 表单带错误提示
        assert "至少选择一个" in r.text

    def test_lab_stats_page(self, client):
        r = client.get("/lab")
        assert r.status_code == 200
        assert "已判定" in r.text   # 统计区存在

    def test_compare_synthesis_degrades_without_key(self, client, monkeypatch):
        """无 key → 对照主表照常，综合区优雅提示，不产百分比。"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = client.post("/compare", data={"q": "我该不该换工作", "systems": ["liuyao", "xiaoliuren", "tarot"], "seed": "7"})
        assert r.status_code == 200
        assert "收敛点" in r.text                     # 对照主表正常
        assert "配置 ANTHROPIC_API_KEY" in r.text     # 综合区降级提示
        assert "%" not in r.text

    def test_compare_synthesis_renders_three_layers(self, client, monkeypatch):
        """有 key（注入 fake 输出）→ 综合区渲染三层，且不产百分比。"""
        import mingli.web.app as webapp
        monkeypatch.setattr(webapp, "llm_available", lambda: True)
        fake = {
            "responses": [{"systemId": "liuyao", "systemName": "六爻", "answer": "卦有反复，宜缓进。"}],
            "divergence": ["分歧说明"],
            "action": "一个月内观察是否有明确事态，作实验记录。",
            "notes": ["以上为解释性综合。"],
        }
        monkeypatch.setattr(webapp, "synthesize_with_llm", lambda q, cls, r, rules: fake)
        r = client.post("/compare", data={"q": "我该不该换工作", "systems": ["liuyao", "xiaoliuren", "tarot"], "seed": "7"})
        assert r.status_code == 200
        assert "各体系怎么说" in r.text
        assert "分歧怎么理解" in r.text
        assert "给你的行动建议" in r.text
        assert "%" not in r.text

    # ── 独立页面：综合分析 /analyze ──
    def test_analyze_form(self, client):
        r = client.get("/analyze")
        assert r.status_code == 200
        assert "综合分析" in r.text
        assert "发起综合分析" in r.text

    def test_analyze_degrades_without_key(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = client.post("/analyze", data={"q": "我该不该换城市", "systems": ["liuyao", "xiaoliuren", "tarot"], "seed": "7"})
        assert r.status_code == 200
        assert "基本盘" in r.text            # 确定性对照作支撑
        assert "配置 ANTHROPIC_API_KEY" in r.text
        assert "逐体系展开" in r.text
        assert "%" not in r.text

    def test_analyze_renders_three_layers(self, client, monkeypatch):
        import mingli.web.app as webapp
        monkeypatch.setattr(webapp, "llm_available", lambda: True)
        fake = {
            "responses": [{"systemId": "liuyao", "systemName": "六爻", "answer": "卦有反复，宜缓进。"}],
            "divergence": ["分歧说明"],
            "action": "一个月内观察是否有明确事态，作实验记录。",
            "notes": ["以上为解释性综合。"],
        }
        monkeypatch.setattr(webapp, "synthesize_with_llm", lambda q, cls, r, rules: fake)
        r = client.post("/analyze", data={"q": "我该不该换城市", "systems": ["liuyao", "xiaoliuren", "tarot"], "seed": "7"})
        assert r.status_code == 200
        assert "各体系怎么说" in r.text
        assert "分歧怎么理解" in r.text
        assert "给你的行动建议" in r.text
        assert "%" not in r.text

    def test_analyze_entry_in_sidebar_and_home(self, client):
        """综合分析入口应出现在生成空间的直达导航中。"""
        gen = client.get("/generate")
        assert "/analyze" in gen.text and "综合分析" in gen.text
        analyze = client.get("/analyze")
        assert analyze.status_code == 200

    # ── 盘局导出（人读报告 / AI 读数据）──
    def test_export_ai_json_structure(self, client):
        """导出 JSON 含盘面原始数据 + 结构化结论（可追溯）+ 免责，且无运势维度。"""
        run = client.post("/run/bazi", data={"q": "", "year": "2006", "month": "1", "day": "25",
                                             "hour": "20", "gender": "男", "longitude": "112"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        r = client.get(f"/session/{sid}/export.ai.json")
        assert r.status_code == 200
        j = r.json()
        assert j["kind"] == "mingli-xuanshi/divination-export"
        assert "columns" in j["calculation"]                 # 盘面原始数据
        assert j["meta"]["systemId"] == "bazi"
        assert j["conclusions"], "应含结构化结论"
        assert all(c.get("calcRefs") for c in j["conclusions"])  # 可追溯
        assert j["disclaimer"]
        # 维度已从解读层移除：结论不出现感情/财运/事业/学业
        for c in j["conclusions"]:
            assert not any(k in c["claim"] for k in ("感情", "财运", "事业", "学业"))

    def test_report_print_page(self, client):
        run = client.post("/run/tarot", data={"q": "测测", "spread": "three", "seed": "9"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        r = client.get(f"/session/{sid}/report")
        assert r.status_code == 200
        assert "盘局报告" in r.text and "@media print" in r.text

    def test_session_export_buttons(self, client):
        run = client.post("/run/tarot", data={"q": "测测", "spread": "three", "seed": "9"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        b = client.get(f"/session/{sid}").text
        assert f"/session/{sid}/report" in b and f"/session/{sid}/export.ai.json" in b

    # ── ask 推荐页 LLM 建议（可选插槽）──
    def test_ask_recommend_degrades_without_key(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = client.post("/ask", data={"text": "我该不该换工作"})
        assert r.status_code == 200
        assert "宜用盘局" in r.text          # 推荐主表照常
        assert "玄师建议" not in r.text      # 无建议段（降级）

    def test_ask_recommend_renders_advice(self, client, monkeypatch):
        import mingli.web.app as webapp
        monkeypatch.setattr(webapp, "llm_available", lambda: True)
        monkeypatch.setattr(webapp, "recommend_with_llm",
                            lambda q, cls, rec: {"advice": "先开六爻，把问题改成可验证的观察。", "tips": ["补时间窗"]})
        r = client.post("/ask", data={"text": "我该不该换工作"})
        assert r.status_code == 200
        assert "玄师建议" in r.text and "先开六爻" in r.text


class TestSettings:
    """API 设置页：本地持久化 API Key / 模型 / 解释器模式（仅远程 API，无本地模型）。"""

    def test_settings_page_renders(self, client):
        r = client.get("/settings")
        assert r.status_code == 200
        assert "API Key" in r.text
        assert "api_key" in r.text               # 表单字段存在
        assert "本地部署模型" in r.text           # 明确无本地 LLM 的声明
        assert "界面主题" in r.text                # 主题配置区
        assert "跟随系统" in r.text

    def test_settings_save_key_enables_llm(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = client.post("/settings", data={
            "api_key": "sk-ant-test", "model": "claude-3-5-sonnet-20241022",
            "interpreter": "llm"}, follow_redirects=False)
        assert r.status_code == 303
        from mingli.core import llm_config
        assert llm_config.api_key() == "sk-ant-test"
        assert llm_config.model() == "claude-3-5-sonnet-20241022"
        assert llm_config.interpreter() == "llm"
        # 页面上应显示「已配置」而非「未配置」
        page = client.get("/settings")
        assert "已配置" in page.text and "未配置" not in page.text

    def test_settings_clear_key(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client.post("/settings", data={"api_key": "sk-ant-old"}, follow_redirects=False)
        from mingli.core.interpret.llm import llm_available
        assert llm_available() is True
        r = client.post("/settings", data={"action": "clear"}, follow_redirects=False)
        assert r.status_code == 303
        from mingli.core import llm_config
        assert llm_config.api_key() is None
        assert llm_available() is False

    def test_settings_keeps_key_when_blank(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client.post("/settings", data={"api_key": "sk-ant-keep"}, follow_redirects=False)
        # 留空 key + 改模型 → 保留已有 key
        client.post("/settings", data={"model": "claude-sonnet-4-5"}, follow_redirects=False)
        from mingli.core import llm_config
        assert llm_config.api_key() == "sk-ant-keep"
        assert llm_config.model() == "claude-sonnet-4-5"


class TestCharts:
    """个人命盘库：保存出生档案，跨命局型体系快速预填。"""

    def test_charts_page_renders(self, client):
        r = client.get("/charts")
        assert r.status_code == 200
        assert "命盘库" in r.text
        assert "新建命盘档案" in r.text
        assert "name=\"year\"" in r.text

    def test_charts_create_prefills_bazi(self, client):
        r = client.post("/charts", data={"name": "我的命盘", "year": "1990", "month": "8",
                                         "day": "11", "hour": "15", "gender": "男"},
                        follow_redirects=False)
        assert r.status_code == 303
        page = client.get("/charts")
        assert "我的命盘" in page.text
        import re
        m = re.search(r"/generate/bazi\?profile=(p_[0-9a-f]+)", page.text)
        assert m, "应有八字重排链接"
        pid = m.group(1)
        # 八字页预填（新路径 + 旧路径重定向都应可用）
        run = client.get(f"/generate/bazi?profile={pid}")
        assert 'value="1990"' in run.text
        assert 'value="8"' in run.text
        assert 'value="15"' in run.text
        assert 'value="男" selected' in run.text
        # 对照页预填出生资料
        cmp_ = client.get(f"/compare?profile={pid}")
        assert 'value="1990"' in cmp_.text

    def test_charts_invalid_date(self, client):
        r = client.post("/charts", data={"year": "1800", "month": "13", "day": "40"})
        assert r.status_code == 200
        assert "出生日期不合法" in r.text

    def test_charts_delete(self, client):
        client.post("/charts", data={"year": "1985", "month": "8", "day": "11"},
                    follow_redirects=False)
        page = client.get("/charts")
        import re
        m = re.search(r"/charts/(p_[0-9a-f]+)/delete", page.text)
        assert m, "应有删除按钮"
        pid = m.group(1)
        r = client.post(f"/charts/{pid}/delete", follow_redirects=False)
        assert r.status_code == 303
        assert f"/charts/{pid}/delete" not in client.get("/charts").text


class TestCalendar:
    """历法·万年历：纯确定性干支 / 月令 / 节气页。"""

    def test_cal_page_renders(self, client):
        r = client.get("/cal")
        assert r.status_code == 200
        assert "历法" in r.text
        assert "月令" in r.text and "公历" in r.text

    def test_cal_specific_date_and_month_row(self, client):
        r = client.get("/cal?date=2026-08-26")
        assert r.status_code == 200
        assert 'value="2026-08-26"' in r.text      # 日期回显
        assert "日干支" in r.text                    # 月度序列表头
        assert "农历" in r.text
        # 8 月只到 31 号，不应出现 32
        assert "> 32 <" not in r.text


class TestLearn:
    """术数课堂：规则库可读版，按体系 + 来源等级组织。"""

    def test_learn_page_renders(self, client):
        r = client.get("/learn")
        assert r.status_code == 200
        assert "学习空间" in r.text                 # 记录与研究 · Tab 3
        assert "S 原典" in r.text                    # 来源等级说明
        assert "流派" in r.text                      # 流派冲突并列提示
        # 至少一个体系的规则条目出现（以 rules id 前缀判断）
        assert "bazi/" in r.text or "liuyao/" in r.text or "yijing/" in r.text

    def test_learn_renders_known_rule(self, client):
        r = client.get("/research?tab=learn")
        assert r.status_code == 200
        assert "bazi/shishen-duanlv" in r.text      # 十神断律规则条目可读
        assert "[S]" in r.text or "[A]" in r.text or "[B]" in r.text   # 来源标注


class TestZiwei:
    """紫微斗数：诚实登记为 knowledge-only（有知识、暂无可靠算盘引擎）。"""

    def test_ziwei_knowledge_present(self):
        from mingli.core.knowledge import load_knowledge
        rules = load_knowledge().for_system("ziwei")
        assert rules, "应有紫微知识条目"
        assert any(r.sourceLevel in ("S", "A", "B") for r in rules)   # 来源等级有效

    def test_ziwei_registered_knowledge_only(self, client):
        import mingli.web.app as webapp
        rows = webapp._registry.describe_all()
        z = next(r for r in rows if r["id"] == "ziwei")
        assert z["status"] == "knowledge-only"
        assert z["runnable"] is False                 # 诚实：不可运行

    def test_learn_shows_ziwei_labels(self, client):
        r = client.get("/learn")
        assert r.status_code == 200
        assert "紫微斗数" in r.text
        assert "knowledge-only" in r.text              # 标注状态
        assert "ziwei/minggong-zhuxing" in r.text      # 紫微规则条目可读


class TestNewIA:
    """三空间信息架构（2026-08 重构）：生成 / 玄师对话 / 记录与研究 + 设置中心。"""

    # ── 全局导航 ──
    def test_sidebar_three_spaces(self, client):
        page = client.get("/").text
        assert 'href="/generate"' in page and "术数生成" in page
        assert 'href="/chat"' in page and "玄师对话" in page
        assert 'href="/research"' in page and "记录与研究" in page
        assert 'href="/settings"' in page

    def test_home_three_entries(self, client):
        page = client.get("/").text
        assert "home-tri" in page            # 三入口卡片
        assert "/chat" in page and "/research" in page

    # ── 旧路由 302 重定向（兼容不删能力）──
    def test_legacy_redirects(self, client):
        for old, marker in [
            ("/history", "tab=records"), ("/lab", "tab=lab"), ("/learn", "tab=learn"),
        ]:
            r = client.get(old, follow_redirects=False)
            assert r.status_code == 302, old
            assert marker in r.headers["location"], old
        r = client.get("/systems", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "/generate"
        r = client.get("/run/bazi?profile=p_x&q=%E6%B5%8B", follow_redirects=False)
        assert r.status_code == 302
        assert "/generate/bazi?profile=p_x" in r.headers["location"]   # 查询串保留

    # ── ① 术数生成：按输入方式分组 ──
    def test_generate_groups(self, client):
        r = client.get("/generate")
        assert r.status_code == 200
        assert "命盘类" in r.text
        assert "问事 · 起课类" in r.text
        assert "随机抽取类" in r.text
        # 分组正确性：八字在页面且 tarot 在页面（分组渲染由 _group_of 决定）
        assert "/generate/bazi" in r.text
        assert "/generate/tarot" in r.text
        # planned 诚实登记仍在
        assert "规划中" in r.text or "仅知识" in r.text

    def test_generate_group_membership(self):
        """分组逻辑：tarot→randomized，bazi→natal，六爻→moment。"""
        import mingli.web.app as webapp
        reg = webapp._registry
        assert webapp._group_of(reg.get("tarot")) == "randomized"
        assert webapp._group_of(reg.get("bazi")) == "natal"
        assert webapp._group_of(reg.get("liuyao")) == "moment"

    # ── ② 玄师对话 ──
    def test_chat_index_empty(self, client):
        r = client.get("/chat")
        assert r.status_code == 200

    def test_chat_full_flow_degrades_without_key(self, client, monkeypatch):
        """结果页 → 建讨论串 → 发消息 → 无 key 时系统提示而非崩溃，线程仍保存。"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        run = client.post("/run/liuyao", data={"q": "测试对话流", "mode": "random", "seed": "7"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        # 结果页应有「与玄师讨论」按钮
        spage = client.get(f"/session/{sid}").text
        assert "与玄师讨论" in spage
        new = client.get(f"/chat/new/{sid}", follow_redirects=False)
        assert new.status_code == 303
        tid = new.headers["location"].rsplit("/", 1)[-1]
        page = client.get(f"/chat/{tid}")
        assert page.status_code == 200
        assert "研究对象" in page.text and "测试对话流" in page.text
        send = client.post(f"/chat/{tid}/send", data={"message": "这个卦怎么看？"},
                           follow_redirects=False)
        assert send.status_code == 303
        import mingli.web.app as _webapp
        t = _webapp._chats.load(tid)
        roles = [m.role for m in t.messages]
        assert roles == ["user", "assistant"]       # 失败轮次以系统提示落档
        assert "API Key" in t.messages[-1].text or "未配置" in t.messages[-1].text

    def test_chat_send_with_llm_mock(self, client, monkeypatch):
        import mingli.web.app as webapp
        monkeypatch.setattr(webapp, "llm_available", lambda: True)
        captured = {}

        def fake_chat(context_payload, history, user_message, model=None):
            captured["ctx"] = context_payload
            captured["history"] = history
            return "基于盘面结构，倾向……（模拟回复）"

        monkeypatch.setattr(webapp, "chat_with_llm", fake_chat)
        run = client.post("/run/liuyao", data={"q": "面试能过吗", "mode": "random", "seed": "3"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        tid = client.get(f"/chat/new/{sid}", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
        r = client.post(f"/chat/{tid}/send", data={"message": "为什么这么解？"}, follow_redirects=False)
        assert r.status_code == 303
        ctx = captured["ctx"]
        assert ctx["systemId"] == "liuyao"
        assert ctx["question"] == "面试能过吗"
        assert ctx["calculation"]                    # 计算事实完整携带
        page = client.get(f"/chat/{tid}")
        assert "模拟回复" in page.text

    def test_chat_context_never_mutates_session(self, client, monkeypatch):
        """对话不得改写计算事实——发消息后 session 的 calculation 不变。"""
        import copy

        import mingli.web.app as _webapp
        run = client.post("/run/tarot", data={"q": "x", "spread": "three", "seed": "5"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        before = copy.deepcopy(_webapp._sessions.load(sid).calculation.data)
        tid = client.get(f"/chat/new/{sid}", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
        monkeypatch.setattr("mingli.core.interpret.llm.llm_available", lambda: True)
        monkeypatch.setattr("mingli.web.app.chat_with_llm",
                            lambda cp, h, m, model=None: "回复")
        client.post(f"/chat/{tid}/send", data={"message": "随便聊聊"})
        after = _webapp._sessions.load(sid).calculation.data
        assert after == before

    # ── ③ 记录与研究 ──
    def test_research_records_tab_search_filter(self, client):
        run = client.post("/run/bazi", data={"q": "职业方向研究", "year": "1990", "month": "5",
                                             "day": "12", "hour": "10", "gender": "男"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        # 打标签+收藏
        tg = client.post(f"/session/{sid}/tags",
                         data={"tags": "职业, 长期", "favorite": "true"}, follow_redirects=False)
        assert tg.status_code == 303
        rec = client.get("/research?tab=records")
        assert rec.status_code == 200
        assert "职业方向研究" in rec.text
        hit = client.get("/research?tab=records&q=职业").text
        assert "职业方向研究" in hit
        miss = client.get("/research?tab=records&q=不存在关键词xyz").text
        assert "职业方向研究" not in miss
        fav = client.get("/research?tab=records&fav=1").text
        assert "职业方向研究" in fav
        bysys = client.get("/research?tab=records&system=bazi").text
        assert "职业方向研究" in bysys

    def test_research_lab_tab_keeps_ledger(self, client):
        run = client.post("/run/liuyao", data={"q": "实验", "mode": "random", "seed": "9"},
                          follow_redirects=False)
        sid = run.headers["location"].rsplit("/", 1)[-1]
        lab = client.post(f"/lab/new/{sid}", data={
            "prediction": "倾向有反复", "window_start": "2026-09-01",
            "window_end": "2026-09-10"}, follow_redirects=False)
        assert lab.status_code == 303
        eid = lab.headers["location"].rsplit("/", 1)[-1]
        detail = client.get(f"/research/lab-detail/{eid}")
        assert "裁定规则表" in detail.text
        page = client.get("/research?tab=lab")
        assert "倾向有反复" in page.text
        assert "个人实验样本" in page.text            # 诚实声明保留

    # ── ⚙ 设置中心 ──
    def test_settings_new_sections(self, client):
        r = client.get("/settings").text
        assert "Provider" in r and "deepseek" in r.lower()
        assert "base_url" in r                       # OpenAI 兼容端点字段
        assert "回答风格" in r                        # 模型行为区
        assert "本地数据管理" in r                    # 数据区

    def test_settings_save_provider_and_style(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = client.post("/settings", data={
            "provider": "deepseek", "api_key": "sk-ds", "model": "deepseek-chat",
            "style": "research", "interpreter": "rule-engine"}, follow_redirects=False)
        assert r.status_code == 303
        from mingli.core import llm_config
        cfg = llm_config.load()
        assert cfg["provider"] == "deepseek"
        assert cfg["style"] == "research"
        assert llm_config.base_url()  # deepseek 默认端点生效

    def test_settings_test_endpoint_no_key(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        import mingli.web.app as webapp
        monkeypatch.setattr(webapp, "llm_available", lambda: False)
        r = client.post("/settings/test")
        assert r.status_code == 400

    def test_systems_shows_ziwei_knowledge_only(self, client):
        r = client.get("/systems")
        assert r.status_code == 200
        assert "knowledge-only" in r.text or "知识" in r.text
