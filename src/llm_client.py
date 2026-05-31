"""InternLM API 客户端封装（OpenAI SDK 兼容）"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI

from . import config


def _is_timeout_error(e: Exception) -> bool:
    """判断异常是否为超时类错误"""
    type_name = type(e).__name__.lower()
    if "timeout" in type_name:
        return True
    return "timeout" in str(e).lower() or "timed out" in str(e).lower()


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
                    wait = 15 * (attempt + 1) if _is_timeout_error(e) else 2 ** attempt
                    print(f"[LLMClient] 请求失败（{type(e).__name__}），{wait}s 后重试（第{attempt + 1}次）...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 调用失败（重试{max_retries}次）: {e}") from e

        return ""

    def chat_json(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None, max_retries: int = 3) -> Any:
        """发送请求并尝试将返回解析为 JSON"""
        raw = self.chat(user_prompt, system_prompt, temperature, max_retries)
        return _parse_json_response_shared(raw)


def _extract_json_from_text(text: str) -> str:
    """从含有前缀说明文字的响应中提取 JSON 部分

    处理 LLM 在 JSON 前输出解释性文字的情况，例如：
        "由于文本被截断，以下是抽取结果：\n```json\n[]\n```"
        "文本不完整，但我尽力抽取：\n{...}"

    策略（按优先级）：
    1. 找 ```json ... ``` 或 ``` ... ``` 代码块内的内容
    2. 找第一个 { 或 [ 作为 JSON 起点，向后扫描匹配的括号
    3. 返回原文（交给调用方处理）
    """
    # 策略1：markdown 代码块（可能被前缀说明文字包围）
    code_block = re.search(r"```(?:json)?\s*\n?([\s\S]+?)\n?```", text)
    if code_block:
        return code_block.group(1).strip()

    # 策略2：找第一个 JSON 起始字符 { 或 [
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            candidate = text[i:]
            # 快速验证：找到对应的结束括号
            close = '}' if ch == '{' else ']'
            last_close = candidate.rfind(close)
            if last_close != -1:
                return candidate[:last_close + 1].strip()
            return candidate.strip()

    return text


def _fix_json(text: str) -> str:
    """简单修复常见 JSON 格式问题"""
    # 去除尾部逗号
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 去除注释
    text = re.sub(r"//.*?\n", "\n", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _fix_string_content(text: str) -> str:
    """修复 JSON 字符串值内的非法字符和疑似未转义引号

    逐字符扫描 JSON，在字符串值内：
    - 将原始控制字符（0x00-0x1F）替换为合法的 JSON 转义序列
    - 对疑似嵌入的裸 " 进行转义（通过后向检查判断真正的字符串结束位置）
    """
    result: list = []
    i = 0
    n = len(text)
    in_string = False
    _ctrl_escape = {'\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f'}

    while i < n:
        ch = text[i]
        if in_string:
            if ch == '\\':
                # 合法转义序列，原样保留（跳过两个字符）
                result.append(ch)
                if i + 1 < n:
                    result.append(text[i + 1])
                    i += 2
                else:
                    i += 1
                continue
            elif ch == '"':
                # 向后扫描，检查此引号后第一个非空白字符是否为合法 JSON 分隔符
                j = i + 1
                while j < n and text[j] in ' \t\r\n':
                    j += 1
                if j >= n or text[j] in (',', '}', ']', ':'):
                    # 合法结束引号
                    in_string = False
                    result.append(ch)
                else:
                    # 疑似嵌入引号，转义
                    result.append('\\"')
                i += 1
                continue
            elif ord(ch) < 0x20:
                # 控制字符：转为合法 JSON 转义（\n/\r/\t 等），其余替换为空格
                result.append(_ctrl_escape.get(ch, ' '))
                i += 1
                continue
        else:
            if ch == '"':
                in_string = True
        result.append(ch)
        i += 1

    return ''.join(result)


def _repair_truncated_json(text: str) -> str:
    """修复被 max_tokens 截断的 JSON

    支持两种场景：
    A. 数组被截断：[完整对象, 完整对象, 残缺对象...
       → 提取所有完整顶层对象，重组为合法数组
    B. 顶层对象被截断：{"key": "val", "key2": "val2截断
       → 找最后一个属性分隔逗号，截断并补 }
    """
    text = text.strip()
    if not text:
        return text

    is_array = text.startswith('[')

    # 用状态机逐字符扫描
    # complete_objects：数组场景收集到的完整 {...}
    # top_commas：顶层结构内（depth==1）的属性/元素分隔逗号位置
    complete_objects: list = []
    depth = 0
    obj_start = -1
    in_string = False
    top_commas: list = []  # depth==1 时的逗号位置
    i = 0

    # 数组场景：顶层对象位于 depth==1（[后面），闭合时 depth 从2→1
    # 对象场景：顶层对象位于 depth==0，闭合时 depth 从1→0
    obj_open_depth = 1 if is_array else 0
    obj_close_depth = 1 if is_array else 0

    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == '\\':
                i += 2
                continue
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch in ('{', '['):
                if depth == obj_open_depth and ch == '{':
                    obj_start = i
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
                if depth == obj_close_depth and obj_start != -1 and ch == '}':
                    complete_objects.append(text[obj_start:i + 1])
                    obj_start = -1
            elif ch == ',' and depth == 1:
                # depth==1：数组元素之间 或 对象属性之间
                top_commas.append(i)
        i += 1

    # 场景A：数组，恢复所有完整顶层 {...} 对象
    if is_array and complete_objects:
        return '[' + ', '.join(complete_objects) + ']'

    # 场景B：顶层对象被截断（开头是 { 但没有完整闭合）
    if not is_array and not complete_objects and text.startswith('{') and top_commas:
        last_comma = top_commas[-1]
        repaired = text[:last_comma].rstrip() + '\n}'
        return repaired

    # 非数组且找到了完整对象，返回第一个
    if not is_array and complete_objects:
        return complete_objects[0]

    return text


def _parse_json_response_shared(raw: str) -> Any:
    """统一的 JSON 响应解析逻辑（供同步/异步客户端共用）

    解析顺序：
    1. 直接 json.loads
    2. 提取 JSON 片段（去除前缀说明文字、markdown 代码块）后再解析
    3. 对提取结果做简单 fix（去除尾逗号、注释）后再解析
    4. 对原始文本做简单 fix 后再解析
    4.5. 全局替换 \r\n\t 为空格后再解析
    4.6. 字符级修复——转义字符串值内的控制字符和疑似嵌入引号后再解析
    5. 修复截断 JSON（提取所有完整顶层对象）后再解析
    """
    raw = raw.strip()

    # 第1步：直接解析（最快路径，LLM 输出规范时命中）
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 第2步：提取 JSON 片段（处理前缀说明文字和 markdown 代码块）
    extracted = _extract_json_from_text(raw)
    if extracted != raw:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass
        # 第3步：对提取结果再做简单 fix
        try:
            return json.loads(_fix_json(extracted))
        except json.JSONDecodeError:
            pass

    # 第4步：对原始文本做简单 fix
    try:
        return json.loads(_fix_json(raw))
    except json.JSONDecodeError:
        pass

    # 第4.5步：清理字符串内的原始控制字符（JSON 规范不允许字符串值中出现原始换行/制表符）
    # LLM 有时在长文本字段（如 main_business）中插入未转义的 \n，导致 "Expecting ',' delimiter"
    cleaned = re.sub(r'[\r\n\t]', ' ', raw)
    if cleaned != raw:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_fix_json(cleaned))
        except json.JSONDecodeError:
            pass

    # 第4.6步：字符级修复——转义字符串值内的控制字符和疑似嵌入引号
    # 处理 LLM 在 main_business 等长文本字段中输出未转义 " 的情况
    fixed = _fix_string_content(raw)
    if fixed != raw:
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_fix_json(fixed))
        except json.JSONDecodeError:
            pass
    # 同时尝试对 extracted 片段做字符级修复
    if extracted != raw:
        fixed_extracted = _fix_string_content(extracted)
        if fixed_extracted != extracted:
            try:
                return json.loads(fixed_extracted)
            except json.JSONDecodeError:
                pass
            try:
                return json.loads(_fix_json(fixed_extracted))
            except json.JSONDecodeError:
                pass

    # 第5步：截断修复——提取所有完整顶层对象，丢弃末尾残缺部分
    # 处理 max_tokens 截断或字符串内含未转义换行等问题
    # 优先修复 fixed/cleaned/raw（保留更多字段），再尝试 extracted（可能在不同位置截断）
    repair_targets = [fixed if fixed != raw else (cleaned if cleaned != raw else raw), raw]
    # 去重（cleaned 可能等于 raw）
    seen_targets: set = set()
    repair_targets = [t for t in repair_targets if not (t in seen_targets or seen_targets.add(t))]
    if extracted != raw:
        repair_targets.append(extracted)
    for repair_target in repair_targets:
        repaired = _repair_truncated_json(repair_target)
        if repaired != repair_target:
            try:
                result = json.loads(repaired)
                count = len(result) if isinstance(result, list) else 1
                print(f"[LLMClient] 截断修复成功，恢复 {count} 条记录")
                return result
            except json.JSONDecodeError:
                pass

    # 所有策略均失败，抛出原始错误
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM 返回无法解析为 JSON: {e}\n原始文本前500字: {raw[:500]}"
        ) from e
    # 理论上不会执行到这里
    return None



class AsyncLLMClient:
    """异步 InternLM API 客户端，支持并发请求和限流"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.API_BASE
        self.model = model or config.MODEL_NAME

        print(f"AsyncLLMClient 初始化, Base URL: {self.base_url}, Model: {self.model}")
        if not self.api_key:
            raise ValueError("API Key 未设置，请配置环境变量 INTERNLM_API_KEY")

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self._semaphore = asyncio.Semaphore(30)
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._min_interval = 2.0

    async def _rate_limit_wait(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

    async def chat_json_async(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None, max_retries: int = 3) -> Any:
        async with self._semaphore:
            await self._rate_limit_wait()
            return await self._chat_with_retry(user_prompt, system_prompt, temperature, max_retries)

    async def _chat_with_retry(self, user_prompt: str, system_prompt: Optional[str], temperature: Optional[float], max_retries: int) -> Any:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        temp = temperature if temperature is not None else config.TEMPERATURE

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=config.MAX_TOKENS,
                    timeout=config.REQUEST_TIMEOUT,
                )
                raw = response.choices[0].message.content or ""
                return self._parse_json_response(raw)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 15 * (attempt + 1) if _is_timeout_error(e) else 2 ** attempt
                    print(f"[LLMClient] 请求失败（{type(e).__name__}），{wait}s 后重试（第{attempt + 1}次）...")
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 调用失败（重试{max_retries}次）: {e}") from e

    def _parse_json_response(self, raw: str) -> Any:
        return _parse_json_response_shared(raw)
