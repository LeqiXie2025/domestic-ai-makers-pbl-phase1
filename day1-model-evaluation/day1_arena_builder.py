
def generate_mock_results() -> list:
    """Generate mock evaluation results when no real results exist."""
    TASKS = [
        {"id": "creative_001", "title": "产品创意生成", "type": "text", "prompt": "为StudyFlow S3设计一个新的学习场景"},
        {"id": "structured_001", "title": "结构化输出", "type": "text", "prompt": "输出JSON Schema描述一个复习卡"},
        {"id": "coding_001", "title": "代码生成", "type": "text", "prompt": "写一个Python函数解析用户输入"},
        {"id": "hallucination_001", "title": "事实诚实性", "type": "text", "prompt": "回答一个你不确定的事实问题"},
        {"id": "multimodal_001", "title": "多模态理解", "type": "multimodal", "prompt": "描述一张课程大纲截图"},
    ]
    MODELS = [
        {"id": "Pro/moonshotai/Kimi-K2.6", "label": "Kimi (Moonshot)"},
        {"id": "deepseek-ai/DeepSeek-V4-Flash", "label": "DeepSeek"},
        {"id": "Qwen/Qwen3.6-27B", "label": "Qwen (Alibaba)"},
    ]
    results = []
    for task in TASKS:
        for model in MODELS:
            score = 5 if model["label"] == "Kimi (Moonshot)" else (4 if model["label"] == "DeepSeek" else 3)
            if task["id"] == "hallucination_001":
                score = 4 if model["label"] == "Kimi (Moonshot)" else (3 if model["label"] == "DeepSeek" else 3)
            results.append({
                "task": task,
                "model": model,
                "score": score,
                "ok": True,
                "output": {
                    "text": f"这是{model['label']}对'{task['title']}'任务的输出示例。",
                    "latency": 1.2 + hash(model["id"]) % 30 * 0.1,
                    "usage": {"total_tokens": 150 + hash(model["id"]) % 500}
                }
            })
    return results

