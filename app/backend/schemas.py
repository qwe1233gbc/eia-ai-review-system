"""数据契约：审核请求与结构化审核结果。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AuditRequest(BaseModel):
    """审核请求体：可传文本，或由前端先上传后回传文件名。"""

    text: Optional[str] = Field(default=None, description="报告全文（未上传文件时）")
    filename: Optional[str] = Field(default=None, description="报告文件名")
    topic: str = Field(default="emission_standards", description="审核主题")
    top_k: int = Field(default=5, ge=1, le=20, description="知识库检索命中条数")


class RegulatoryBasis(BaseModel):
    """正确依据（来自知识库检索 / LLM 判断）。"""

    standard_name: str = ""
    standard_no: str = ""
    clause: str = ""
    pollutant: str = ""
    limit: str = ""
    unit: str = ""
    control_location: str = ""
    reference: str = ""


class AuditIssue(BaseModel):
    """单条审核问题。"""

    id: str = Field(description="问题序号，如 ISSUE-1")
    category: str = Field(
        description="问题类别：标准名称/标准编号/表号/污染物/限值/单位/控制位置/适用性/其他"
    )
    severity: str = Field(description="风险等级：高/中/低")
    description: str = Field(description="问题描述")
    reported: str = Field(default="", description="报告中所填/声称的内容")
    correct_basis: RegulatoryBasis = Field(default_factory=RegulatoryBasis)
    suggestion: str = Field(default="", description="修改建议")


class RetrievedSource(BaseModel):
    """知识库检索命中记录（用于前端展示证据来源）。"""

    rank: int
    score: float
    source_id: str = ""
    title: str = ""
    snippet: str = ""


class AuditResult(BaseModel):
    """审核结果。"""

    topic: str = "emission_standards"
    mode: str = Field(description="mock / live")
    model: str = ""
    summary: str = Field(description="总体审核结论")
    risk_level: str = Field(description="整体风险等级：高/中/低")
    issues: List[AuditIssue] = Field(default_factory=list)
    retrieved_sources: List[RetrievedSource] = Field(default_factory=list)
    elapsed_seconds: float = 0.0