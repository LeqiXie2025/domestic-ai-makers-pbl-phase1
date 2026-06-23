import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
CONTENT_ROOT = ROOT.parent
DAY1_BRIEF = CONTENT_ROOT / "day1-model-evaluation" / "outputs" / "day1_to_day2_brief.json"
DAY3_SUMMARY = CONTENT_ROOT / "day3-desktop-agent" / "outputs" / "agent_workspace" / "summaries" / "course_summary.md"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_text(path: Path, limit: int = 5000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:limit]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower())


def product_spec() -> Dict[str, Any]:
    return {
        "product_name": "StudyFlow S3",
        "one_liner": "基于 M5Stack CoreS3 的 AI 学习产品原型，支持复习卡生成、答题评分、资料整理和设备短回复。",
        "target_users": "需要期末突击复习、希望利用碎片时间的大学生。",
        "day2_positioning": "AI Learning Capability Module：把提示词工程、上下文工程、结构化输出、多模态上下文抽取和 AI Coding 封装成可被 Day3 Agent 调用的能力模块。",
        "core_jobs": [
            "从课程资料生成 M5Stack CoreS3 可播报的复习卡。",
            "对学生口述答案进行结构化评分。",
            "把截图、图片、板书或设备界面描述整理成结构化上下文。",
            "把错题和薄弱点整理成 Day3 Agent 可写入的学习状态。",
            "为 Day4 S3/微信入口生成短回复。",
        ],
        "pain_points": [
            "手机复习易分心，难以专注背诵。",
            "错题分散在纸本与手机间，整理耗时。",
            "教师/教练不了解学生真实薄弱点，辅导滞后。",
        ],
        "mvp_features": [
            {
                "name": "Review Card Generator",
                "user_value": "把课程资料转成可抽背的问题、答案、提示和知识标签。",
                "engine_function": "generate_review_cards",
                "output_schema": "schemas/review_card.schema.json",
            },
            {
                "name": "Answer Grader",
                "user_value": "学生回答后给出分数、缺漏点和下一道追问。",
                "engine_function": "grade_answer",
                "output_schema": "schemas/answer_grading.schema.json",
            },
            {
                "name": "Agent Handoff",
                "user_value": "Day3 Agent 能读取 Day2 能力模块的提示词、上下文和输出格式。",
                "engine_function": "build_agent_handoff",
                "output_schema": "schemas/agent_handoff.schema.json",
            },
            {
                "name": "Multimodal Context Extractor",
                "user_value": "把截图、图片、板书或设备界面描述转成 Agent 可使用的上下文。",
                "engine_function": "extract_multimodal_context",
                "output_schema": "schemas/multimodal_observation.schema.json",
            },
        ],
        "model_requirements": {
            "source": "Day1 模型能力评估与路由包",
            "routing_file": "context_pack/day1_model_brief.json",
            "rule": "从硅基流动模型池按任务选择模型；文本任务和多模态任务分开路由，输出失败时切换兜底模型。",
        },
        "hardware_touchpoint": "Day2 定义设备交互内容、结构化输出和多模态上下文格式；真实 S3/ESP-Claw 网关放到 Day4。",
        "success_metrics": [
            "复习卡 JSON 100% 可解析。",
            "答题评分输出包含 score、missing_points、next_prompt。",
            "多模态上下文输出包含 input_type、observations、uncertainties、agent_context。",
            "Day3 Agent 能读取 agent_handoff/day2_agent_contract.json。",
        ],
    }


