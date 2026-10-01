"""Mock 模式示例结果：用于无 API Key 时验证前后端全链路。"""

MOCK_RESULT = {
    "topic": "emission_standards",
    "mode": "mock",
    "model": "",
    "summary": (
        "（Mock 示例）报告废气排放执行标准存在标准编号引用错误与非甲烷总烃排放限值引用不准确，"
        "建议依《合成树脂工业污染物排放标准》(GB 31572-2015) 及广东省地方标准复核后更正。"
    ),
    "risk_level": "高",
    "issues": [
        {
            "id": "ISSUE-1",
            "category": "标准编号",
            "severity": "高",
            "description": "报告将挤出/注塑工序废气排放执行的行业标准编号写错。",
            "reported": "GB 16297-1996《大气污染物综合排放标准》",
            "correct_basis": {
                "standard_name": "合成树脂工业污染物排放标准",
                "standard_no": "GB 31572-2015",
                "clause": "表 5 大气污染物特别排放限值",
                "pollutant": "非甲烷总烃",
                "limit": "60",
                "unit": "mg/m³",
                "control_location": "有组织排放口",
                "reference": "GB 31572-2015（塑胶/合成树脂行业应优先执行行业标准）",
            },
            "suggestion": "将行业标准更正为 GB 31572-2015，并同步核对排放限值。",
        },
        {
            "id": "ISSUE-2",
            "category": "限值",
            "severity": "中",
            "description": "非甲烷总烃有组织排放限值引用与现行行业标准不一致。",
            "reported": "120 mg/m³",
            "correct_basis": {
                "standard_name": "合成树脂工业污染物排放标准",
                "standard_no": "GB 31572-2015",
                "clause": "表 5",
                "pollutant": "非甲烷总烃",
                "limit": "60",
                "unit": "mg/m³",
                "control_location": "有组织排放口",
                "reference": "GB 31572-2015 特别排放限值",
            },
            "suggestion": "非甲烷总烃排放限值按 60 mg/m³ 复核（以项目环评批复及所在地执行档位为准）。",
        },
        {
            "id": "ISSUE-3",
            "category": "其他",
            "severity": "低",
            "description": "未写明标准执行档位（特别排放限值 / 一般限值）及控制位置。",
            "reported": "",
            "correct_basis": {
                "standard_name": "",
                "standard_no": "",
                "clause": "",
                "pollutant": "",
                "limit": "",
                "unit": "",
                "control_location": "有组织排放口、厂界无组织监控点",
                "reference": "",
            },
            "suggestion": "补充说明执行档位与各污染物对应的控制位置（排气筒 / 厂界）。",
        },
    ],
    "retrieved_sources": [
        {
            "rank": 1,
            "score": 0.911,
            "source_id": "SRC_GB31572_2015",
            "title": "GB 31572-2015",
            "snippet": "合成树脂工业污染物排放标准 表5 非甲烷总烃 60 mg/m³",
        },
        {
            "rank": 2,
            "score": 0.874,
            "source_id": "SRC_DB44_2367_2022",
            "title": "DB44/2367-2022",
            "snippet": "固定污染源挥发性有机物综合排放标准",
        },
    ],
}