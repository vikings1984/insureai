"""保险领域 AI 评分器

基于 Horizon 评分架构 + 保险领域专属评分维度
对每条资讯进行: 保险相关度分析、综合评分、分类、标签
"""

from __future__ import annotations
import json
import asyncio
from typing import TYPE_CHECKING

from src.config import get_env_var, get_ai_config, get_categories, get_scoring_config
from src.ai.multi_provider import MultiProviderManager

if TYPE_CHECKING:
    from src.models import NewsItem


SCORING_PROMPT_ZH = """你是一位保险行业资深分析师。请对以下资讯进行评分和分析。

## 评分标准（0-10分）

### 保险相关度（Insurance Relevance）- 核心维度
- 9-10: 直接关于保险行业的重大事件（监管变革、巨头并购、突破性产品）
- 7-8: 与保险密切相关（新产品、重要理赔案例、精算研究）
- 5-6: 间接相关（金融科技、健康医疗、汽车等保险关联领域）
- 3-4: 弱相关（泛金融、泛经济新闻）
- 0-2: 无关

### 综合评分维度
1. 技术深度与创新性 (权重20%): 原创观点、新技术、新方法论
2. 行业影响力 (权重30%): 对保险行业的广泛影响程度
3. 内容质量 (权重20%): 清晰度、结构完整性、深度
4. 时效性与新颖性 (权重30%): 是否为最新动态、首次报道

## 分类体系
请从以下类别中选择最匹配的一个:
- regulation: 监管政策（银保监会/金融监管总局新规、合规要求、政策解读）
- product: 产品发布/更新（保险新产品、产品升级、费率调整、创新产品）
- industry: 行业动态（保险公司经营、市场格局、并购、人事变动、业绩）
- research: 论文研究（保险科技、精算研究、风险模型、AI+保险学术论文）
- claims: 理赔与案例（理赔案例、纠纷判例、反欺诈、消费者权益）

## 待分析资讯

{items_text}

## 输出格式

请严格以 JSON 格式输出，不要包含任何其他文本:
```json
[
  {{
    "index": 0,
    "ai_score": 7.5,
    "insurance_relevance": 0.85,
    "category": "regulation",
    "ai_reason": "简要评分理由",
    "ai_summary": "一句话中文摘要",
    "ai_tags": ["监管", "偿付能力", "金融监管总局"]
  }}
]
```"""


class InsuranceScorer:
    """保险领域 AI 评分器"""

    def __init__(self, config: dict):
        self.config = config
        self.ai_config = get_ai_config(config)
        self.scoring_config = get_scoring_config(config)
        self.categories = get_categories(config)
        self.batch_size = self.ai_config.get("batch_size", 10)
        self.throttle_sec = self.ai_config.get("throttle_sec", 0)
        self.max_retries = self.ai_config.get("max_retries", 3)
        # 初始化多提供商管理器
        self.provider_manager = MultiProviderManager(config)

    def _prepare_item_text(self, item: "NewsItem", index: int) -> str:
        """准备单条资讯的文本表示"""
        content = item.content[:800] if item.content else item.title
        engagement = ""
        if item.engagement_score:
            engagement += f" 互动分数: {item.engagement_score}"
        if item.comment_count:
            engagement += f" 评论数: {item.comment_count}"

        return (
            f"[{index}] 标题: {item.title}\n"
            f"来源: {item.source_name} ({item.source_type}){engagement}\n"
            f"内容: {content}"
        )

    async def _call_ai(self, prompt: str) -> str:
        """调用 AI 模型（使用多提供商故障切换）"""
        return await self.provider_manager.call_with_fallback(
            prompt=prompt,
            system_prompt="你是一位保险行业资深分析师，擅长信息筛选和内容评估。",
            temperature=self.ai_config.get("temperature", 0.3),
            max_tokens=4096,
        )

    def _parse_response(self, response_text: str) -> list[dict]:
        """解析 AI 返回的 JSON"""
        # 尝试直接解析
        text = response_text.strip()
        # 去掉 markdown code block
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            result = json.loads(text)
            if isinstance(result, dict) and "items" in result:
                return result["items"]
            return result if isinstance(result, list) else [result]
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            raise

    async def score_batch(self, items: list["NewsItem"]) -> list["NewsItem"]:
        """对一批资讯进行评分"""
        if not items:
            return items

        # 准备 prompt
        items_text = "\n\n".join(
            self._prepare_item_text(item, i) for i, item in enumerate(items)
        )
        prompt = SCORING_PROMPT_ZH.format(items_text=items_text)

        # 调用 AI（带重试）
        for attempt in range(self.max_retries):
            try:
                response = await self._call_ai(prompt)
                results = self._parse_response(response)

                # 将结果映射回 items
                for result in results:
                    idx = result.get("index", 0)
                    if 0 <= idx < len(items):
                        items[idx].ai_score = float(result.get("ai_score", 0))
                        items[idx].insurance_relevance = float(result.get("insurance_relevance", 0))
                        items[idx].category = result.get("category", "")
                        items[idx].ai_reason = result.get("ai_reason", "")
                        items[idx].ai_summary = result.get("ai_summary", "")
                        items[idx].ai_tags = result.get("ai_tags", [])

                return items

            except Exception as e:
                print(f"[Scorer] 第 {attempt + 1} 次尝试失败: {e}")
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    await asyncio.sleep(wait)

        # 全部失败，给默认分
        for item in items:
            item.ai_score = 0
        return items

    async def score_all(self, items: list["NewsItem"]) -> list["NewsItem"]:
        """对所有资讯分批评分"""
        scored_items: list["NewsItem"] = []

        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            scored = await self.score_batch(batch)
            scored_items.extend(scored)

            if self.throttle_sec > 0 and i + self.batch_size < len(items):
                await asyncio.sleep(self.throttle_sec)

        return scored_items

    def filter_items(self, items: list["NewsItem"]) -> list["NewsItem"]:
        """根据评分和保险相关度过滤"""
        threshold = self.scoring_config.get("ai_score_threshold", 6.0)
        relevance_min = self.scoring_config.get("insurance_relevance_min", 0.4)

        return [
            item for item in items
            if item.ai_score >= threshold and item.insurance_relevance >= relevance_min
        ]