def prompt_library(day1_brief: Dict[str, Any]) -> Dict[str, Any]:
    router = day1_brief.get("router", {})
    return {
        "generated_at": now(),
        "router_source": "Day1 模型能力评估与路由包",
        "model_policy": "模型来自硅基流动模型池；默认值只是无 Day1 路由时的占位，不限制学生选择。",
        "prompts": [
            {
                "id": "system_pocket_review_coach",
                "type": "system",
                "preferred_model": router.get("risk_checker", {}).get("preferred_model", "student-selected-risk-review-model"),
                "template": "你是 StudyFlow S3 的 AI 学习能力模块。必须输出短、准、可解析的中文 JSON，不编造课程资料。",
                "teaches": "系统提示词：定义角色、边界、输出纪律。",
            },
            {
                "id": "generate_review_cards",
                "type": "task",
                "preferred_model": router.get("schema_generator", {}).get("preferred_model", "student-selected-schema-model"),
                "template": "根据课程上下文生成3张复习卡。字段必须包含 question, answer, hint, tags, source。",
                "teaches": "结构化输出：把大模型结果变成后续程序能消费的数据。",
            },
            {
                "id": "grade_answer",
                "type": "task",
                "preferred_model": router.get("risk_checker", {}).get("preferred_model", "student-selected-risk-review-model"),
                "template": "对学生答案评分，输出 score, verdict, missing_points, next_prompt, confidence。",
                "teaches": "Evaluation：让模型输出可追踪评分而不是泛泛点评。",
            },
            {
                "id": "extract_multimodal_context",
                "type": "task",
                "preferred_model": router.get("multimodal_context", router.get("context_designer", {})).get("preferred_model", "student-selected-multimodal-model"),
                "template": "从截图、图片、板书或设备界面描述中抽取学习上下文，输出 input_type, observations, text_fragments, uncertainties, agent_context。",
                "teaches": "多模态上下文工程：把非文本输入转成 Agent 可使用的结构化上下文。",
            },
            {
                "id": "repair_json",
                "type": "repair",
                "preferred_model": router.get("schema_generator", {}).get("preferred_model", "student-selected-schema-model"),
                "template": "修复不可解析JSON，只输出修复后的JSON，不解释。",
                "teaches": "容错：能力模块必须处理模型格式漂移。",
            },
            {
                "id": "agent_handoff",
                "type": "handoff",
                "preferred_model": router.get("code_assistant", {}).get("preferred_model", "student-selected-code-model"),
                "template": "把产品能力描述成Day3 Agent可调用的动作、输入、输出和文件路径。",
                "teaches": "AI Coding：把提示词资产变成工程接口。",
            },
        ],
    }


def schemas() -> Dict[str, Dict[str, Any]]:
    return {
        "review_card.schema.json": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "answer", "hint", "tags", "source"],
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "hint": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string"},
                },
            },
        },
        "answer_grading.schema.json": {
            "type": "object",
            "required": ["score", "verdict", "missing_points", "next_prompt", "confidence"],
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "verdict": {"type": "string"},
                "missing_points": {"type": "array", "items": {"type": "string"}},
                "next_prompt": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "multimodal_observation.schema.json": {
            "type": "object",
            "required": ["input_type", "observations", "text_fragments", "uncertainties", "agent_context"],
            "properties": {
                "input_type": {"type": "string"},
                "observations": {"type": "array", "items": {"type": "string"}},
                "text_fragments": {"type": "array", "items": {"type": "string"}},
                "uncertainties": {"type": "array", "items": {"type": "string"}},
                "agent_context": {"type": "string"},
            },
        },
        "agent_handoff.schema.json": {
            "type": "object",
            "required": ["engine_name", "actions", "files", "day3_contract"],
            "properties": {
                "engine_name": {"type": "string"},
                "actions": {"type": "array"},
                "files": {"type": "object"},
                "day3_contract": {"type": "object"},
            },
        },
    }


