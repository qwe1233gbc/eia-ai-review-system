#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读探查 05_检索索引_六文件：source 分布 + 排放标准相关候选 source。"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

IDX = Path(r"D:\华南理工项目\环评审核幻觉实验\03_知识库\05_检索索引_六文件")

# 排放标准相关关键词（用于把 source 归到"排放标准"类）
EMISSION_KW = [
    "排放", "限值", "污染物排放标准", "GB 31572", "GB31572", "DB44", "DB44/2367",
    "大气污染物", "水污染物", "恶臭", "臭气", "合成树脂", "塑料", "塑胶",
    "挥发性有机物", "VOCs", "非甲烷总烃", "颗粒物", "废气", "废水", "噪声",
    "固体废物", "危险废物", "表", "污染物排放控制标准", "执行标准",
]


def main():
    meta = [json.loads(x) for x in (IDX / "child_metadata.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    print(f"总文档数: {len(meta)}")
    print("字段:", sorted(meta[0].keys()))
    print("样例:", json.dumps(meta[0], ensure_ascii=False)[:500])

    src_counter = Counter(d.get("source_id", "?") for d in meta)
    print(f"\nsource 数: {len(src_counter)}")
    # 每个 source 的名字 + 文档数，查找是否排放相关
    src_sample = {}
    for d in meta:
        sid = d.get("source_id", "?")
        src_sample.setdefault(sid, d)

    emit_srcs = set()
    lines = []
    for sid, cnt in src_counter.most_common():
        d = src_sample[sid]
        title = (d.get("title") or d.get("doc_no") or d.get("source_id") or "")
        # 用该 source 下若干文档的文本判断主题
        texts = [x.get("text") or x.get("content") or "" for x in meta if x.get("source_id") == sid][:5]
        blob = (title + " " + " ".join(texts))
        is_emit = any(kw in blob for kw in EMISSION_KW)
        if is_emit:
            emit_srcs.add(sid)
        lines.append((sid, cnt, "★排放" if is_emit else "", title[:60]))

    print(f"\n排放标准相关 source 数: {len(emit_srcs)}")
    emit_docs = sum(c for s, c in src_counter.items() if s in emit_srcs)
    print(f"排放标准相关文档数: {emit_docs} / {len(meta)}")

    for sid, cnt, tag, title in lines:
        print(f"{tag:4} {cnt:5}  {sid:30}  {title}")


if __name__ == "__main__":
    main()