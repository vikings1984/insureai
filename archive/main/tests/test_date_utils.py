#!/usr/bin/env python3
"""日期工具函数单元测试
覆盖 _parse_date_string, _validate_date, extract_date_from_text, assign_score, is_safe_url
"""
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# 确保能导入 run_collect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_collect import (
    _parse_date_string,
    _validate_date,
    extract_date_from_text,
    assign_score,
    is_safe_url,
    validate_url,
    is_blacklisted,
    is_stock_noise,
    is_search_engine_noise,
    title_similarity,
)


class TestParseDateString:
    """_parse_date_string 各种日期格式解析"""

    def test_iso_format(self):
        assert _parse_date_string("2026-07-02") == "2026-07-02"
        assert _parse_date_string("2026-07-02T10:30:00+08:00") == "2026-07-02"
        assert _parse_date_string("2026-7-2") == "2026-07-02"

    def test_chinese_format_with_ri(self):
        assert _parse_date_string("2024年3月2日") == "2024-03-02"
        assert _parse_date_string("2026年12月25日") == "2026-12-25"

    def test_chinese_format_without_ri(self):
        """BUG FIX: ARTICLE_DATE_PATTERNS 捕获组不含'日'，_parse_date_string 必须兼容"""
        assert _parse_date_string("2024年3月2") == "2024-03-02"
        assert _parse_date_string("2026年1月1") == "2026-01-01"

    def test_slash_format(self):
        assert _parse_date_string("2026/07/02") == "2026-07-02"
        assert _parse_date_string("2026/7/2") == "2026-07-02"

    def test_invalid_date_range(self):
        """BUG FIX: 无效日期应返回 None 而非格式化字符串"""
        assert _parse_date_string("2026-13-45") is None
        assert _parse_date_string("2026-02-30") is None  # 2月没有30日
        assert _parse_date_string("2026-00-01") is None  # 月份不能为0
        assert _parse_date_string("2026-12-00") is None  # 日期不能为0

    def test_invalid_input(self):
        assert _parse_date_string("") is None
        assert _parse_date_string("not a date") is None
        assert _parse_date_string("10:30:00") is None

    def test_whitespace(self):
        assert _parse_date_string("  2026-07-02  ") == "2026-07-02"


class TestValidateDate:
    """_validate_date 日期范围校验"""

    def test_valid_dates(self):
        assert _validate_date("2026", "7", "2") == "2026-07-02"
        assert _validate_date("2026", "12", "31") == "2026-12-31"
        assert _validate_date("2024", "2", "29") == "2024-02-29"  # 闰年

    def test_invalid_dates(self):
        assert _validate_date("2026", "13", "1") is None
        assert _validate_date("2026", "2", "30") is None  # 非闰年2月
        assert _validate_date("2024", "2", "30") is None  # 闰年2月也只有29天

    def test_zero_padding(self):
        assert _validate_date("2026", "1", "1") == "2026-01-01"
        assert _validate_date("2026", "12", "1") == "2026-12-01"


