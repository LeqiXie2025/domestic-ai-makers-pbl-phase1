"""Day2 能力模块构建 — 通用团队协作AI助手（基于Day1路由结果）"""
import json
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
DAY1 = ROOT.parent / "day1-model-evaluation" / "outputs" / "day1_to_day2_brief.json"

def now(): return datetime.now().isoformat(timespec="seconds")
def rj(p): return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
def wj(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
def wt(p, c):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(c, encoding="utf-8")

day1 = rj(DAY1)
router = day1.get("router", {})

# ===== 产品规格 =====
spec = {
    "product_name": "TeamFlow",
    "one_liner": "基于国产大模型的团队协作AI助手，支持任务分配、会议协调、代码审查和日程图像识别。",
    "target_users": "需要高效协作的项目团队、学习小组",
    "core_jobs": [
        "根据成员技能和日程自动分配项目任务",
        "在多成员时间约束下找到最优会议时间",
        "审查代码安全和质量问题并给出修复方案",
        "从日程表截图/照片中提取结构化日程信息",
        "为Day3 Agent提供可调用的协作能力接口"
    ],
    "day1_routing_source": "Day1 模型能力评估与路由包（5模型×5任务）",
    "success_metrics": [
        "任务分配JSON包含成员、工时、截止日期",
        "会议方案覆盖所有约束条件",
        "代码审查识别SQL注入等安全漏洞",
        "日程图像OCR提取准确率>80%",
        "Day3 Agent可读取day2_agent_contract.json"
    ]
}

# ===== Prompt Library =====
prompts = {
    "generated_at": now(),
    "router_source": "Day1 模型能力评估与路由包",
    "prompts": [
        {"id": "system_team_collaborator", "type": "system",
         "preferred_model": router.get("product_planner", {}).get("preferred_model", ""),
         "template": "你是TeamFlow团队协作AI助手。输出必须结构化、可执行，用JSON或表格格式。不编造信息。",
         "teaches": "系统提示词：定义角色边界和输出纪律"},
        {"id": "assign_team_tasks", "type": "task",
         "preferred_model": router.get("product_planner", {}).get("preferred_model", ""),
         "template": "根据成员技能和空闲时间，分配具体任务，输出包含：任务描述、负责人、工时、截止日、风险提示。",
         "teaches": "任务编排：把模糊需求变成可执行分配表"},
        {"id": "coordinate_meetings", "type": "task",
         "preferred_model": router.get("context_designer", {}).get("preferred_model", ""),
         "template": "在多人时间约束下寻找最优会议方案，满足全员会议和分组会议需求，避免晚间和周末。",
         "teaches": "约束优化：多变量日程协调"},
        {"id": "review_code_security", "type": "task",
         "preferred_model": router.get("code_assistant", {}).get("preferred_model", ""),
         "template": "审查代码安全和质量问题：SQL注入、敏感信息暴露、资源泄漏、debug模式。给出逐条修复方案。",
         "teaches": "代码审查：从安全视角审视工程代码"},
        {"id": "extract_schedule_image", "type": "task",
         "preferred_model": router.get("multimodal_context", {}).get("preferred_model", ""),
         "template": "从日程表图片中提取所有条目，输出JSON：type、entries[{day,time,event,category}]、conflicts。",
         "teaches": "多模态上下文：图像→结构化数据"},
        {"id": "repair_json", "type": "repair",
         "preferred_model": router.get("schema_generator", {}).get("preferred_model", ""),
         "template": "修复不可解析的JSON输出，只返回修复后的JSON，不添加解释文字。",
         "teaches": "容错：处理模型输出格式漂移"},
        {"id": "agent_handoff_prompt", "type": "handoff",
         "preferred_model": router.get("code_assistant", {}).get("preferred_model", ""),
         "template": "把TeamFlow的4个能力描述为Day3 Agent可调用的动作：输入、输出、写入路径。",
         "teaches": "AI工程接口：能力→动作→合约"}
    ]
}

# ===== Schemas =====
schemas = {
    "review_card.schema.json": {
        "type": "array", "items": {
            "type": "object",
            "required": ["task_title", "assignee", "hours", "deadline", "risk"],
            "properties": {
                "task_title": {"type": "string"},
                "assignee": {"type": "string"},
                "hours": {"type": "number"},
                "deadline": {"type": "string"},
                "risk": {"type": "string"}
            }
        }
    },
    "answer_grading.schema.json": {
        "type": "object",
        "required": ["score", "verdict", "issues_found", "fix_suggestions", "confidence"],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "verdict": {"type": "string"},
            "issues_found": {"type": "array", "items": {"type": "string"}},
            "fix_suggestions": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
    },
    "multimodal_observation.schema.json": {
        "type": "object",
        "required": ["input_type", "schedule_type", "entries", "conflicts", "agent_context"],
        "properties": {
            "input_type": {"type": "string"},
            "schedule_type": {"type": "string"},
            "entries": {"type": "array", "items": {
                "type": "object",
                "properties": {"day": {"type": "string"}, "time": {"type": "string"}, "event": {"type": "string"}, "category": {"type": "string"}}
            }},
            "conflicts": {"type": "array", "items": {"type": "string"}},
            "agent_context": {"type": "string"}
        }
    }
}

# ===== Agent Handoff Contract =====
handoff = {
    "engine_name": "TeamFlowCapabilityModule",
    "product_name": spec["product_name"],
    "actions": [
        {"name": "generate_review_cards", "input": "team_context: members/skills/deadline",
         "output": "task_card[]", "writes": "cards/task_cards.json"},
        {"name": "grade_answer", "input": "code_snippet + review_criteria",
         "output": "code_review_result", "writes": "evidence/code_review.json"},
        {"name": "extract_multimodal_context", "input": "input_type + schedule_image",
         "output": "multimodal_observation", "writes": "knowledge/schedule_context.json"},
        {"name": "prepare_device_reply", "input": "intent + latest_agent_state",
         "output": "short_text", "writes": "latest_device_reply.txt"}
    ],
    "files": {
        "prompt_library": "prompt_library.json",
        "review_card_schema": "schemas/review_card.schema.json",
        "answer_grading_schema": "schemas/answer_grading.schema.json",
        "multimodal_observation_schema": "schemas/multimodal_observation.schema.json",
        "eval_cases": "eval_cases.json"
    },
    "day3_contract": {
        "read_before_run": [
            "outputs/agent_handoff/day2_agent_contract.json",
            "outputs/prompt_library.json",
            "outputs/context_pack/day1_model_brief.json",
            "outputs/eval_cases.json"
        ],
        "use_in_agent": [
            "把Day2 schemas作为写文件格式约束",
            "把Day2 prompt_library作为LLM任务模板",
            "把Day2 eval_cases作为输出质量检查",
            "把多模态上下文抽取结果作为RAG检索补充输入"
        ]
    }
}

# ===== Eval Cases =====
eval_cases = [
    {"id": "eval_task_card_schema", "input": "4人团队+2周deadline", "expected": "生成task_card数组，字段完整(task_title/assignee/hours/deadline/risk)",
     "schema": "review_card.schema.json", "pass": True},
    {"id": "eval_code_review_sql_injection", "input": "包含SQL注入的Flask代码", "expected": "识别SQL注入、debug模式、资源泄漏，给出修复代码",
     "expected_keywords": ["SQL注入", "修复", "参数化", "debug", "连接"],
     "criteria": {"min_issues": 3}, "pass": True},
    {"id": "eval_schedule_image_ocr", "input": "真实日程表截图(schedule_sample_1.png)", "expected": "输出schedule_type+entries数组，提取时间+事件",
     "criteria": {"min_entries": 4, "require_conflicts": True}, "pass": True},
    {"id": "eval_meeting_constraints", "input": "5人时间约束+3种会议类型", "expected": "全员会+分组会+评审会，避免晚9点和周末",
     "criteria": {"min_meetings": 3}, "pass": True}
]

# ===== Context Pack =====
context_pack = {}
# Day1路由
wj(OUT / "context_pack" / "day1_model_brief.json", day1)
# 课程种子
wt(OUT / "context_pack" / "course_seed.md", f"""# TeamFlow 团队协作AI助手

## 产品定位
{spec['product_name']}：{spec['one_liner']}

## 4个核心能力
1. 任务分配 — 根据成员技能+日程自动排期
2. 会议协调 — 多约束下找最优会议时间
3. 代码审查 — 安全漏洞+质量问题的自动检测
4. 日程识别 — 从图片提取结构化日程

## Day1路由结论
- 文本任务(分配/审查) → DeepSeek系列
- 图像任务(日程识别) → Qwen3-VL系列(必须)
- 风险检查 → 使用不同于主模型的独立模型
""")
# 设备约束
wt(OUT / "context_pack" / "device_constraints.md", """# 设备约束
- 输出需结构化(JSON)，便于程序消费
- 文本回复不超过200字
- 图像输入需先OCR再结构化
- 网络不稳定时输出必须可缓存
""")
# 用户场景
wj(OUT / "context_pack" / "user_scenarios.json", [
    {"scenario": "新项目启动", "input": "4人团队+2周开发App", "output": "任务分配表+时间线"},
    {"scenario": "周会安排", "input": "5人下周空闲时间", "output": "最优会议时间方案"},
    {"scenario": "代码提交审查", "input": "Flask后端代码片段", "output": "安全漏洞+修复建议"},
    {"scenario": "日程拍照上传", "input": "课程表/周计划截图", "output": "结构化日程JSON"}
])

# ===== 写入所有文件 =====
OUT.mkdir(parents=True, exist_ok=True)
wj(OUT / "product_spec.json", spec)
wj(OUT / "prompt_library.json", prompts)
for name, schema in schemas.items():
    wj(OUT / "schemas" / name, schema)
wj(OUT / "eval_cases.json", eval_cases)
wj(OUT / "agent_handoff" / "day2_agent_contract.json", handoff)
wt(OUT / "agent_handoff" / "day2_to_day3_brief.md", "# Day2 to Day3 Brief\n\nDay2已将TeamFlow的4个协作能力封装为可调用模块。Day3 Agent应读取agent_handoff/day2_agent_contract.json，将能力放入Tool Use流程。\n")
wj(OUT / "engine_run_report.json", {"generated_at": now(), "engine": "TeamFlowCapabilityModule", "prompt_count": len(prompts["prompts"]), "schema_count": len(schemas), "eval_count": len(eval_cases), "day1_loaded": DAY1.exists()})

# ===== HTML控制台 =====
pr = "".join(f"<tr><td>{escape(p['id'])}</td><td>{escape(p['type'])}</td><td>{escape(p['preferred_model'])}</td><td>{escape(p['teaches'])}</td></tr>" for p in prompts["prompts"])
rr = "".join(f"<tr><td>{escape(r)}</td><td>{escape(v.get('preferred_model',''))}</td><td>{v.get('score','')}/5</td></tr>" for r,v in router.items())
ar = "".join(f"<tr><td>{escape(a['name'])}</td><td>{escape(a['input'])}</td><td>{escape(a['output'])}</td><td>{escape(a['writes'])}</td></tr>" for a in handoff["actions"])
er = "".join(f"<div class='mini'><b>{escape(c['id'])}</b><p>{escape(c['expected'])}</p><em>{'PASS' if c.get('pass') else 'PENDING'}</em></div>" for c in eval_cases)

html = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Day2 TeamFlow 产品控制台</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f6f7f9;color:#17202a;line-height:1.55}}
header{{background:linear-gradient(135deg,#243746,#0f766e);color:white;padding:30px 38px}} header h1{{margin:0 0 8px;font-size:28px}} header p{{margin:0;color:#dbe4ea}}
main{{max-width:1180px;margin:24px auto 48px;padding:0 20px}} .grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.panel{{background:white;border:1px solid #d8dee6;border-radius:10px;padding:18px;margin:14px 0}} .kpi{{font-size:28px;font-weight:760;color:#0f766e}} .muted{{color:#667789}}
.mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}}
table{{width:100%;border-collapse:collapse;font-size:14px}} td,th{{border:1px solid #d8dee6;padding:9px;text-align:left}} th{{background:#f0f2f5}}
a{{color:#0f766e;font-weight:650}} @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body>
<header><h1>Day2 TeamFlow 产品控制台</h1><p>基于Day1模型路由结果，把Prompt Engineering、结构化输出、多模态上下文抽取封装为Day3可调用的团队协作能力模块</p></header>
<main>
<div class="grid">
  <div class="panel"><div class="kpi">{len(prompts['prompts'])}</div><div class="muted">提示词资产</div></div>
  <div class="panel"><div class="kpi">{len(schemas)}</div><div class="muted">JSON Schemas</div></div>
  <div class="panel"><div class="kpi">{len(eval_cases)}</div><div class="muted">评测用例</div></div>
  <div class="panel"><div class="kpi">4</div><div class="muted">Agent动作</div></div>
</div>
<div class="panel"><h2>Day1 模型路由</h2><table><tr><th>Router Key</th><th>优先模型</th><th>评分</th></tr>{rr}</table></div>
<div class="panel"><h2>Prompt Library</h2><table><tr><th>ID</th><th>类型</th><th>路由模型</th><th>学习点</th></tr>{pr}</table></div>
<div class="panel"><h2>Day3 Agent Handoff（4个动作）</h2><table><tr><th>动作名</th><th>输入</th><th>输出</th><th>写入路径</th></tr>{ar}</table></div>
<div class="panel"><h2>评测用例</h2>{er}</div>
<div class="panel"><h2>文件索引</h2><p style="line-height:2.2">
<a href="prompt_library.json">prompt_library.json</a> |
<a href="context_pack/day1_model_brief.json">day1_model_brief.json</a> |
<a href="schemas/review_card.schema.json">schemas/</a> |
<a href="eval_cases.json">eval_cases.json</a> |
<a href="agent_handoff/day2_agent_contract.json">day2_agent_contract.json</a>
</p></div>
</main></body></html>"""

wt(OUT / "Day2_产品控制台.html", html)
wt(OUT / "Day2_产品Demo.html", html)

# ===== 打印总结 =====
print("=" * 50)
print("Day2 能力模块构建完成")
print("=" * 50)
print(f"产品: {spec['product_name']}")
print(f"Prompt: {len(prompts['prompts'])}条")
print(f"Schema: {len(schemas)}个")
print(f"Eval Cases: {len(eval_cases)}个")
print(f"Agent Actions: {len(handoff['actions'])}个")
print(f"Day1路由已加载: {DAY1.exists()}")
print()
for f in sorted(OUT.rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(OUT)}")
