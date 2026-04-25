"""InternLM API 客户端封装（OpenAI SDK 兼容）"""

import json
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from . import config


class LLMClient:
    """封装 InternLM API 调用"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.API_BASE
        self.model = model or config.MODEL_NAME

        if not self.api_key:
            raise ValueError("API Key 未设置，请配置环境变量 INTERNLM_API_KEY")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None, max_retries: int = 3) -> str:
        """发送单轮对话请求，返回模型生成的文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        temp = temperature if temperature is not None else config.TEMPERATURE

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=config.MAX_TOKENS,
                    timeout=config.REQUEST_TIMEOUT,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 调用失败（重试{max_retries}次）: {e}") from e

        return ""

    def chat_json(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None, max_retries: int = 3) -> Any:
        """发送请求并尝试将返回解析为 JSON"""
        raw = self.chat(user_prompt, system_prompt, temperature, max_retries)
        raw = raw.strip()
        if raw.startswith("```"):
            # 去除 markdown 代码块
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            # 尝试修复常见的 JSON 格式问题
            try:
                # 有时模型会输出带注释的 JSON 或多余逗号
                fixed = _fix_json(raw)
                return json.loads(fixed)
            except Exception:
                raise RuntimeError(f"LLM 返回无法解析为 JSON: {e}\n原始文本前500字: {raw[:500]}") from e


def _fix_json(text: str) -> str:
    """简单修复常见 JSON 格式问题"""
    # 去除尾部逗号
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 去除注释
    text = re.sub(r"//.*?\n", "\n", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


import re  # noqa: E402