def generate_review_cards(course_context: str) -> List[Dict[str, Any]]:
    terms = [term for term in tokenize(course_context) if len(term) >= 2]
    unique_terms = []
    for term in terms:
        if term not in unique_terms and term not in {"day3", "day4", "agent", "core"}:
            unique_terms.append(term)
    focus = unique_terms[:6] or ["Tool Use", "RAG", "结构化输出"]
    return [
        {
            "question": "为什么 Day2 能力模块必须输出 JSON？",
            "answer": "因为 Day3 Agent 和 Day4 设备入口需要稳定读取复习卡、评分和短回复，JSON 能让模型输出变成可测试、可追踪、可复用的数据。",
            "hint": "结构化输出是工程接口。",
            "tags": ["结构化输出", "Prompt-to-Product", "Agent接口"],
            "source": "Day2 AI Learning Capability Module",
        },
        {
            "question": "Context Engineering 在 StudyFlow S3 里解决什么问题？",
            "answer": "它把课程资料、设备限制、用户场景、Day1模型选型和Day3工作区约束组织成模型可用的上下文，降低幻觉和跑题。",
            "hint": "关键是组织可用上下文。",
            "tags": ["Context Engineering", "幻觉控制", focus[0]],
            "source": "context_pack/course_seed.md",
        },
        {
            "question": "Day2 和 Day3 的接口是什么？",
            "answer": "Day2 交付 prompt_library、schemas、eval_cases 和 agent_handoff/day2_agent_contract.json；Day3 读取这些文件，把产品能力放入工具调用和 RAG 流程。",
            "hint": "Day2 做能力模块，Day3 做 Agent 执行环境。",
            "tags": ["Agent Handoff", "Tool Use", "RAG"],
            "source": "agent_handoff/day2_agent_contract.json",
        },
    ]


def extract_multimodal_context(input_type: str, description: str) -> Dict[str, Any]:
    observations = []
    if "截图" in description or "screen" in description.lower():
        observations.append("输入包含界面或页面结构，需要保留可点击区域、标题和状态信息。")
    if "板书" in description or "白板" in description:
        observations.append("输入包含课堂板书，需要抽取概念、箭头关系和未完成问题。")
    if "S3" in description or "设备" in description:
        observations.append("输入包含设备状态，需要抽取网络、模型、服务地址和错误提示。")
    if not observations:
        observations.append("输入需要先识别可见文本、主体对象和与学习任务相关的证据。")
    fragments = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_:/.-]{2,}", description)[:8]
    return {
        "input_type": input_type,
        "observations": observations,
        "text_fragments": fragments,
        "uncertainties": ["没有真实图像像素时，只能基于文字描述抽取上下文。"],
        "agent_context": "；".join(observations) + " 可交给 Day3 Agent 作为检索与写文件的上下文。",
    }


def grade_answer(answer: str, expected_keywords: List[str]) -> Dict[str, Any]:
    answer_terms = set(tokenize(answer))
    expected = set(expected_keywords)
    hit = sorted(answer_terms & expected)
    score = round((len(hit) / max(1, len(expected))) * 100)
    missing = sorted(expected - answer_terms)
    return {
        "score": score,
        "verdict": "通过" if score >= 70 else "需要补强",
        "missing_points": missing,
        "next_prompt": "请补充说明 Day2 输出如何被 Day3 Agent 读取。" if missing else "请举一个设备端短回复的例子。",
        "confidence": 0.82 if expected else 0.5,
    }


def build_agent_handoff(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "engine_name": "StudyFlowCapabilityModule",
        "product_name": spec["product_name"],
        "actions": [
            {
                "name": "generate_review_cards",
                "input": "course_context: markdown/text",
                "output": "review_card[]",
                "writes": "cards/review_cards.json",
            },
            {
                "name": "grade_answer",
                "input": "question + expected_keywords + student_answer",
                "output": "answer_grading",
                "writes": "evidence/grading_result.json",
            },
            {
                "name": "extract_multimodal_context",
                "input": "input_type + image_or_screenshot_description",
                "output": "multimodal_observation",
                "writes": "knowledge/multimodal_observation.json",
            },
            {
                "name": "prepare_device_reply",
                "input": "intent + latest_agent_state",
                "output": "short_text",
                "writes": "latest_device_reply.txt",
            },
        ],
        "files": {
            "prompt_library": "prompt_library.json",
            "review_card_schema": "schemas/review_card.schema.json",
            "answer_grading_schema": "schemas/answer_grading.schema.json",
            "multimodal_observation_schema": "schemas/multimodal_observation.schema.json",
            "eval_cases": "eval_cases.json",
            "engine_report": "engine_run_report.json",
        },
        "day3_contract": {
            "read_before_run": [
                "outputs/agent_handoff/day2_agent_contract.json",
                "outputs/prompt_library.json",
                "outputs/context_pack/course_seed.md",
                "outputs/eval_cases.json",
            ],
            "use_in_agent": [
                "把Day2的schemas作为写文件格式约束。",
                "把Day2的prompt_library作为LLM任务模板。",
                "把Day2的eval_cases作为Agent输出质量检查。",
                "把多模态上下文抽取结果作为RAG检索和文件整理的补充输入。",
            ],
            "do_not_do_in_day2": [
                "不操作真实桌面文件。",
                "不配置ESP-Claw或微信。",
                "不暴露/v1/chat/completions。",
            ],
        },
    }


