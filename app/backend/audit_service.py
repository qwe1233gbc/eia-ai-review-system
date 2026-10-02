"""审核编排：报告文本 → 检索 → LLM(function calling) → 结构化结果。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator, List, Tuple

from .config import settings
from .llm_client import chat_completion
from .mock_data import MOCK_RESULT
from .retrieval import get_retriever
from .schemas import AuditIssue, AuditResult, RegulatoryBasis, RetrievedSource

TOPIC_LABELS = {
    "emission_standards": "排放标准准确性",
}

_SYSTEM_PROMPT = """你是一名专业的环境影响评价报告审核人员，专门核查建设项目环境影响报告表中"污染物排放控制标准"的准确性。

【审核维度】逐一核查报告引用的排放标准：
1. 标准名称是否准确
2. 标准编号是否准确（含年号）
3. 表号/条款是否准确
4. 污染物种类是否完整、准确
5. 排放限值是否准确
6. 单位是否正确
7. 控制位置（有组织排气筒 / 厂界无组织监控点等）是否明确
8. 标准适用性（行业标准优先于综合标准；地方标准严于国家标准）

【判定原则】
- 结合"知识库检索证据"与报告上下文判断，不得脱离证据臆造
- 优先引用行业标准（如 GB 31572-2015）与广东省/佛山市地方标准（如 DB44/2367-2022）
- 区分"实质性错误"（标准名称、编号、限值、适用对象错误）与"次要问题"（表述不完整、未注明执行档位）
- 报告未提及、且证据不足以确认的内容，标记为"待确认"，不要编造标准名称、编号、条款或限值
- 风险等级：高＝实质性错误导致结论不可靠；中＝次要但需更正；低＝表述完善性建议

