#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简检索索引：只保留 runtime 需要的 3 个文件 + 剔除 metadata 冗余字段。

原则：
- 文档数、顺序、ID 完全不变 -> FAISS 向量与 BM25 posting 里的 doc id 依旧对齐。
- 只删除 serve 期用不到的字段（parent_text / embedding_text / 各种 hash / token 统计），
  保留检索展示所需的 source_id / doc_no / section / article_no / unit_type / text 等。
"""
import json
from pathlib import Path

IDX = Path(r"D:\华南理工项目\环评审核幻觉实验\03_知识库\05_检索索引_六文件")
OUT = Path(r"D:\华南理工项目\环评审核幻觉实验\app\deploy\kb_slim")

KEEP = [
    "source_id", "source_file", "doc_no", "section", "article_no", "clause_no",
    "unit_type", "title", "text", "content", "evidence_tier", "jurisdiction",
    "effective_from", "effective_to", "status",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) 精简 metadata
    src = IDX / "child_metadata.jsonl"
    slim = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        keep = {k: d.get(k) for k in KEEP if k in d}
        # text/content 归一：优先 text，其次 content
        keep["text"] = d.get("text") or d.get("content") or ""
        keep.pop("content", None)
        slim.append(keep)

    meta_out = OUT / "child_metadata.jsonl"
    with meta_out.open("w", encoding="utf-8") as f:
        for d in slim:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 2) 复制 BM25 与 FAISS（doc id / 顺序未变，原样可用）
    for name in ("bm25_index.json", "child_cosine_flat.index"):
        (OUT / name).write_bytes((IDX / name).read_bytes())

    # 3) 校验 BM25 文档数一致
    bm = json.loads((OUT / "bm25_index.json").read_text(encoding="utf-8"))
    assert bm["document_count"] == len(slim), (
        f"文档数不一致: bm25={bm['document_count']} metadata={len(slim)}"
    )

    raw = src.stat().st_size
    new = meta_out.stat().st_size
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"文档数: {len(slim)}")
    print(f"metadata: {raw/1024/1024:.2f}MB -> {new/1024/1024:.2f}MB "
          f"(-{(1-new/raw)*100:.0f}%)")
    print(f"精简索引 3 文件合计: {total/1024/1024:.2f}MB")


if __name__ == "__main__":
    main()