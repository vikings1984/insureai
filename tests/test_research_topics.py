#!/usr/bin/env python3
"""研究主题分类与权威报告检测单元测试
覆盖 assign_research_topic, is_authoritative_report, detect_report_layer,
以及 assign_score 的 report_bonus 加分逻辑
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# 确保能导入 run_collect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_collect import (
    assign_research_topic,
    is_authoritative_report,
    detect_report_layer,
    assign_score,
    RESEARCH_TOPICS,
    RESEARCH_TOPIC_LABELS,
    AUTHORITATIVE_REPORT_SOURCES,
    AUTHORITATIVE_REPORT_SOURCES_REINSURANCE,
    AUTHORITATIVE_REPORT_SOURCES_CONSULTING,
    AUTHORITATIVE_REPORT_SOURCES_DOMESTIC,
)


class TestAssignResearchTopic:
    """assign_research_topic 8大研究主题分类"""

    def test_ai_intelligent(self):
        topic = assign_research_topic("AI驱动保险行业变革", "生成式AI在智能核保中的应用")
        assert topic == "ai_intelligent"

    def test_ai_intelligent_english(self):
        topic = assign_research_topic("GenAI reshapes underwriting", "Large language models in insurance")
        assert topic == "ai_intelligent"

    def test_pension_finance(self):
        topic = assign_research_topic("个人养老金制度全面推开", "第三支柱养老保险体系建设")
        assert topic == "pension_finance"

    def test_product_innovation(self):
        topic = assign_research_topic("惠民保可持续发展", "UBI车险产品创新方案")
        assert topic == "product_innovation"

    def test_channel_transformation(self):
        topic = assign_research_topic("银保渠道新规落地", "保险中介与代理人队伍转型趋势")
        assert topic == "channel_transformation"

    def test_capital_reinsurance(self):
        topic = assign_research_topic("再保险续转费率下降", "巨灾债券发行创新高ILS市场扩张")
        assert topic == "capital_reinsurance"

    def test_climate_catastrophe(self):
        topic = assign_research_topic("台风摩羯保险赔付分析", "自然灾害巨灾保险体系建设")
        assert topic == "climate_catastrophe"

    def test_digital_transformation(self):
        topic = assign_research_topic("保险科技InsurTech融资追踪", "核心系统现代化与数字化指数提升")
        assert topic == "digital_transformation"

    def test_regulatory_change(self):
        topic = assign_research_topic("C-ROSS二期实施效果", "IFRS 17新会计准则对保险公司影响")
        assert topic == "regulatory_change"

    def test_no_match(self):
        topic = assign_research_topic("某公司发布财报", "营收增长5%")
        assert topic == ""

    def test_multiple_topics_picks_highest(self):
        """当多个主题关键词都匹配时，选择匹配最多的主题"""
        title = "AI驱动的养老金产品创新"
        content = "人工智能技术在养老保险产品设计与数字化转型中的应用"
        topic = assign_research_topic(title, content)
        # ai_intelligent 有2个匹配（AI、人工智能），pension_finance 有1个（养老金），
        # product_innovation 有1个（产品创新），digital_transformation 有1个（数字化转型）
        assert topic == "ai_intelligent"

    def test_empty_input(self):
        assert assign_research_topic("", "") == ""
        assert assign_research_topic("", None) == ""

    def test_all_topics_have_labels(self):
        """确保所有8个主题都有对应的中文标签"""
        assert len(RESEARCH_TOPICS) == 8
        for topic_key in RESEARCH_TOPICS:
            assert topic_key in RESEARCH_TOPIC_LABELS, f"主题 {topic_key} 缺少中文标签"

    def test_all_topics_have_keywords(self):
        """确保所有主题都有非空关键词列表"""
        for topic_key, keywords in RESEARCH_TOPICS.items():
            assert len(keywords) > 0, f"主题 {topic_key} 关键词列表为空"


class TestIsAuthoritativeReport:
    """is_authoritative_report 权威报告来源检测"""

    def test_reinsurance_source(self):
        assert is_authoritative_report("瑞士再保险", "全球保险市场展望", "sigma报告内容") == True

    def test_consulting_source(self):
        assert is_authoritative_report("麦肯锡", "全球保险业报告2025", "增长策略分析") == True

    def test_domestic_source(self):
        assert is_authoritative_report("国家金融监督管理总局", "保险业统计数据", "保费收入数据") == True

    def test_non_authoritative_source(self):
        assert is_authoritative_report("某自媒体", "保险行业新闻", "普通新闻内容") == False

    def test_content_references_authority(self):
        """文章内容引用了权威机构也算"""
        assert is_authoritative_report("新浪财经", "德勤发布2026保险展望", "德勤报告指出AI将重塑保险业") == True

    def test_title_with_report_keyword_and_authority(self):
        """标题含"报告"且来源匹配权威机构"""
        assert is_authoritative_report("BCG", "保险数字化转型白皮书", "数字化战略") == True

    def test_title_with_report_keyword_no_authority(self):
        """标题含"报告"但不匹配权威机构，不算"""
        assert is_authoritative_report("某博客", "我的保险投资报告", "个人观点") == False

    def test_empty_source(self):
        assert is_authoritative_report("", "标题", "内容") == False

    def test_english_source_name(self):
        assert is_authoritative_report("Swiss Re Institute", "Global Insurance Report", "market outlook") == True
        assert is_authoritative_report("Munich Re", "NatCat Report 2024", "natural disaster losses") == True

    def test_all_sources_have_three_layers(self):
        """确保三层覆盖体系都有内容"""
        assert len(AUTHORITATIVE_REPORT_SOURCES_REINSURANCE) > 0
        assert len(AUTHORITATIVE_REPORT_SOURCES_CONSULTING) > 0
        assert len(AUTHORITATIVE_REPORT_SOURCES_DOMESTIC) > 0
        # 总列表应该是三层之和
        assert len(AUTHORITATIVE_REPORT_SOURCES) == (
            len(AUTHORITATIVE_REPORT_SOURCES_REINSURANCE)
            + len(AUTHORITATIVE_REPORT_SOURCES_CONSULTING)
            + len(AUTHORITATIVE_REPORT_SOURCES_DOMESTIC)
        )


class TestDetectReportLayer:
    """detect_report_layer 层级检测"""

    def test_reinsurance_layer(self):
        assert detect_report_layer("瑞士再保险") == "reinsurance"
        assert detect_report_layer("Munich Re") == "reinsurance"
        assert detect_report_layer("劳合社") == "reinsurance"

    def test_consulting_layer(self):
        assert detect_report_layer("麦肯锡") == "consulting"
        assert detect_report_layer("BCG") == "consulting"
        assert detect_report_layer("Accenture") == "consulting"

    def test_domestic_layer(self):
        assert detect_report_layer("国家金融监督管理总局") == "domestic"
        assert detect_report_layer("清华五道口") == "domestic"
        assert detect_report_layer("头豹研究院") == "domestic"

    def test_no_layer(self):
        assert detect_report_layer("新浪财经") == ""
        assert detect_report_layer("") == ""


class TestAssignScoreReportBonus:
    """assign_score 权威报告加分逻辑"""

    def test_auth_report_gets_bonus(self):
        """权威报告条目应获得额外1.5分加分"""
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        # 使用完全相同的标题和内容，仅 is_auth_report 不同
        score_normal, _ = assign_score(
            "某地天气情况", "今天阳光明媚风力三级的天气预报", "某媒体", today, date_verified=True
        )
        score_report, _ = assign_score(
            "某地天气情况", "今天阳光明媚风力三级的天气预报", "某媒体", today, date_verified=True, is_auth_report=True
        )
        assert score_report > score_normal, "权威报告应获得更高分数"
        assert score_report - score_normal >= 1.5, f"权威报告加分应至少1.5分，实际差值 {score_report - score_normal}"

    def test_auth_report_with_unverified_date(self):
        """权威报告 + 未验证日期：有加分但无新鲜度加分"""
        score, _ = assign_score(
            "保险行业报告", "报告内容", "某媒体", "", date_verified=False, is_auth_report=True
        )
        # 基础3.0 + 报告1.5 = 至少4.5（无关键词、无权威、无长度、无新鲜度）
        assert score >= 4.5

    def test_auth_report_max_score(self):
        """权威报告 + 验证日期 + 权威来源 + 关键词 + 长内容 = 满分10.0"""
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        long_content = "保险监管" * 200  # 足够长
        score, _ = assign_score(
            "保险监管新规发布",
            long_content,
            "中国证券报",
            today,
            date_verified=True,
            is_auth_report=True,
        )
        assert score == 10.0, f"预期满分10.0，实际 {score}"

    def test_no_bonus_for_non_auth(self):
        """非权威报告不获得加分"""
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        score, _ = assign_score(
            "保险新闻", "新闻内容", "某媒体", today, date_verified=True, is_auth_report=False
        )
        score_default, _ = assign_score(
            "保险新闻", "新闻内容", "某媒体", today, date_verified=True
        )
        assert score == score_default, "is_auth_report=False 不应影响分数"


if __name__ == "__main__":
    import traceback as tb

    classes = [
        TestAssignResearchTopic,
        TestIsAuthoritativeReport,
        TestDetectReportLayer,
        TestAssignScoreReportBonus,
    ]
    passed, failed = 0, 0
    for cls in classes:
        for method_name in dir(cls):
            if method_name.startswith("test_"):
                try:
                    getattr(cls, method_name)(cls)
                    passed += 1
                    print(f"  ✓ {cls.__name__}.{method_name}")
                except Exception as e:
                    failed += 1
                    print(f"  ✗ {cls.__name__}.{method_name}: {e}")
                    tb.print_exc()
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
