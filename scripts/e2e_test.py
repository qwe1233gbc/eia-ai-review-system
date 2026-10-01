"""端到端冒烟测试：健康检查 / 首页 / 主题 / 真实上传审核。"""
import json

import requests

BASE = "http://127.0.0.1:8000"


def show(name, fn):
    try:
        r = fn()
        print(f"\n== {name} ==")
        if isinstance(r, requests.Response):
            print("  HTTP", r.status_code)
            if "application/json" in r.headers.get("content-type", ""):
                d = r.json()
                if name.startswith("upload"):
                    print("  topic:", d.get("topic"), "| mode:", d.get("mode"), "| risk:", d.get("risk_level"))
                    print("  summary:", d.get("summary", "")[:120])
                    print("  issues:", len(d.get("issues", [])), "| sources:", len(d.get("retrieved_sources", [])))
                    for it in d.get("issues", [])[:2]:
                        print("   -", it.get("id"), it.get("category"), it.get("severity"), it.get("description", "")[:50])
                else:
                    print(" ", json.dumps(d, ensure_ascii=False)[:400])
            else:
                print(" ", r.text[:80].replace("\n", " "))
        else:
            print(" ", r)
    except Exception as e:
        print(f"  ERROR: {e}")


if __name__ == "__main__":
    show("health", lambda: requests.get(f"{BASE}/api/health", timeout=10))
    show("homepage", lambda: requests.get(f"{BASE}/", timeout=10))
    show("topics", lambda: requests.get(f"{BASE}/api/topics", timeout=10))

    sample = (
        "三、区域环境质量现状、环境保护目标及评价标准\n"
        "本项目废气执行《大气污染物综合排放标准》(GB 16297-1996)，非甲烷总烃有组织排放限值120mg/m³。"
    )
    show("upload_live", lambda: requests.post(
        f"{BASE}/api/audit/upload",
        files={"file": ("PL_sample.md", sample.encode("utf-8"), "text/markdown")},
        data={"topic": "emission_standards"},
        timeout=300,
    ))