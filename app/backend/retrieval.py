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
            txt = (d.get("text") or d.get("content") or "").replace("\n", " ")
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