【输出】必须调用 submit_eia_review 输出结构化审核结果，不要输出任何额外文字。"""

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_eia_review",
        "description": "提交环评报告排放标准准确性审核结果",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "总体审核结论"},
                "risk_level": {"type": "string", "enum": ["高", "中", "低"]},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": ["标准名称", "标准编号", "表号", "污染物", "限值", "单位", "控制位置", "适用性", "其他"],
                            },
                            "severity": {"type": "string", "enum": ["高", "中", "低"]},
                            "description": {"type": "string", "description": "问题描述"},
                            "reported": {"type": "string", "description": "报告中所填/声称的内容"},
                            "correct_basis": {
                                "type": "object",
                                "properties": {
                                    "standard_name": {"type": "string"},
                                    "standard_no": {"type": "string"},
                                    "clause": {"type": "string"},
                                    "pollutant": {"type": "string"},
                                    "limit": {"type": "string"},
                                    "unit": {"type": "string"},
                                    "control_location": {"type": "string"},
                                    "reference": {"type": "string"},
                                },
                            },
                            "suggestion": {"type": "string", "description": "修改建议"},
                        },
                        "required": ["category", "severity", "description", "suggestion"],
                    },
                },
            },
            "required": ["summary", "risk_level", "issues"],
        },
    },
}

_TOOL_CHOICE = {"type": "function", "function": {"name": "submit_eia_review"}}

_STANDARD_RE = re.compile(
    r"(?:GB|DB|DB44|HJ|HJT|WS|GBZ)\s*[/T]?\s*\d{3,5}(?:[.\-–—]\d{1,4})?(?:-\d{2,4})?",
    re.IGNORECASE,
)

MAX_CONTEXT_CHARS = 12000


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]


def _build_query(text: str) -> str:
    numbers = list(dict.fromkeys(m.group(0) for m in _STANDARD_RE.finditer(text)))
    paras = _split_paragraphs(text)
    relevant = [
        p for p in paras if any(k in p for k in ("标准", "限值", "排放", "mg", "DB44", "GB "))
    ]
    query = " ".join(numbers[:20]) + " " + " ".join(relevant[:10])
    return query[:1500] or text[:1500]


def _build_context(text: str) -> str:
    paras = _split_paragraphs(text)
    preferred = [p for p in paras if any(k in p for k in ("标准", "限值", "GB", "DB", "HJ", "mg", "排放"))]
    rest = [p for p in paras if p not in preferred]
    ordered = preferred + rest
    buf = ""
    for p in ordered:
        if len(buf) + len(p) + 1 > MAX_CONTEXT_CHARS:
            break
        buf += p + "\n"
    return buf or text[:MAX_CONTEXT_CHARS]


def _format_sources(hits: List[dict]) -> str:
    parts = []
    for h in hits:
        parts.append(
            f"【证据{h['rank']}】{h['source_id']} {h['title']}\n{h['snippet']}"
        )
    return "\n\n".join(parts) or "（无检索证据）"


def _to_result(topic: str, arguments: dict, hits: List[dict], model: str, elapsed: float) -> AuditResult:
    issues: List[AuditIssue] = []
    for i, raw in enumerate(arguments.get("issues") or [], 1):
        basis_raw = raw.get("correct_basis") or {}
        issues.append(
            AuditIssue(
                id=f"ISSUE-{i}",
                category=raw.get("category", "其他"),
                severity=raw.get("severity", "中"),
                description=raw.get("description", ""),
                reported=raw.get("reported", ""),
                correct_basis=RegulatoryBasis(
                    standard_name=basis_raw.get("standard_name", ""),
                    standard_no=basis_raw.get("standard_no", ""),
                    clause=basis_raw.get("clause", ""),
                    pollutant=basis_raw.get("pollutant", ""),
                    limit=basis_raw.get("limit", ""),
                    unit=basis_raw.get("unit", ""),
                    control_location=basis_raw.get("control_location", ""),
                    reference=basis_raw.get("reference", ""),
                ),
                suggestion=raw.get("suggestion", ""),
            )
        )
    return AuditResult(
        topic=topic,
        mode="live",
        model=model,
        summary=arguments.get("summary", ""),
        risk_level=arguments.get("risk_level", "中"),
        issues=issues,
        retrieved_sources=[
            RetrievedSource(
                rank=h["rank"],
                score=h["score"],
                source_id=h.get("source_id", ""),
                title=h.get("title", ""),
                snippet=h.get("snippet", ""),
            )
            for h in hits
        ],
        elapsed_seconds=round(elapsed, 2),
    )


def _stage(key: str, label: str, progress: int, eta: int) -> dict:
    return {"stage": key, "label": label, "progress": progress, "eta": eta}


def audit_stream(
    text: str, topic: str = "emission_standards", top_k: int = 5
) -> Iterator[Tuple[str, Any]]:
    """流式审核：依次产出 ("stage", 阶段事件) 与 ("result", AuditResult)。

    阶段事件用于前端展示「当前环节 + 进度 + 预计剩余秒数」。
    """
    # Mock 模式：直接返回示例，验证链路
    if settings.effective_mode:
        yield "stage", _stage("parse", "解析报告文本", 20, 2)
        yield "stage", _stage("retrieve", "检索法规知识库", 60, 1)
        yield "stage", _stage("format", "生成结构化结果", 95, 0)
        res = AuditResult(**MOCK_RESULT)
        res.topic = topic
        yield "result", res
        return

    start = time.time()
    yield "stage", _stage("parse", "解析报告文本", 8, 18)
    query = _build_query(text)
    context = _build_context(text)

    yield "stage", _stage("retrieve", "检索法规知识库", 35, 15)
    hits = get_retriever().search(query, k=top_k)

    yield "stage", _stage("llm", "调用大模型审核", 70, 12)
    user_prompt = (
        f"## 报告文本（排放标准相关章节）\n{context}\n\n"
        f"## 知识库检索证据\n{_format_sources(hits)}\n\n"
        f"请审核该报告排放标准的准确性，并调用 submit_eia_review 输出结构化结果。"
    )
    try:
        reply = chat_completion(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            tools=[_TOOL_SCHEMA],
            tool_choice=_TOOL_CHOICE,
        )
    except Exception as e:
        yield "result", AuditResult(
            topic=topic,
            mode="live",
            model=settings.LLM_MODEL,
            summary=f"审核失败：{str(e)[:200]}",
            risk_level="中",
            issues=[],
            retrieved_sources=[
                RetrievedSource(
                    rank=h["rank"], score=h["score"], source_id=h.get("source_id", ""),
                    title=h.get("title", ""), snippet=h.get("snippet", ""),
                )
                for h in hits
            ],
            elapsed_seconds=round(time.time() - start, 2),
        )
        return

    yield "stage", _stage("format", "生成结构化结果", 95, 1)

    if reply.get("_type") == "function":
        arguments = reply.get("arguments") or {}
    else:
        # 模型未走 function call，尝试解析纯文本 JSON
        content = reply.get("content", "")
        arguments = {}
        try:
            arguments = json.loads(content.strip())
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                try:
                    arguments = json.loads(m.group(0))
                except json.JSONDecodeError:
                    arguments = {"summary": content[:500], "risk_level": "中", "issues": []}

    yield "result", _to_result(topic, arguments, hits, settings.LLM_MODEL, time.time() - start)


def audit(text: str, topic: str = "emission_standards", top_k: int = 5) -> AuditResult:
    """同步审核（内部消费 audit_stream），供非流式接口使用。"""
    result: Any = None
    for kind, payload in audit_stream(text, topic, top_k):
        if kind == "result":
            result = payload
    return result