class TestExtractDateFromText:
    """extract_date_from_text 搜索引擎结果页时间解析"""

    def test_hours_ago(self):
        result = extract_date_from_text("3小时前")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        assert result == today

    def test_hours_ago_threshold(self):
        """BUG FIX: 超过24小时的'X小时前'不应返回今天"""
        assert extract_date_from_text("9999小时前") is None
        assert extract_date_from_text("25小时前") is None

    def test_hours_ago_boundary(self):
        """23小时前仍应返回今天"""
        result = extract_date_from_text("23小时前")
        assert result is not None

    def test_days_ago(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        result = extract_date_from_text("3天前")
        expected = (today - timedelta(days=3)).isoformat()
        assert result == expected

    def test_relative_dates(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        assert extract_date_from_text("昨天") == (today - timedelta(days=1)).isoformat()
        assert extract_date_from_text("前天") == (today - timedelta(days=2)).isoformat()
        assert extract_date_from_text("今天") == today.isoformat()
        assert extract_date_from_text("今日") == today.isoformat()

    def test_absolute_date(self):
        assert extract_date_from_text("2026-07-02") == "2026-07-02"
        assert extract_date_from_text("发布于 2026-07-02 15:30") == "2026-07-02"

    def test_chinese_month_day(self):
        result = extract_date_from_text("3月15日")
        year = datetime.now(ZoneInfo("Asia/Shanghai")).year
        assert result == f"{year}-03-15"

    def test_empty_input(self):
        assert extract_date_from_text("") is None
        assert extract_date_from_text(None) is None

    def test_no_date_found(self):
        assert extract_date_from_text("这是一段没有日期的文字") is None

    def test_invalid_month_day(self):
        """BUG FIX: 无效月日应返回 None"""
        assert extract_date_from_text("13月45日") is None
        assert extract_date_from_text("0月15日") is None


class TestAssignScore:
    """assign_score 新鲜度加分逻辑"""

    def test_verified_today_gets_max_freshness(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        score, _ = assign_score("保险监管新规", "监管政策内容", "新华社", today, date_verified=True)
        # 基础3.0 + 关键词 + 权威1.0 + 长度 + 新鲜度3.5
        assert score >= 6.0  # 至少有基础分+新鲜度

    def test_unverified_no_freshness_bonus(self):
        """BUG FIX: date_verified=False 时不获得新鲜度加分"""
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        score_verified, _ = assign_score("保险监管新规", "监管政策内容", "新华社", today, date_verified=True)
        score_unverified, _ = assign_score("保险监管新规", "监管政策内容", "新华社", today, date_verified=False)
        assert score_verified > score_unverified, "已验证条目应比未验证条目得分更高"

    def test_empty_pub_date_no_freshness(self):
        """空日期不获得新鲜度加分"""
        score, _ = assign_score("保险监管新规", "监管政策内容", "新华社", "", date_verified=False)
        assert score < 10.0  # 不应该满分

    def test_future_date_no_freshness(self):
        """未来日期异常，不加分"""
        future = "2099-12-31"
        score, _ = assign_score("保险监管新规", "监管政策内容", "新华社", future, date_verified=True)
        # 未来日期不获得新鲜度加分
        assert score < 7.0  # 只有基础分+关键词+权威+长度

    def test_old_date_reduced_freshness(self):
        old_date = "2020-01-01"
        score, _ = assign_score("保险监管新规", "监管政策内容", "新华社", old_date, date_verified=True)
        # 旧文不获得新鲜度加分（>14天）
        assert score < 7.0


class TestIsSafeUrl:
    """is_safe_url SSRF 防护"""

    def test_block_loopback(self):
        assert is_safe_url("http://127.0.0.1/") is False
        assert is_safe_url("http://127.0.0.1:8080/") is False
        assert is_safe_url("http://localhost/") is False
        assert is_safe_url("http://localhost:3000/") is False

    def test_block_private_ranges(self):
        assert is_safe_url("http://10.0.0.1/") is False
        assert is_safe_url("http://10.255.255.255/") is False
        assert is_safe_url("http://192.168.1.1/") is False
        assert is_safe_url("http://172.16.0.1/") is False

    def test_block_link_local(self):
        """云元数据端点 169.254.169.254"""
        assert is_safe_url("http://169.254.169.254/") is False
        assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    def test_block_reserved(self):
        assert is_safe_url("http://0.0.0.0/") is False

    def test_invalid_scheme(self):
        assert is_safe_url("ftp://example.com/") is False
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("javascript:alert(1)") is False

    def test_invalid_input(self):
        assert is_safe_url("") is False
        assert is_safe_url("not-a-url") is False
        assert is_safe_url(None) is False


class TestValidateUrl:
    """validate_url 协议校验"""

    def test_valid_http(self):
        assert validate_url("http://example.com") == "http://example.com"
        assert validate_url("https://example.com/path") == "https://example.com/path"

    def test_invalid_scheme(self):
        assert validate_url("ftp://example.com") == ""
        assert validate_url("javascript:alert(1)") == ""
        assert validate_url("file:///etc/passwd") == ""

    def test_empty_input(self):
        assert validate_url("") == ""
        assert validate_url(None) == ""


class TestIsBlacklisted:
    """is_blacklisted 非新闻来源过滤"""

    def test_blacklisted_domains(self):
        assert is_blacklisted("https://zhihu.com/question/123", "") is True
        assert is_blacklisted("https://baike.baidu.com/item/insurance", "") is True
        assert is_blacklisted("https://picc.com.cn/product", "") is True

    def test_allowed_domains(self):
        assert is_blacklisted("https://finance.sina.com.cn/article", "") is False
        assert is_blacklisted("https://www.nfra.gov.cn/notice", "") is False

    def test_blacklisted_source_names(self):
        assert is_blacklisted("", "知乎") is True
        assert is_blacklisted("", "百度百科") is True


class TestStockNoise:
    """is_stock_noise 股市噪声过滤"""

    def test_stock_noise(self):
        assert is_stock_noise("保险板块拉升") is True
        assert is_stock_noise("中国平安涨停") is True
        assert is_stock_noise("保险板块持续反弹") is True

    def test_exempt_content(self):
        assert is_stock_noise("保险科技板块拉升") is False
        assert is_stock_noise("保险产品创新助力行业发展") is False

    def test_normal_news(self):
        assert is_stock_noise("金融监管总局发布新规") is False
        assert is_stock_noise("健康险产品上线") is False


class TestSearchEngineNoise:
    """is_search_engine_noise 搜索引擎噪声过滤"""

    def test_noise_patterns(self):
        assert is_search_engine_noise("中国平安官方网站") is True
        assert is_search_engine_noise("保险计算器") is True
        assert is_search_engine_noise("保险理赔流程-官方网站") is True

    def test_normal_titles(self):
        assert is_search_engine_noise("金融监管总局发布偿付能力新规") is False
        assert is_search_engine_noise("保险业上半年罚单破亿") is False


class TestTitleSimilarity:
    """title_similarity 标题去重"""

    def test_identical(self):
        assert title_similarity("保险新规出台", "保险新规出台") == 1.0

    def test_similar(self):
        sim = title_similarity("保险监管新规发布", "保险监管新规出台")
        assert sim > 0.5

    def test_different(self):
        sim = title_similarity("保险监管新规", "新能源汽车销量")
        assert sim < 0.3

    def test_empty(self):
        assert title_similarity("", "test") == 0
        assert title_similarity("", "") == 0


if __name__ == "__main__":
    # 简单运行器，无需 pytest
    import traceback as tb

    classes = [
        TestParseDateString, TestValidateDate, TestExtractDateFromText,
        TestAssignScore, TestIsSafeUrl, TestValidateUrl,
        TestIsBlacklisted, TestStockNoise, TestSearchEngineNoise,
        TestTitleSimilarity,
    ]
    passed, failed = 0, 0
    for cls in classes:
        for method_name in dir(cls):
            if method_name.startswith("test_"):
                try:
                    getattr(cls, method_name)(cls)
                    passed += 1
                except Exception as e:
                    failed += 1
                    print(f"FAIL: {cls.__name__}.{method_name}: {e}")
                    tb.print_exc()
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