import json
import statistics
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
RESULTS = OUT / "day1_results.json"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def short(text: str, limit: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def load_results() -> List[Dict[str, Any]]:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def task_key(item: Dict[str, Any]) -> str:
    task = item.get("task", {})
    return task.get("id") or task.get("title") or "unknown"


def model_label(item: Dict[str, Any]) -> str:
    model = item.get("model", {})
    return model.get("label") or model.get("id") or "unknown"


def task_title(item: Dict[str, Any]) -> str:
    task = item.get("task", {})
    return task.get("title") or task_key(item)


def output_text(item: Dict[str, Any]) -> str:
    output = item.get("output") or {}
    if isinstance(output, dict):
        return str(output.get("text") or output.get("content") or "")
    return str(output or "")


def latency(item: Dict[str, Any]) -> float:
    output = item.get("output") or {}
    if isinstance(output, dict):
        try:
            return float(output.get("latency") or 0)
        except Exception:
            return 0.0
    return 0.0


def usage_total(item: Dict[str, Any]) -> int:
    output = item.get("output") or {}
    usage = output.get("usage") if isinstance(output, dict) else {}
    try:
        return int((usage or {}).get("total_tokens") or 0)
    except Exception:
        return 0


def score_item(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("score") or 0)
    except Exception:
        return 0


def build_matrix(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    tasks: Dict[str, Dict[str, Any]] = {}
    models: Dict[str, Dict[str, Any]] = {}
    for item in results:
        tkey = task_key(item)
        tasks.setdefault(
            tkey,
            {
                "id": tkey,
                "title": task_title(item),
                "type": item.get("task", {}).get("type", "unknown"),
                "prompt": item.get("task", {}).get("prompt", ""),
                "checks": item.get("task", {}).get("checks", []),
            },
        )
        label = model_label(item)
        models.setdefault(label, {"label": label, "id": item.get("model", {}).get("id", label), "items": []})
        models[label]["items"].append(item)

    matrix = []
    for label, model in sorted(models.items()):
        items = model["items"]
        scores = [score_item(item) for item in items]
        latencies = [latency(item) for item in items if latency(item) > 0]
        tokens = [usage_total(item) for item in items if usage_total(item) > 0]
        task_scores = {task_key(item): score_item(item) for item in items}
        strengths = [task_title(item) for item in items if score_item(item) >= 4]
        risks = [task_title(item) for item in items if score_item(item) <= 2 or not item.get("ok")]
        matrix.append(
            {
                "model_label": label,
                "model_id": model["id"],
                "avg_score": round(statistics.mean(scores), 2) if scores else 0,
                "avg_latency_seconds": round(statistics.mean(latencies), 2) if latencies else 0,
                "avg_total_tokens": round(statistics.mean(tokens), 1) if tokens else 0,
                "task_scores": task_scores,
                "strengths": strengths,
                "risks": risks,
                "recommendation": recommend_model_role(label, task_scores),
            }
        )

    leaderboards = {}
    for tkey, task in tasks.items():
        candidates = [
            {
                "model": model_label(item),
                "score": score_item(item),
                "latency": latency(item),
                "sample": short(output_text(item), 260),
            }
            for item in results
            if task_key(item) == tkey
        ]
        candidates.sort(key=lambda row: (-row["score"], row["latency"]))
        leaderboards[tkey] = {"task": task, "ranking": candidates}

    return {
        "generated_at": now(),
        "arena_name": "Day1 国产大模型能力评估与路由",
        "models": [{"label": row["model_label"], "id": row["model_id"]} for row in matrix],
        "tasks": list(tasks.values()),
        "matrix": matrix,
        "leaderboards": leaderboards,
        "assessment_focus": [
            "同一任务多模型对比，形成可复用的工程证据。",
            "保留原始输出、评分、失败样本和选型理由。",
            "把模型能力差异转化为 Day2 能力模块的模型路由规则。",
            "文本模型和多模态模型分开评估，避免用单一总分覆盖任务差异。",
        ],
    }


def recommend_model_role(label: str, task_scores: Dict[str, int]) -> List[str]:
    roles = []
    if task_scores.get("creative_001", 0) >= 4:
        roles.append("产品创意与场景扩展")
    if task_scores.get("structured_001", 0) >= 4:
        roles.append("结构化输出与schema生成")
    if task_scores.get("coding_001", 0) >= 4:
        roles.append("AI Coding辅助")
    if task_scores.get("hallucination_001", 0) >= 3:
        roles.append("事实诚实性与风险复核")
    if task_scores.get("multimodal_001", 0) >= 4:
        roles.append("多模态应用设计")
    return roles or ["低风险辅助生成"]


def build_day2_brief(matrix: Dict[str, Any]) -> Dict[str, Any]:
    role_map = {
        "product_planner": "creative_001",
        "context_designer": "multimodal_001",
        "multimodal_context": "multimodal_001",
        "schema_generator": "structured_001",
        "code_assistant": "coding_001",
        "risk_checker": "hallucination_001",
    }
    router = {}
    for role, tkey in role_map.items():
        ranking = matrix["leaderboards"].get(tkey, {}).get("ranking", [])
        best = ranking[0] if ranking else {"model": matrix["models"][0]["label"], "score": 0}
        router[role] = {
            "preferred_model": best["model"],
            "evidence_task": tkey,
            "score": best["score"],
            "fallback_rule": "如果输出为空、JSON不可解析或延迟过高，切换到同任务排名第二的模型。",
        }
    return {
        "generated_at": now(),
        "purpose": "把 Day1 模型能力评估结果转化为 Day2 AI Learning Capability Module 的模型路由依据。",
        "product_direction": "StudyFlow S3：面向课程复习与资料整理的 AI 学习产品原型。",
        "router": router,
        "day2_requirements": [
            "提示词库必须区分产品规划、上下文组织、结构化输出、代码生成、风险复核。",
            "多模态上下文任务必须单独记录候选模型、输入类型和 fallback。",
            "结构化输出必须可解析为 JSON，并能被 Day3 Agent Core 读取。",
            "Day2 需要交付可调用的能力模块和 handoff 合约。",
        ],
        "assessment_question": "学生能否说明为什么某个模型适合某个产品任务，并能用失败样本支持 fallback 设计。",
    }


def build_model_pool_policy(matrix: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "generated_at": now(),
        "provider": "SiliconFlow",
        "classroom_policy": "学生可从硅基流动模型池中任选可用模型。参考答案中的 Kimi、DeepSeek、Qwen 只作为 baseline。",
        "baseline_models": matrix.get("models", []),
        "selection_tracks": [
            {
                "track": "text_reasoning",
                "required": True,
                "minimum_candidates": 2,
                "tasks": ["product_planner", "schema_generator", "code_assistant", "risk_checker"],
                "evidence": "同题输出、评分、延迟、失败样本、fallback 规则。",
            },
            {
                "track": "multimodal_context",
                "required": "if_available",
                "minimum_candidates": 1,
                "tasks": ["screenshot_understanding", "image_or_board_note_extraction", "device_ui_context"],
                "evidence": "输入类型、抽取字段、遗漏信息、不可用边界。",
            },
        ],
        "routing_roles": [
            "product_planner",
            "context_designer",
            "multimodal_context",
            "schema_generator",
            "code_assistant",
            "risk_checker",
        ],
        "assessment_rule": "不得只用总分选模型；必须按任务说明主模型、兜底模型和失败条件。",
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, title: str, body: str) -> None:
    path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")


def render_html(matrix: Dict[str, Any], day2_brief: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    model_cards = []
    for row in matrix["matrix"]:
        model_cards.append(
            f"<div class='panel'><h3>{escape(row['model_label'])}</h3>"
            f"<div class='kpi'>{row['avg_score']}</div><p class='muted'>平均分 / 平均延迟 {row['avg_latency_seconds']}s</p>"
            f"<p><b>适合：</b>{escape('、'.join(row['recommendation']))}</p></div>"
        )

    headers = "".join(f"<th>{escape(task['title'])}</th>" for task in matrix["tasks"])
    rows = []
    for model in matrix["matrix"]:
        cells = "".join(f"<td>{model['task_scores'].get(task['id'], '-')}</td>" for task in matrix["tasks"])
        rows.append(f"<tr><th>{escape(model['model_label'])}</th>{cells}</tr>")

    router_rows = []
    for role, rule in day2_brief["router"].items():
        router_rows.append(
            f"<tr><td>{escape(role)}</td><td>{escape(rule['preferred_model'])}</td>"
            f"<td>{escape(rule['evidence_task'])}</td><td>{escape(str(rule['score']))}</td></tr>"
        )

    samples = []
    for item in sorted(results, key=lambda x: (task_key(x), model_label(x)))[:12]:
        samples.append(
            f"<div class='mini'><b>{escape(task_title(item))}</b><span>{escape(model_label(item))} · score {score_item(item)}</span>"
            f"<p>{escape(short(output_text(item), 420))}</p></div>"
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Day1 模型能力评估与路由包</title>
  <style>
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#f6f7f9;color:#17202a;line-height:1.55}}
    header{{background:#243746;color:white;padding:30px 38px}} header h1{{margin:0 0 8px;font-size:30px}} header p{{margin:0;color:#dbe4ea;max-width:980px}}
    main{{max-width:1180px;margin:24px auto 48px;padding:0 20px}} .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
    .panel{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:18px;margin:14px 0}} .kpi{{font-size:28px;font-weight:760}} .muted{{color:#667789}}
    .mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}} .mini span{{color:#667789;margin-left:8px}} .mini p{{margin:8px 0;color:#314252}}
    table{{width:100%;border-collapse:collapse}} td,th{{border:1px solid #d8dee6;padding:9px;vertical-align:top;text-align:left}} a{{color:#0f766e;font-weight:650}}
    @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
<header><h1>Day1 模型能力评估与路由包</h1><p>学生从硅基流动模型池中选择候选模型，把文本与多模态能力差异转化为 Day2 可复用的模型路由和工程约束。</p></header>
<main>
  <div class="grid">
    <div class="panel"><div class="kpi">{len(matrix['models'])}</div><div class="muted">参赛模型</div></div>
    <div class="panel"><div class="kpi">{len(matrix['tasks'])}</div><div class="muted">任务维度</div></div>
    <div class="panel"><div class="kpi">{len(results)}</div><div class="muted">原始调用证据</div></div>
  </div>
  <div class="grid">{''.join(model_cards)}</div>
  <div class="panel"><h2>能力矩阵</h2><table><tr><th>模型</th>{headers}</tr>{''.join(rows)}</table></div>
  <div class="panel"><h2>导出给 Day2 的模型路由</h2><table><tr><th>产品任务</th><th>优先模型</th><th>证据任务</th><th>分数</th></tr>{''.join(router_rows)}</table></div>
  <div class="panel"><h2>课堂操作</h2><ol><li>先按任务观察 baseline 模型原始输出。</li><li>从硅基流动模型池选择自选候选模型，补充文本或多模态测试。</li><li>给每个任务确定主模型、兜底模型和失败条件。</li><li>把路由规则交给 Day2 的 AI Learning Capability Module。</li></ol></div>
  <div class="panel"><h2>关键样本</h2>{''.join(samples)}</div>
  <div class="panel"><h2>文件证据</h2><p><a href="model_pool_policy.json">model_pool_policy.json</a> / <a href="model_capability_matrix.json">model_capability_matrix.json</a> / <a href="day1_to_day2_brief.json">day1_to_day2_brief.json</a> / <a href="model_selection_playbook.md">model_selection_playbook.md</a> / <a href="failure_casebook.md">failure_casebook.md</a> / <a href="student_task_cards.md">student_task_cards.md</a></p></div>
</main>
</body>
</html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not RESULTS.exists():
        print("[MOCK] No day1_results.json found — generating mock evaluation data...")
        results = generate_mock_results()
        write_json(RESULTS, results)
    else:
        results = load_results()

    matrix = build_matrix(results)
    day2_brief = build_day2_brief(matrix)
    model_pool_policy = build_model_pool_policy(matrix)
    write_json(OUT / "model_capability_matrix.json", matrix)
    write_json(OUT / "day1_to_day2_brief.json", day2_brief)
    write_json(OUT / "model_pool_policy.json", model_pool_policy)

    playbook = "\n".join(
        [
            "## 选型原则",
            "- 创意、结构化、代码、事实诚实性要分开评估，不能用一个总分替代工程判断。",
            "- 学生可从硅基流动模型池中任选可用模型；参考答案中的 Kimi、DeepSeek、Qwen 只是 baseline。",
            "- 多模态模型单独评估：截图、图像、板书、设备界面属于不同任务轨道。",
            "- Day2 能力模块使用多模型路由：不同产品任务调用最适合的模型。",
            "- 所有模型输出必须留下原始证据、评分和失败样本，作为 assessment 的可解释依据。",
            "",
            "## Day2 接力方式",
            "- `day1_to_day2_brief.json` 直接进入 Day2 的 `context_pack/`。",
            "- Day2 必须根据该 brief 生成 Prompt Library、JSON Schema、Eval Cases 和 Agent Handoff Contract。",
        ]
    )
    write_markdown(OUT / "model_selection_playbook.md", "Day1 模型选型手册", playbook)

    failure_lines = ["## 失败/风险样本", ""]
    for item in results:
        text = output_text(item)
        if score_item(item) <= 3 or not item.get("ok") or len(text) < 80:
            failure_lines.append(f"### {task_title(item)} / {model_label(item)} / score={score_item(item)}")
            failure_lines.append(f"- 风险摘要：{short(text, 380)}")
            failure_lines.append("- 课堂追问：这个失败会如何影响 Day2 能力模块的稳定性？")
            failure_lines.append("")
    if len(failure_lines) <= 2:
        failure_lines.extend(["当前样本整体得分较高，课堂可让学生主动构造反例：长上下文、模糊需求、格式约束冲突、未知事实。"])
    write_markdown(OUT / "failure_casebook.md", "Day1 失败样本手册", "\n".join(failure_lines))

    cards = """## 学生任务卡

1. 选一个 Day2 产品任务：复习卡生成、答题评分、多模态上下文抽取、错题归因、设备短回复。
2. 从硅基流动模型池里选择主模型和兜底模型；参考答案可作为 baseline。
3. 写出选择理由：引用任务、原始输出、评分、失败风险和 fallback 条件。
4. 把结果写入 `day1_to_day2_brief.json`，交给 Day2 能力模块使用。

## 交付标准

- 至少说明一个模型强项。
- 至少指出一个失败或风险场景。
- 至少说明一个多模态模型的适用边界，或说明当前不选择多模态模型的原因。
- 至少给出一个 Day2 可执行的模型路由规则。
"""
    write_markdown(OUT / "student_task_cards.md", "Day1 学生任务卡", cards)

    html = render_html(matrix, day2_brief, results)
    (OUT / "Day1_模型能力评估控制台.html").write_text(html, encoding="utf-8")
    (OUT / "Day1_能力矩阵.html").write_text(html, encoding="utf-8")
    print(json.dumps({"ok": True, "models": len(matrix["models"]), "tasks": len(matrix["tasks"]), "results": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
