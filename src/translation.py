"""翻译服务 - 支持多语言内容翻译为中文"""

from __future__ import annotations
import os
from typing import Optional
from dataclasses import dataclass
import re


@dataclass
class TranslationResult:
    """翻译结果"""
    original: str
    translated: str
    source_lang: str
    target_lang: str = "zh"
    success: bool = True
    error: Optional[str] = None


class TranslationService:
    """翻译服务基类"""

    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        """翻译文本"""
        raise NotImplementedError

    def translate_batch(self, texts: list[str], source_lang: str = "en", target_lang: str = "zh") -> list[TranslationResult]:
        """批量翻译"""
        return [self.translate(t, source_lang, target_lang) for t in texts]


class GoogleFreeTranslation(TranslationService):
    """免费 Google Translate (使用 deep_translator)"""

    def __init__(self):
        self._translator = None

    def _get_translator(self):
        """延迟加载翻译器"""
        if self._translator is None:
            try:
                from deep_translator import GoogleTranslator
                self._translator = GoogleTranslator(source='en', target='zh-CN')
            except ImportError:
                return None
        return self._translator

    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", source_lang=source_lang, success=True)

        try:
            translator = self._get_translator()
            if translator is None:
                return TranslationResult(
                    original=text, translated=text, source_lang=source_lang,
                    success=False, error="deep-translator 库未安装"
                )

            translated = translator.translate(text)

            if translated:
                return TranslationResult(
                    original=text, translated=translated,
                    source_lang=source_lang, success=True
                )
            else:
                return TranslationResult(
                    original=text, translated=text, source_lang=source_lang,
                    success=False, error="翻译结果为空"
                )

        except Exception as e:
            return TranslationResult(
                original=text, translated=text, source_lang=source_lang,
                success=False, error=str(e)
            )


class ZhipuTranslation(TranslationService):
    """智谱 GLM 翻译 (推荐 - 国内可用)"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
        self.api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", source_lang=source_lang, success=True)

        if not self.api_key:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error="ZHIPU_API_KEY 未设置"
            )

        try:
            import httpx

            lang_map = {"en": "英文", "ja": "日文", "ko": "韩文", "fr": "法文", "de": "德文"}
            source_name = lang_map.get(source_lang, source_lang)

            prompt = f"""你是一个专业的翻译专家。请将以下{source_name}内容准确翻译成中文，保持原文的专业术语和风格。

翻译要求：
1. 保险、金融、法律等专业术语保持准确
2. 保持原文的语气和风格
3. 专有名词首次出现时可保留英文原文
4. 翻译自然流畅，符合中文阅读习惯
5. 直接输出翻译结果，不要添加任何解释

原文：
{text}"""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "model": "glm-4-flash",
                "messages": [
                    {"role": "system", "content": "你是一个专业的翻译专家。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.api_url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()

            translated = result["choices"][0]["message"]["content"].strip()
            translated = re.sub(r'^["""]|["""]$', '', translated)

            return TranslationResult(
                original=text,
                translated=translated,
                source_lang=source_lang,
                success=True
            )

        except Exception as e:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error=str(e)
            )


class OpenAITranslation(TranslationService):
    """OpenAI GPT 翻译"""

    def __init__(self, api_key: Optional[str] = None, base_url: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", source_lang=source_lang, success=True)

        if not self.api_key:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error="OPENAI_API_KEY 未设置"
            )

        try:
            import httpx

            lang_map = {"en": "英文", "ja": "日文", "ko": "韩文", "fr": "法文", "de": "德文"}
            source_name = lang_map.get(source_lang, source_lang)

            prompt = f"""Translate the following {source_name} text to Chinese. Maintain professional terminology for insurance, finance, and legal content. Output only the translation.

原文：
{text}"""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a professional translator."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=data)
                response.raise_for_status()
                result = response.json()

            translated = result["choices"][0]["message"]["content"].strip()
            translated = re.sub(r'^["""]|["""]$', '', translated)

            return TranslationResult(
                original=text,
                translated=translated,
                source_lang=source_lang,
                success=True
            )

        except Exception as e:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error=str(e)
            )


class ClaudeTranslation(TranslationService):
    """Anthropic Claude 翻译"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", source_lang=source_lang, success=True)

        if not self.api_key:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error="ANTHROPIC_API_KEY 未设置"
            )

        try:
            import httpx

            lang_map = {"en": "English", "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German"}
            source_name = lang_map.get(source_lang, source_lang)

            prompt = f"""Translate the following {source_name} text to Chinese. Maintain professional terminology for insurance, finance, and legal content.

Text:
{text}"""

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }

            data = {
                "model": "claude-3-haiku-20240307",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 2000
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=data)
                response.raise_for_status()
                result = response.json()

            translated = result["content"][0]["text"].strip()

            return TranslationResult(
                original=text,
                translated=translated,
                source_lang=source_lang,
                success=True
            )

        except Exception as e:
            return TranslationResult(
                original=text,
                translated=text,
                source_lang=source_lang,
                success=False,
                error=str(e)
            )


def get_translation_service(provider: str = "auto") -> TranslationService:
    """获取翻译服务实例

    provider 选项:
    - "auto": 自动选择 (优先付费服务，其次免费)
    - "zhipu": 智谱 GLM (推荐国内使用)
    - "openai": OpenAI GPT
    - "claude": Anthropic Claude
    - "google_free": 免费 Google Translate
    """
    # 自动选择
    if provider == "auto":
        # 优先检查付费服务
        if os.environ.get("ZHIPU_API_KEY"):
            return ZhipuTranslation()
        elif os.environ.get("OPENAI_API_KEY"):
            return OpenAITranslation()
        elif os.environ.get("ANTHROPIC_API_KEY"):
            return ClaudeTranslation()
        else:
            # 使用免费服务
            return GoogleFreeTranslation()

    providers = {
        "zhipu": ZhipuTranslation,
        "openai": OpenAITranslation,
        "claude": ClaudeTranslation,
        "google_free": GoogleFreeTranslation,
    }

    service_class = providers.get(provider.lower())
    if not service_class:
        raise ValueError(f"不支持的翻译服务: {provider}")

    return service_class()