def eval_cases(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": "eval_card_schema",
            "input": "课程资料：Prompt Engineering、Context Engineering、结构化输出、AI Coding。",
            "expected": "生成3张review_card，字段完整。",
            "actual": cards,
            "pass": all(set(["question", "answer", "hint", "tags", "source"]).issubset(card) for card in cards),
        },
        {
            "id": "eval_answer_grading_good",
            "input": "学生回答：Day2输出JSON Schema和handoff合约，Day3读取后执行工具调用。",
            "expected_keywords": ["day2", "json", "schema", "handoff", "day3"],
            "actual": grade_answer("Day2 输出 JSON schema 和 handoff 合约，Day3 读取后执行工具调用。", ["day2", "json", "schema", "handoff", "day3"]),
        },
        {
            "id": "eval_answer_grading_weak",
            "input": "学生回答：提示词写好就行。",
            "expected_keywords": ["json", "schema", "handoff", "context"],
            "actual": grade_answer("提示词写好就行。", ["json", "schema", "handoff", "context"]),
        },
        {
            "id": "eval_multimodal_context",
            "input": "截图描述：S3配置页显示Base URL、模型名、超时、WiFi状态；学生希望判断为什么微信消息没有触发本机Agent。",
            "expected": "输出包含input_type、observations、uncertainties、agent_context。",
            "actual": extract_multimodal_context("screenshot_description", "截图描述：S3配置页显示Base URL、模型名、超时、WiFi状态；学生希望判断为什么微信消息没有触发本机Agent。"),
        },
    ]


