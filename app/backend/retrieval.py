"""知识库检索：FAISS(余弦) + BM25 融合，复用已冻结的"检索索引_六文件"。

索引一旦加载常驻内存（单例），避免每次请求重复 IO。
仅 live 模式调用在线 embedding；embedding 失败时自动回退纯 BM25。
"""
from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from .config import settings
from .llm_client import embed

K1 = 1.5
B = 0.75
DENSE_WEIGHT = 0.6
SPARSE_WEIGHT = 0.4


def _clean_snippet(text: str) -> str:
    """清洗知识库片段：去除 HTML 标签/实体、孤立属性碎片、LaTeX 命令、Markdown 标记等噪声，输出可读纯文本。"""
    t = text or ""
    # 实体解码（先做，避免 &lt;td&gt; 这类转义标签漏网）
    t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("&amp;", "&").replace("&#60;", "<").replace("&#62;", ">")
    # 去掉属性赋值（含引号值与裸值），覆盖 text 被截断后残留的孤立属性
    t = re.sub(
        r"\b(?:colspan|rowspan|width|height|align|valign|style|class|id|border"
        r"|cellspacing|cellpadding|bgcolor|nowrap|scope|headers)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        " ",
        t,
    )
    # 去掉完整标签与孤立尖括号
    t = re.sub(r"<[^>]*>", " ", t)
    t = re.sub(r"(?<![<>=])>", " ", t)
    t = t.replace("<", " ")
    t = re.sub(r'(?<=[\w"])"', " ", t)
    # 去掉 text 被截断后残留的孤立标签名/属性名（如 "td rowspan"）
    t = re.sub(
        r"\b(?:table|tbody|thead|tfoot|tr|td|th|span|div|font|html|body|colgroup|col)\b",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"\b(?:colspan|rowspan|cellspacing|cellpadding|valign|bgcolor|nowrap|width|height|align|border)\b",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    # LaTeX / 单位 / 标记
    t = t.replace("[表格已提取]", " ").replace("▓", " ")
    t = re.sub(r"\$+", " ", t)
    t = re.sub(r"\\[a-zA-Z]+", " ", t)
    t = re.sub(r"\^\s*\{?\s*3\s*\}?", "³", t)
    t = re.sub(r"\^\s*\{?\s*2\s*\}?", "²", t)
    t = re.sub(r"[{}_\\]", "", t)
    t = re.sub(r"#+\s*", " ", t)
    for pat, rep in (
        (r"T\s+V\s+O\s+C", "TVOC"),
        (r"V\s+O\s+C\s*s", "VOCs"),
        (r"V\s+O\s+C", "VOC"),
        (r"N\s+M\s+H\s+C", "NMHC"),
    ):
        t = re.sub(pat, rep, t)
    t = re.sub(r"m\s+³", "m³", t)
    t = re.sub(r"m\s+²", "m²", t)
    t = re.sub(r"\bm\s+g\b", "mg", t)
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _tokens(text: str) -> List[str]:
    s = text.lower()
    out = re.findall(r"[a-z]+(?:[._/-][a-z0-9]+)*|\d+(?:[._/-]\d+)*", s)
    cs = re.findall(r"[\u4e00-\u9fff]", s)
    out.extend(cs)
    out.extend(a + b for a, b in zip(cs, cs[1:]))
    return out


class Retriever:
    def __init__(self, index_dir: str):
        self.index_dir = Path(index_dir)
        self._lock = threading.Lock()
        self._loaded = False
        self._metadata: List[dict] = []
        self._bm25: dict = {}
        self._index = None

    def _load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            idx_dir = self.index_dir
            meta_path = idx_dir / "child_metadata.jsonl"
            bm_path = idx_dir / "bm25_index.json"
            faiss_path = idx_dir / "child_cosine_flat.index"
            missing = [p.name for p in (meta_path, bm_path, faiss_path) if not p.exists()]
            if missing:
                raise RuntimeError(f"检索索引缺失: {missing}（VECTOR_DB_PATH={idx_dir}）")

            self._metadata = [
                json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            self._bm25 = json.loads(bm_path.read_text(encoding="utf-8"))
            self._index = self._load_faiss(faiss_path)
            self._loaded = True

    @staticmethod
    def _load_faiss(src: Path):
        # faiss C 层无法直接读取含中文的 Windows 路径：先复制到 ASCII 临时目录
        tmp = Path(tempfile.mkdtemp(prefix="faiss_srv_"))
        dst = tmp / "idx.index"
        with src.open("rb") as a, dst.open("wb") as b:
            shutil.copyfileobj(a, b)
        try:
            return faiss.read_index(str(dst))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _bm25_search(self, query: str, k: int) -> List[tuple]:
        bm = self._bm25
        postings = bm["postings"]
        doclen = bm["doc_lengths"]
        n = bm["document_count"]
        avgdl = bm["average_document_length"]
        qtf = Counter(_tokens(query))
        scores: defaultdict = defaultdict(float)
        for t, c in qtf.items():
            pl = postings.get(t) or []
            w = c * math.log1p((n - len(pl) + 0.5) / (len(pl) + 0.5))
            for doc, cnt in pl:
                denom = cnt + K1 * (1 - B + B * doclen[doc] / avgdl)
                scores[doc] += w * cnt / denom
        return sorted(scores.items(), key=lambda x: -x[1])[:k]

    def search(self, query: str, k: int = 5) -> List[dict]:
        self._load()
        meta = self._metadata

        # 稀疏召回
        sparse = self._bm25_search(query, k)
        smax = max((s for _, s in sparse), default=0.0)
        sparse_norm = {doc: (s / smax if smax > 0 else 0.0) for doc, s in sparse}

        # 稠密召回（在线 embedding，失败则回退纯 BM25）
        combined: defaultdict = defaultdict(float)
        dense = []
        try:
            qv = embed([query])[0]
            dist, ids = self._index.search(qv.reshape(1, -1).astype("float32"), k)
            for d, j in zip(dist[0], ids[0]):
                if j < 0:
                    continue
                dense.append((float(d), int(j)))
        except Exception:
            dense = []

        for sc, j in dense:
            combined[j] += DENSE_WEIGHT * sc
        for doc, ns in sparse_norm.items():
            combined[doc] += SPARSE_WEIGHT * ns

        top = sorted(combined.items(), key=lambda x: -x[1])[:k]

        hits = []
        for rank, (doc_id, score) in enumerate(top, 1):
            d = meta[doc_id] if doc_id < len(meta) else {}
            title = (
                d.get("title")
                or d.get("doc_no")
                or d.get("section")
                or d.get("article_no")
                or ""
            )
            txt = _clean_snippet(d.get("text") or d.get("content") or "")
            hits.append(
                {
                    "rank": rank,
                    "score": round(float(score), 4),
                    "source_id": d.get("source_id", ""),
                    "title": str(title),
                    "snippet": txt[:300],
                }
            )
        return hits

    def stats(self) -> dict:
        """汇总知识库来源分布，供前端展示知识库覆盖范围。"""
        self._load()
        groups: dict = {}
        for d in self._metadata:
            sid = d.get("source_id", "")
            if sid not in groups:
                groups[sid] = {
                    "source_id": sid,
                    "file": d.get("source_file", "") or sid,
                    "doc_no": (d.get("doc_no") or "").strip(),
                    "count": 0,
                }
            g = groups[sid]
            g["count"] += 1
            if not g["doc_no"] and (d.get("doc_no") or "").strip():
                g["doc_no"] = d.get("doc_no", "").strip()
        sources = sorted(groups.values(), key=lambda x: -x["count"])
        return {
            "total_documents": len(self._metadata),
            "total_sources": len(groups),
            "sources": sources,
        }


_retriever: Optional[Retriever] = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(settings.VECTOR_DB_PATH)
    return _retriever