"""保险资讯内容增强器

基于 Horizon Enricher 架构，针对保险领域进行概念提取和背景补充
添加背景知识、参考链接、智能标签、社区讨论摘要等丰富内容
"""

from __future__ import annotations
import json
import asyncio
from typing import TYPE_CHECKING
from dataclasses import dataclass

from src.config import get_env_var, get_ai_config, get_scoring_config

if TYPE_CHECKING:
    from src.models import NewsItem


@dataclass
class EnrichmentResult:
    """增强结果数据结构"""
    whats_new: str = ""
    why_it_matters: str = ""
    key_details: str = ""
    background: list[dict] = None
    references: list[dict] = None
    tags: list[str] = None
    community_discussion: str = ""
    
    def __post_init__(self):
        if self.background is None:
            self.background = []
        if self.references is None:
            self.references = []
        if self.tags is None:
            self.tags = []


ENRICHMENT_PROMPT_V2 = """你是一位保险行业资深分析师。请对以下保险资讯进行深度分析，输出 Horizon 风格的结构化内容。

## 待分析资讯

标题: {title}
内容: {content}
来源: {source}
AI摘要: {summary}
现有标签: {tags}

## 请输出以下结构化内容（严格JSON格式）:

```json
{{
  "whats_new": "具体发生了什么变化或事件（中文，2-3句，突出时效性）",
  "why_it_matters": "这条资讯对保险行业的重要性（中文，3-4句，突出影响范围）",
  "key_details": "值得关注的技术细节或关键信息（中文，2-3句）",
  "background": [
    {{
      "concept": "概念名称",
      "explanation": "简要解释（50字以内，通俗易懂）"
    }}
  ],
  "references": [
    {{
      "title": "参考资源标题",
      "url": "相关链接",
      "description": "简要说明"
    }}
  ],
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6"],
  "community_discussion": "模拟社区可能的讨论焦点（中文，2-3句）"
}}
```

## 输出要求:

1. **background**: 提取 2-3 个文中涉及的专业概念，用通俗语言解释
2. **why_it_matters**: 说明对保险公司、消费者、监管层的不同影响
3. **whats_new**: 强调这条资讯相比以往有何新意
4. **references**: 推荐 2-3 个高质量相关资源（维基百科、官方文档、权威报道）
5. **tags**: 生成 6-8 个标签，涵盖：细分领域、技术/业务类型、影响范围、地域
6. **community_discussion**: 预测 HackerNews/Reddit 等专业社区可能的讨论角度

请确保 JSON 格式正确，不要包含任何其他文本。"""


