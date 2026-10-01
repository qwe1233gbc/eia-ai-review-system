"""OpenAI 兼容接口客户端：LLM 对话（function calling）与文本 Embedding。"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from .config import settings


class LLMError(RuntimeError):
    pass


def embed(texts: List[str]) -> List[np.ndarray]:
    """调用 text-embedding 接口，返回 L2 归一化后的向量数组。"""
    if not texts:
        return []
    resp = requests.post(
        f"{settings.EMBEDDING_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.EMBEDDING_MODEL,
            "input": texts,
            "dimensions": 1024,
            "encoding_format": "float",
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    out: List[np.ndarray] = []
    for item in data.get("data", []):
        v = np.asarray(item["embedding"], dtype="float32")
        norm = float(np.linalg.norm(v))
        out.append(v / max(norm, 1e-12))
    return out


def chat_completion(
    system: str,
    user: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    max_attempts: int = 2,
) -> Dict[str, Any]:
    """调用 /chat/completions，返回 function-call 的 arguments（或 message content）。

    支持 tool_choice=required 强制结构化输出；失败后按工程原因（传输/JSON/校验）重试，
    不做答案质量相关重试。
    """
    url = f"{settings.LLM_BASE_URL}/chat/completions"
    payload: Dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        # DashScope qwen3 非流式调用必须显式关闭思考模式
        "enable_thinking": False,
    }
    if tools:
        payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

    last_err = ""
    for attempt in range(max_attempts):
        start = time.time()
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # 传输/HTTP 错误
            last_err = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            raise LLMError(f"API 调用失败: {last_err[:200]}") from e

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        # 优先解析 function call
        tool_calls = message.get("tool_calls")
        if tool_calls:
            return _parse_tool_call(tool_calls[0])

        content = message.get("content")
        if content:
            return {"_type": "text", "content": content}

        last_err = "空响应（无 tool_calls 也无 content）"
        if attempt < max_attempts - 1:
            continue
        raise LLMError(last_err)

    raise LLMError(last_err or "重试耗尽")


def _parse_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    import json

    fn = tool_call.get("function") or {}
    raw = fn.get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        raise LLMError(f"tool-call arguments 非 JSON: {raw[:200]}")
    return {"_type": "function", "name": fn.get("name", ""), "arguments": args}