def render_dashboard(spec: Dict[str, Any], prompt_lib: Dict[str, Any], cards: List[Dict[str, Any]], handoff: Dict[str, Any], cases: List[Dict[str, Any]], day1_brief: Dict[str, Any]) -> str:
    prompt_rows = "".join(
        f"<tr><td>{escape(p['id'])}</td><td>{escape(p['type'])}</td><td>{escape(p['preferred_model'])}</td><td>{escape(p['teaches'])}</td></tr>"
        for p in prompt_lib["prompts"]
    )
    card_html = "".join(
        f"<div class='mini'><b>{escape(card['question'])}</b><p>{escape(card['answer'])}</p><em>{escape(' / '.join(card['tags']))}</em></div>"
        for card in cards
    )
    eval_html = "".join(
        f"<div class='mini'><b>{escape(case['id'])}</b><p>{escape(json.dumps(case.get('actual'), ensure_ascii=False)[:500])}</p></div>"
        for case in cases
    )
    router = day1_brief.get("router", {})
    router_rows = "".join(
        f"<tr><td>{escape(role)}</td><td>{escape(rule.get('preferred_model',''))}</td><td>{escape(str(rule.get('score','')))}</td></tr>"
        for role, rule in router.items()
    )
    action_rows = "".join(
        f"<tr><td>{escape(action['name'])}</td><td>{escape(action['input'])}</td><td>{escape(action['output'])}</td><td>{escape(action['writes'])}</td></tr>"
        for action in handoff["actions"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Day2 AI Learning Capability Module</title>
  <style>
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#f6f7f9;color:#17202a;line-height:1.55}}
    header{{background:#243746;color:white;padding:30px 38px}} header h1{{margin:0 0 8px;font-size:30px}} header p{{margin:0;color:#dbe4ea;max-width:1000px}}
    main{{max-width:1180px;margin:24px auto 48px;padding:0 20px}} .grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
    .panel{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:18px;margin:14px 0}} .kpi{{font-size:28px;font-weight:760}} .muted{{color:#667789}}
    .mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}} .mini p{{margin:8px 0;color:#314252}} .mini em{{color:#667789}}
    table{{width:100%;border-collapse:collapse}} td,th{{border:1px solid #d8dee6;padding:9px;text-align:left;vertical-align:top}} pre{{white-space:pre-wrap;word-break:break-word;background:#f8fafc;padding:10px;border-radius:6px;max-height:320px;overflow:auto}} a{{color:#0f766e;font-weight:650}}
    @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
<header><h1>Day2 AI Learning Capability Module</h1><p>学生把 Prompt Engineering、Context Engineering、结构化输出、多模态上下文抽取和 AI Coding 封装成 Day3 可调用的 AI 学习产品能力模块。</p></header>
<main>
  <div class="grid">
    <div class="panel"><div class="kpi">{len(prompt_lib['prompts'])}</div><div class="muted">提示词资产</div></div>
    <div class="panel"><div class="kpi">{len(handoff['files']) if 'files' in handoff else 4}</div><div class="muted">工程文件索引</div></div>
    <div class="panel"><div class="kpi">{len(cards)}</div><div class="muted">复习卡样例</div></div>
    <div class="panel"><div class="kpi">{len(cases)}</div><div class="muted">评测用例</div></div>
  </div>
  <div class="panel"><h2>Day1 模型路由</h2><table><tr><th>产品任务</th><th>优先模型</th><th>Day1分数</th></tr>{router_rows}</table></div>
  <div class="panel"><h2>Prompt Library</h2><table><tr><th>ID</th><th>类型</th><th>优先模型</th><th>学习点</th></tr>{prompt_rows}</table></div>
  <div class="panel"><h2>Day3 Agent Handoff Actions</h2><table><tr><th>动作</th><th>输入</th><th>输出</th><th>写入</th></tr>{action_rows}</table></div>
  <div class="panel"><h2>复习卡样例</h2>{card_html}</div>
  <div class="panel"><h2>Eval Cases</h2>{eval_html}</div>
  <div class="panel"><h2>文件证据</h2><p><a href="prompt_library.json">prompt_library.json</a> / <a href="context_pack/day1_model_brief.json">day1_model_brief.json</a> / <a href="schemas/review_card.schema.json">schemas</a> / <a href="eval_cases.json">eval_cases.json</a> / <a href="agent_handoff/day2_agent_contract.json">day2_agent_contract.json</a> / <a href="engine_run_report.json">engine_run_report.json</a></p></div>
  <div class="panel"><h2>产品规格</h2><pre>{escape(json.dumps(spec, ensure_ascii=False, indent=2)[:3000])}</pre></div>
</main>
</body>
</html>"""


def run_engine() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    day1_brief = read_json(DAY1_BRIEF, {"router": {}, "purpose": "Day1 brief not generated yet."})
    spec = product_spec()
    prompt_lib = prompt_library(day1_brief)
    schema_map = schemas()
    day3_context = read_text(DAY3_SUMMARY, 3200)
    course_seed = f"""# Day2 Course Seed

## Product
{spec['product_name']}：{spec['one_liner']}

## Day2 Learning Focus
- Prompt Engineering
- Context Engineering
- Structured Output
- AI Coding
- Evaluation

## Day3 Context Preview
{day3_context or 'Day3 Agent Core 尚未运行；Day2 仍可先用本课程种子资料生成能力模块。'}
"""
    cards = generate_review_cards(course_seed)
    cases = eval_cases(cards)
    handoff = build_agent_handoff(spec)
    report = {
        "generated_at": now(),
        "engine_name": "StudyFlowCapabilityModule",
        "product": spec["product_name"],
        "day1_brief_loaded": DAY1_BRIEF.exists(),
        "day3_summary_loaded": DAY3_SUMMARY.exists(),
        "prompt_count": len(prompt_lib["prompts"]),
        "schema_count": len(schema_map),
        "eval_count": len(cases),
        "cards": cards,
        "handoff_contract": handoff,
        "assessment": [
            "是否把提示词变成可复用产品能力。",
            "是否提供JSON Schema和Eval Cases。",
            "是否能被Day3 Agent读取并用于工具/RAG流程。",
        ],
    }

    write_json(OUT / "product_spec.json", spec)
    write_json(OUT / "prompt_library.json", prompt_lib)
    write_json(OUT / "context_pack" / "day1_model_brief.json", day1_brief)
    write_text(OUT / "context_pack" / "course_seed.md", course_seed)
    write_text(
        OUT / "context_pack" / "device_constraints.md",
        "# Device Constraints\n\n- 屏幕小：回复不超过120字。\n- 输入可能来自语音或微信：需要二次确认。\n- 网络不稳定：输出必须可缓存。\n- 端侧只做触发和展示，复杂推理走本机/云端服务。\n- 多模态输入如果来自截图或板书，需要先转成结构化上下文，再交给 Agent 使用。\n",
    )
    write_json(
        OUT / "context_pack" / "user_scenarios.json",
        [
            {"scenario": "期末路上抽背", "input": "给我一道复习题", "output": "短题目+提示"},
            {"scenario": "整理今天资料", "input": "请整理今天资料", "output": "确认后调用Day3 Agent"},
            {"scenario": "错题复盘", "input": "我刚才答错了", "output": "记录错题并生成下一问"},
        ],
    )
    for name, schema in schema_map.items():
        write_json(OUT / "schemas" / name, schema)
    write_json(OUT / "eval_cases.json", cases)
    write_json(OUT / "agent_handoff" / "day2_agent_contract.json", handoff)
    write_text(
        OUT / "agent_handoff" / "day2_to_day3_brief.md",
        "# Day2 to Day3 Brief\n\nDay2 已经把 StudyFlow S3 的提示词、上下文、结构化输出、多模态上下文抽取和评测样例封装成能力模块。Day3 的桌面 Agent Core 应读取 `agent_handoff/day2_agent_contract.json`，把这些能力放入本地工具调用、RAG 检索和文件写入流程。\n",
    )
    write_json(OUT / "engine_run_report.json", report)
    html = render_dashboard(spec, prompt_lib, cards, handoff, cases, day1_brief)
    write_text(OUT / "Day2_产品控制台.html", html)
    write_text(OUT / "Day2_产品Demo.html", html)
    write_text(
        OUT / "engineering_critique.md",
        "# Day2 工程评审\n\n- 核心产物是 `StudyFlowCapabilityModule`。\n- Prompt Library、Context Pack、Schemas、Eval Cases、Agent Handoff Contract 构成可被 Day3 调用的能力模块。\n- 多模态上下文需要先结构化，再进入 Agent 的检索和文件操作流程。\n- 最大风险仍是模型输出格式漂移，因此必须保留 `repair_json` 提示词和 schema 检查。\n- Day2 不配置硬件、不操作真实桌面文件；这些分别放到 Day4 和 Day3。\n",
    )
    write_text(OUT / "demo_run_before_day3.txt", "Day2 Engine 已可独立生成复习卡、评分样例和 Day3 handoff 合约。\n")
    write_text(OUT / "demo_run_after_day3.txt", f"Day2 Engine 已读取 Day3 摘要：{bool(day3_context)}\n")
    return report


def main() -> None:
    report = run_engine()
    print(json.dumps({"ok": True, "prompt_count": report["prompt_count"], "eval_count": report["eval_count"], "day1_loaded": report["day1_brief_loaded"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
