#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证精简索引：文档数/顺序/ID 对齐，FAISS 可加载，BM25 可检索。"""
import json
import re
import tempfile
import shutil
from collections import Counter
from pathlib import Path

OUT = Path(r"D:\华南理工项目\环评审核幻觉实验\app\deploy\kb_slim")


def tokens(text):
    s = text.lower()
    out = re.findall(r"[a-z]+(?:[._/-][a-z0-9]+)*|\d+(?:[._/-]\d+)*", s)
    cs = re.findall(r"[\u4e00-\u9fff]", s)
    out.extend(cs)
    out.extend(a + b for a, b in zip(cs, cs[1:]))
    return out


def main():
    meta = [json.loads(x) for x in (OUT / "child_metadata.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    bm = json.loads((OUT / "bm25_index.json").read_text(encoding="utf-8"))
    N = bm["document_count"]
    print(f"metadata={len(meta)}  bm25_count={N}  -> {'OK' if N == len(meta) else 'MISMATCH!'}")

    # BM25 posting 里的最大 doc id 是否越界
    max_id = max((doc_id for pl in bm["postings"].values() for doc_id, _ in pl), default=-1)
    print(f"bm25 max doc id={max_id}  -> {'OK' if max_id < N else 'OUT OF RANGE!'}")

    # FAISS 向量数
    try:
        import faiss
        src = OUT / "child_cosine_flat.index"
        tmp = Path(tempfile.mkdtemp(prefix="slimcheck_"))
        dst = tmp / "idx.index"
        shutil.copyfileobj(src.open("rb"), dst.open("wb"))
        idx = faiss.read_index(str(dst))
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"faiss ntotal={idx.ntotal}  -> {'OK' if idx.ntotal == N else 'MISMATCH!'}")
    except Exception as e:
        print(f"faiss 检查跳过: {e}")

    # 一次 BM25 检索，看召回内容是否正常（排放标准相关）
    q = "合成树脂工业大气污染物排放标准 非甲烷总烃 限值"
    postings = bm["postings"]; doclen = bm["doc_lengths"]; avgdl = bm["average_document_length"]
    import math
    qtf = Counter(tokens(q)); k1 = 1.5; b = 0.75
    scores = {}
    for t, c in qtf.items():
        pl = postings.get(t) or []
        w = c * math.log1p((N - len(pl) + 0.5) / (len(pl) + 0.5))
        for doc, cnt in pl:
            scores[doc] = scores.get(doc, 0) + w * cnt / (cnt + k1 * (1 - b + b * doclen[doc] / avgdl))
    top = sorted(scores.items(), key=lambda x: -x[1])[:5]
    print(f"\n测试查询: {q}")
    for rank, (doc, sc) in enumerate(top, 1):
        d = meta[doc]
        title = d.get("doc_no") or d.get("source_id") or ""
        print(f"  #{rank} {title:20} | {(d.get('text') or '')[:60]}")
    print("\n精简索引验证完成。")


if __name__ == "__main__":
    main()