#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_research_topics_v2.py — 研究主题分类与扩充关键词单测

验证 infer_topic() 对 8 大主题的覆盖，特别是扩充后的
digital_transformation / climate_catastrophe / channel_transformation / regulatory_change。

运行：
    python3 -m unittest tests/test_research_topics_v2.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect


class TestDigitalTransformation(unittest.TestCase):
    """数字化转主题（扩充后应能匹配更多内容）"""

    def test_cloud_computing(self):
        self.assertEqual(collect.infer_topic("险企上云加速，云计算赋能保险核心系统", ""), "digital_transformation")

    def test_big_data(self):
        self.assertEqual(collect.infer_topic("保险大数据平台建设进入新阶段", ""), "digital_transformation")

    def test_saas(self):
        self.assertEqual(collect.infer_topic("SaaS模式重塑保险中介IT架构", ""), "digital_transformation")

    def test_paperless(self):
        # "无纸化" + "信息化" 两个数字化关键词 > "车险" 一个产品关键词
        self.assertEqual(collect.infer_topic("保险理赔无纸化，信息化水平提升", ""), "digital_transformation")

    def test_microservice(self):
        self.assertEqual(collect.infer_topic("保险核心系统微服务改造完成", ""), "digital_transformation")

    def test_digital_not_ai(self):
        """'数字化' 应归属 digital_transformation 而非 ai_intelligent"""
        topic = collect.infer_topic("保险公司数字化转型进入深水区", "")
        self.assertEqual(topic, "digital_transformation")


class TestClimateCatastrophe(unittest.TestCase):
    """气候与巨灾主题（扩充后应能匹配更多灾害类型）"""

    def test_earthquake(self):
        self.assertEqual(collect.infer_topic("四川地震保险赔付启动，快速响应灾害", ""), "climate_catastrophe")

    def test_drought(self):
        self.assertEqual(collect.infer_topic("旱灾推动农业保险指数化理赔普及", ""), "climate_catastrophe")

    def test_mudslide(self):
        self.assertEqual(collect.infer_topic("泥石流灾害保险理赔进展", ""), "climate_catastrophe")

    def test_disaster_prevention(self):
        self.assertEqual(collect.infer_topic("保险业防灾减损体系建设加速", ""), "climate_catastrophe")

    def test_wildfire_english(self):
        self.assertEqual(collect.infer_topic("California wildfire insurance losses escalate", ""), "climate_catastrophe")


class TestChannelTransformation(unittest.TestCase):
    """渠道变革主题（扩充后应能匹配更多渠道形态）"""

    def test_bancassurance(self):
        self.assertEqual(collect.infer_topic("银保渠道新规落地，bancassurance面临转型", ""), "channel_transformation")

    def test_live_streaming(self):
        self.assertEqual(collect.infer_topic("保险直播带货合规指引发布", ""), "channel_transformation")

    def test_telesales(self):
        self.assertEqual(collect.infer_topic("电销渠道保费下滑，telesales模式亟待升级", ""), "channel_transformation")

    def test_private_domain(self):
        self.assertEqual(collect.infer_topic("险企私域运营赋能代理人获客", ""), "channel_transformation")


class TestRegulatoryChange(unittest.TestCase):
    """监管变革主题（扩充后应能匹配更多监管领域）"""

    def test_cross2(self):
        # "偿二代" + "监管" 两个监管关键词 > "资本" 一个资本关键词
        self.assertEqual(collect.infer_topic("偿二代二期监管规则修订", ""), "regulatory_change")

    def test_consumer_protection(self):
        self.assertEqual(collect.infer_topic("消费者权益保护新规出台，消保考核加码", ""), "regulatory_change")

    def test_aml(self):
        self.assertEqual(collect.infer_topic("反洗钱AML新规对保险业的影响", ""), "regulatory_change")

    def test_regtech(self):
        self.assertEqual(collect.infer_topic("监管科技RegTech在保险合规中的应用", ""), "regulatory_change")

    def test_internal_control(self):
        self.assertEqual(collect.infer_topic("险企内控合规管理办法修订", ""), "regulatory_change")


class TestTopicPriority(unittest.TestCase):
    """多主题命中时的优先级验证"""

    def test_digital_over_ai(self):
        """数字化 + AI 同时出现，数字化关键词更多时应归 digital_transformation"""
        topic = collect.infer_topic(
            "保险数字化转型：大数据平台上云与SaaS架构",
            "信息化建设微服务中台技术架构科技投入")
        self.assertEqual(topic, "digital_transformation")

    def test_ai_over_digital(self):
        """AI 关键词更多时应归 ai_intelligent"""
        topic = collect.infer_topic(
            "AI大模型赋能智能核保与智能理赔",
            "人工智能Agent智能体automation insurtech")
        self.assertEqual(topic, "ai_intelligent")

    def test_no_match_returns_none(self):
        self.assertIsNone(collect.infer_topic("完全无关的内容", "没有任何保险关键词"))


class TestStockNoiseIntegration(unittest.TestCase):
    """股市噪声过滤与主题分类的集成验证"""

    def test_stock_noise_not_classified(self):
        """股市噪声标题不应进入主题分类流程（已在 _ingest 中被拦截）"""
        noise_title = "保险板块拉升，新华保险涨超4%"
        # is_stock_noise 应返回 True
        self.assertTrue(collect.is_stock_noise(noise_title))
        # 即使能匹配主题关键词，也不应进入数据集

    def test_legitimate_insurance_news(self):
        """正常保险新闻不应被误判为噪声"""
        legit_title = "新华保险推出新重疾险产品，覆盖100种重大疾病"
        self.assertFalse(collect.is_stock_noise(legit_title))


if __name__ == "__main__":
    unittest.main()