class InsuranceEnricher:
    """保险资讯内容增强器 - Horizon 风格"""

    def __init__(self, config: dict):
        self.config = config
        self.ai_config = get_ai_config(config)
        self.scoring_config = get_scoring_config(config)
        self.enrichment_threshold = config.get("enrichment", {}).get("score_threshold_for_enrichment", 7.0)

    async def _call_ai(self, prompt: str) -> str:
        """调用 AI 模型"""
        provider = self.ai_config.get("provider", "openai")
        model = self.ai_config.get("model", "gpt-4o")
        api_key = get_env_var(self.ai_config.get("api_key_env", "OPENAI_API_KEY"))
        base_url = self.ai_config.get("base_url", "")

        if not api_key or api_key == "sk-your-openai-key":
            # 无 API Key 时使用模拟数据
            return self._generate_mock_response()

        if provider in ("openai", "ali"):
            from openai import AsyncOpenAI

            if provider == "ali" and not base_url:
                base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

            client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
            
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是保险行业专家，擅长深度分析和背景补充。请严格输出JSON格式。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"} if "gpt-4" in model else None,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"[Enricher] AI 调用失败: {e}")
                return self._generate_mock_response()

        elif provider == "anthropic":
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system="你是保险行业专家，擅长深度分析和背景补充。请严格输出JSON格式。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return response.content[0].text
            except Exception as e:
                print(f"[Enricher] AI 调用失败: {e}")
                return self._generate_mock_response()

        else:
            raise ValueError(f"不支持的 AI 提供商: {provider}")

    def _generate_mock_response(self) -> str:
        """生成模拟增强数据（用于测试）"""
        return json.dumps({
            "whats_new": "这是该领域近期的重要进展，具有时效性和创新性。",
            "why_it_matters": "该资讯对保险行业的业务模式、技术应用或监管环境可能产生深远影响，值得行业从业者关注。",
            "key_details": "关键信息包括具体的数据指标、实施时间节点、涉及的主体范围等。",
            "background": [
                {
                    "concept": "保险科技",
                    "explanation": "运用科技手段改进保险业务流程，提升效率和用户体验"
                },
                {
                    "concept": "偿付能力",
                    "explanation": "保险公司履行赔付义务的能力，是监管核心指标"
                }
            ],
            "references": [
                {
                    "title": "保险监管政策解读",
                    "url": "https://www.nfra.gov.cn",
                    "description": "金融监管总局官方政策文件"
                }
            ],
            "tags": ["保险科技", "监管政策", "行业动态", "数字化转型", "风险管理"],
            "community_discussion": "专业人士可能讨论该政策的实施细节、对不同类型保险公司的差异化影响，以及行业应对策略。"
        }, ensure_ascii=False)

    def _parse_response(self, response_text: str) -> EnrichmentResult:
        """解析增强结果"""
        text = response_text.strip()
        
        # 去掉 markdown code block
        if text.startswith("```"):
            lines = text.split("\n")
            # 找到第一个 { 和最后一个 }
            start = -1
            end = -1
            for i, line in enumerate(lines):
                if "{" in line and start == -1:
                    start = i
                if "}" in line:
                    end = i
            if start >= 0 and end >= start:
                text = "\n".join(lines[start:end+1])
            else:
                text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
            return EnrichmentResult(
                whats_new=data.get("whats_new", ""),
                why_it_matters=data.get("why_it_matters", ""),
                key_details=data.get("key_details", ""),
                background=data.get("background", []),
                references=data.get("references", []),
                tags=data.get("tags", []),
                community_discussion=data.get("community_discussion", ""),
            )
        except json.JSONDecodeError as e:
            print(f"[Enricher] JSON 解析失败: {e}")
            # 尝试提取 JSON
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                    return EnrichmentResult(
                        whats_new=data.get("whats_new", ""),
                        why_it_matters=data.get("why_it_matters", ""),
                        key_details=data.get("key_details", ""),
                        background=data.get("background", []),
                        references=data.get("references", []),
                        tags=data.get("tags", []),
                        community_discussion=data.get("community_discussion", ""),
                    )
                except:
                    pass
            return EnrichmentResult()

    async def enrich_item(self, item: "NewsItem") -> "NewsItem":
        """增强单条资讯"""
        # 构造 prompt
        prompt = ENRICHMENT_PROMPT_V2.format(
            title=item.title,
            content=item.content[:1000] if item.content else "",
            source=item.source_name,
            summary=item.ai_summary or "",
            tags=", ".join(item.ai_tags) if item.ai_tags else "",
        )

        # 调用 AI
        try:
            response = await self._call_ai(prompt)
            result = self._parse_response(response)

            # 更新 item
            item.whats_new = result.whats_new
            item.why_it_matters = result.why_it_matters
            item.key_details = result.key_details
            item.background = result.background
            item.references = result.references
            item.community_discussion = result.community_discussion
            
            # 合并标签（去重）
            existing_tags = set(item.ai_tags) if item.ai_tags else set()
            new_tags = set(result.tags)
            item.ai_tags = list(existing_tags | new_tags)[:10]  # 最多10个标签

            # 组合详细摘要（Horizon 风格）
            parts = []
            if result.whats_new:
                parts.append(f"**最新动态**: {result.whats_new}")
            if result.why_it_matters:
                parts.append(f"**行业影响**: {result.why_it_matters}")
            if result.key_details:
                parts.append(f"**关键细节**: {result.key_details}")
            if result.community_discussion:
                parts.append(f"**社区讨论**: {result.community_discussion}")
            
            # 添加背景知识
            if result.background:
                bg_parts = []
                for bg in result.background[:3]:
                    bg_parts.append(f"- **{bg.get('concept', '')}**: {bg.get('explanation', '')}")
                if bg_parts:
                    parts.append(f"**背景知识**:\n" + "\n".join(bg_parts))
            
            # 添加参考链接
            if result.references:
                ref_parts = []
                for ref in result.references[:3]:
                    ref_parts.append(f"- [{ref.get('title', '')}]({ref.get('url', '')}) - {ref.get('description', '')}")
                if ref_parts:
                    parts.append(f"**参考链接**:\n" + "\n".join(ref_parts))
            
            item.detailed_summary = "\n\n".join(parts)

        except Exception as e:
            print(f"[Enricher] 增强失败 ({item.title[:30]}...): {e}")

        return item

    async def enrich_all(self, items: list["NewsItem"]) -> list["NewsItem"]:
        """增强所有高分资讯"""
        # 仅增强超过阈值的项目
        to_enrich = [item for item in items if item.ai_score >= self.enrichment_threshold]

        print(f"[Enricher] 需要增强 {len(to_enrich)}/{len(items)} 条资讯")

        # 并发增强（限制并发数）
        semaphore = asyncio.Semaphore(3)

        async def enrich_with_limit(item: "NewsItem") -> "NewsItem":
            async with semaphore:
                return await self.enrich_item(item)

        enriched = await asyncio.gather(*[enrich_with_limit(item) for item in to_enrich])

        # 合并结果
        enriched_map = {id(item): item for item in enriched}
        for i, item in enumerate(items):
            if id(item) in enriched_map:
                items[i] = enriched_map[id(item)]

        return items
