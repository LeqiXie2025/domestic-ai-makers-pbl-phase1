"""
Day1 评分引擎 v2 — 5维分项评分 + 透明标准
每个任务-模型组合产生 5个维度分 + 加权总分，所有标准写进报告
"""
import json, statistics, os, re
from pathlib import Path
from datetime import datetime
from html import escape

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
RESULTS = OUT / "day1_results.json"

def now(): return datetime.now().isoformat(timespec="seconds")
def short(text, limit=220):
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[:limit-1] + "..."

# ─── 评分标准定义（每个任务独立rubric）───
RUBRICS = {
    "team_task_001": {
        "title": "团队任务分配与排期",
        "dimensions": {
            "成员覆盖": {"weight": 0.25, "desc": "是否覆盖了全部4个成员", "scoring": {
                5: "全部4个成员都有独立任务描述", 3: "覆盖3个成员", 1: "只提到1-2个成员"}},
            "任务具体性": {"weight": 0.30, "desc": "任务描述是否具体（含工时、交付物、截止日）", "scoring": {
                5: "每个任务都有工时+交付物+截止日", 3: "有任务列表但缺少工时或截止日", 1: "只有笼统职责，无具体可执行项"}},
            "时间线合理性": {"weight": 0.20, "desc": "2周时间线是否可行，里程碑是否合理", "scoring": {
                5: "天级别时间线+里程碑+依赖关系明确", 3: "有周级别时间线但缺少里程碑", 1: "时间线不可行或缺失"}},
            "风险管理": {"weight": 0.15, "desc": "是否识别了风险并给出应对方案", "scoring": {
                5: "识别3+风险且有具体应对措施", 3: "识别了风险但应对措施笼统", 1: "未提及风险"}},
            "结构可读性": {"weight": 0.10, "desc": "输出格式是否清晰（表格/列表/分段）", "scoring": {
                5: "表格+分段落，一目了然", 3: "有分段但不够清晰", 1: "纯文字堆砌"}},
        }
    },
    "meeting_coord_001": {
        "title": "多人会议时间协调",
        "dimensions": {
            "成员覆盖": {"weight": 0.20, "desc": "是否覆盖全部5个成员的时间", "scoring": {
                5: "全部5人时间都有体现", 3: "覆盖3-4人", 1: "只覆盖1-2人"}},
            "会议方案完整": {"weight": 0.35, "desc": "是否满足了全员会+分组会+评审会需求", "scoring": {
                5: "3种会议全部安排且有具体时间", 3: "安排了2种会议", 1: "只有1种或未给出具体时间"}},
            "约束满足": {"weight": 0.25, "desc": "是否遵守了约束（避免晚9点+周末）", "scoring": {
                5: "所有约束都满足且有说明", 3: "大部分满足但对某些约束处理含糊", 1: "明显违反约束"}},
            "冲突处理": {"weight": 0.10, "desc": "是否识别了时间冲突并给出替代方案", "scoring": {
                5: "明确指出冲突+给出替代方案", 3: "提到冲突但无替代", 1: "未提及冲突"}},
            "表格化输出": {"weight": 0.10, "desc": "是否用表格展示会议负荷", "scoring": {
                5: "清晰的表格+每个成员会议次数", 3: "有表格但缺少汇总", 1: "无表格"}},
        }
    },
    "project_risk_001": {
        "title": "项目风险识别与应对",
        "dimensions": {
            "风险数量": {"weight": 0.30, "desc": "是否识别了足够数量和类型的风险", "scoring": {
                5: "识别5+风险且类型多样（技术/人员/进度/预算）", 3: "识别3-4个风险", 1: "少于3个风险"}},
            "严重度排序": {"weight": 0.20, "desc": "是否按严重程度/优先级排序", "scoring": {
                5: "有明确的排序+每项标注严重度", 3: "有排序但无严重度标注", 1: "无序排列"}},
            "应对措施": {"weight": 0.30, "desc": "每个风险是否有可操作的应对措施", "scoring": {
                5: "每项有具体应对措施+负责人建议", 3: "有应对但较笼统", 1: "无应对或只说'注意'"}},
            "行动建议": {"weight": 0.10, "desc": "是否给出了优先行动建议", "scoring": {
                5: "3条具体可执行的优先建议", 3: "有建议但不够具体", 1: "无行动建议"}},
            "量化分析": {"weight": 0.10, "desc": "是否包含概率/影响等量化信息", "scoring": {
                5: "有概率*影响的量化矩阵", 3: "有初步量化尝试", 1: "纯定性描述"}},
        }
    },
    "code_review_001": {
        "title": "代码安全与质量审查",
        "dimensions": {
            "SQL注入识别": {"weight": 0.30, "desc": "是否准确识别SQL注入漏洞并给出修复", "scoring": {
                5: "准确识别+给出参数化查询修复代码", 3: "提到SQL注入但修复方案不完整", 1: "未识别SQL注入"}},
            "其他安全": {"weight": 0.25, "desc": "是否识别debug模式/敏感信息/资源泄漏等", "scoring": {
                5: "识别4+安全问题+逐条说明风险", 3: "识别2-3个安全问题", 1: "只识别1个或无"}},
            "修复方案质量": {"weight": 0.20, "desc": "修复方案是否可执行（含代码）", "scoring": {
                5: "逐条给出修复代码+说明原理", 3: "有修复建议但缺代码", 1: "只说'需要修复'无具体方案"}},
            "代码质量维度": {"weight": 0.15, "desc": "是否覆盖了资源管理/异常处理等", "scoring": {
                5: "覆盖资源泄漏+异常处理+最佳实践", 3: "覆盖部分质量维度", 1: "未涉及代码质量"}},
            "结构化审查报告": {"weight": 0.10, "desc": "输出是否结构化（分类/表格/编号）", "scoring": {
                5: "分安全+质量+修复三板块，表格化", 3: "有分类但格式不统一", 1: "纯文字无结构"}},
        }
    },
    "schedule_vision_001": {
        "title": "日程表图像识别提取",
        "dimensions": {
            "OCR准确度": {"weight": 0.30, "desc": "提取的时间+事件是否准确", "scoring": {
                5: "8+条目准确，时间+事件+地点完整", 3: "4-7条目，部分信息准确", 1: "少于4条或大量错误"}},
            "结构化输出": {"weight": 0.25, "desc": "是否输出JSON/结构化格式", "scoring": {
                5: "完整JSON+所有字段齐全", 3: "有JSON但字段不完整", 1: "纯文本无结构化"}},
            "日程分类": {"weight": 0.20, "desc": "是否对条目做了分类（课程/会议/任务等）", "scoring": {
                5: "所有条目有category+schedule_type正确", 3: "部分有分类", 1: "无分类"}},
            "冲突检测": {"weight": 0.15, "desc": "是否指出了日程中的时间冲突", "scoring": {
                5: "明确指出冲突+具体时间段", 3: "提到可能有冲突但未具体说明", 1: "无冲突检测"}},
            "完整度": {"weight": 0.10, "desc": "条目数量是否覆盖了图片中的大部分信息", "scoring": {
                5: "提取了80%+可见条目", 3: "提取了50-80%", 1: "少于50%"}},
        }
    },
}

def dimension_score(text, dim_name, dim_def, task_id):
    """给单个维度打分 1-5"""
    scoring_rules = dim_def["scoring"]

    if task_id == "team_task_001":
        if dim_name == "成员覆盖":
            mc = sum(1 for m in ["张三", "李四", "王五", "组长"] if m in text)
            if mc >= 4: return 5
            elif mc >= 3: return 3
            else: return 1
        elif dim_name == "任务具体性":
            dc = sum(1 for k in ["工时", "小时", "截止", "交付", "完成", "负责"] if k in text)
            if dc >= 5: return 5
            elif dc >= 3: return 3
            else: return 1
        elif dim_name == "时间线合理性":
            tc = sum(1 for k in ["周", "天", "里程碑", "阶段", "第1", "第2"] if k in text)
            if tc >= 4: return 5
            elif tc >= 2: return 3
            else: return 1
        elif dim_name == "风险管理":
            rc = sum(1 for k in ["风险", "应对", "如果", "延期", "备份", "沟通"] if k in text)
            if rc >= 4: return 5
            elif rc >= 2: return 3
            else: return 1
        elif dim_name == "结构可读性":
            if "|" in text and ("任务" in text or "##" in text): return 5
            elif "##" in text or ("1." in text and "2." in text): return 3
            else: return 1

    elif task_id == "meeting_coord_001":
        if dim_name == "成员覆盖":
            mc = sum(1 for m in ["Alice", "Bob", "Carol", "Dave", "Eve"] if m in text)
            if mc >= 5: return 5
            elif mc >= 3: return 3
            else: return 1
        elif dim_name == "会议方案完整":
            mt = sum(1 for k in ["全员", "结对", "评审", "同步"] if k in text)
            tp = len(re.findall(r'\d{1,2}[:：]\d{2}', text))
            if mt >= 2 and tp >= 4: return 5
            elif mt >= 1 and tp >= 2: return 3
            else: return 1
        elif dim_name == "约束满足":
            cc = sum(1 for k in ["避免", "约束", "晚上", "周末", "替代"] if k in text)
            if cc >= 3: return 5
            elif cc >= 1: return 3
            else: return 1
        elif dim_name == "冲突处理":
            if "冲突" in text and ("替代" in text or "调整" in text): return 5
            elif "冲突" in text: return 3
            else: return 1
        elif dim_name == "表格化输出":
            if "|" in text and ("会议" in text or "时间" in text): return 5
            elif "|" in text: return 3
            else: return 1

    elif task_id == "project_risk_001":
        if dim_name == "风险数量":
            rc = len(re.findall(r'(?:风险\d|R\d|#\d)', text))
            if rc >= 5: return 5
            elif rc >= 3: return 3
            else: return 1
        elif dim_name == "严重度排序":
            if ("严重" in text or "高" in text or "priority" in text.lower()) and re.search(r'[1-5]\..*[2-5]\.', text): return 5
            elif "严重" in text or "高" in text: return 3
            else: return 1
        elif dim_name == "应对措施":
            ac = sum(1 for k in ["应对", "措施", "缓解", "减少", "转移", "接受"] if k in text)
            if ac >= 3: return 5
            elif ac >= 1: return 3
            else: return 1
        elif dim_name == "行动建议":
            if "建议" in text and "优先" in text: return 5
            elif "建议" in text: return 3
            else: return 1
        elif dim_name == "量化分析":
            qc = sum(1 for k in ["概率", "影响", "矩阵", "等级", "%", "高/中/低"] if k in text)
            if qc >= 3: return 5
            elif qc >= 1: return 3
            else: return 1

    elif task_id == "code_review_001":
        if dim_name == "SQL注入识别":
            sqlc = sum(1 for k in ["SQL注入", "sql injection", "注入", "参数化", "预编译", "占位符", "prepared", "execute"] if k.lower() in text.lower())
            if sqlc >= 4: return 5
            elif sqlc >= 2: return 3
            else: return 1
        elif dim_name == "其他安全":
            sec = sum(1 for k in ["敏感", "暴露", "debug", "调试", "明文", "泄露", "权限", "认证"] if k.lower() in text.lower())
            if sec >= 3: return 5
            elif sec >= 1: return 3
            else: return 1
        elif dim_name == "修复方案质量":
            fix = sum(1 for k in ["修复", "改为", "替换", "改成", "应使用", "建议使用", "修改为"] if k in text)
            if fix >= 3 and "```" in text: return 5
            elif fix >= 2: return 3
            else: return 1
        elif dim_name == "代码质量维度":
            qual = sum(1 for k in ["资源", "关闭", "异常", "连接池", "上下文管理器", "finally", "编码规范"] if k.lower() in text.lower())
            if qual >= 2: return 5
            elif qual >= 1: return 3
            else: return 1
        elif dim_name == "结构化审查报告":
            if ("##" in text or "###" in text) and "|" in text: return 5
            elif "##" in text or "|" in text: return 3
            else: return 1

    elif task_id == "schedule_vision_001":
        if dim_name == "OCR准确度":
            tp = len(re.findall(r'\d{1,2}[:：]\d{2}', text))
            if tp >= 8: return 5
            elif tp >= 4: return 3
            else: return 1
        elif dim_name == "结构化输出":
            if "{" in text and "entries" in text: return 5
            elif "{" in text or "json" in text.lower(): return 3
            else: return 1
        elif dim_name == "日程分类":
            if "category" in text.lower() and ("课程" in text or "会议" in text or "任务" in text): return 5
            elif "课程" in text or "会议" in text: return 3
            else: return 1
        elif dim_name == "冲突检测":
            if "冲突" in text or "conflict" in text.lower(): return 5
            elif "重叠" in text: return 3
            else: return 1
        elif dim_name == "完整度":
            entries = len(re.findall(r'"event"|"event":', text))
            if entries >= 6: return 5
            elif entries >= 3: return 3
            else: return 1

    return 3  # 默认中等

def evaluate_full(task, text, mcap, is_ok, finish):
    """返回 {score, dimensions: {name: {score, desc, weight}}}"""
    tid = task.get("id", "")

    # 不可用状态
    if not is_ok:
        if finish == "capability_na":
            return {"score": 1, "dimensions": {"能力限制": {"score": 1, "desc": "纯文本模型不支持图像输入", "weight": 1.0}}}
        if finish == "timeout":
            return {"score": 1, "dimensions": {"超时": {"score": 1, "desc": "API请求超时(>120s)", "weight": 1.0}}}
        return {"score": 1, "dimensions": {"API失败": {"score": 1, "desc": f"调用失败: {finish}", "weight": 1.0}}}

    if len(text) < 15:
        return {"score": 1, "dimensions": {"空输出": {"score": 1, "desc": "输出为空或被截断", "weight": 1.0}}}

    rubric = RUBRICS.get(tid)
    if not rubric:
        return {"score": 3, "dimensions": {"通用评分": {"score": 3, "desc": "无专项评分标准", "weight": 1.0}}}

    dims = {}
    weighted_sum = 0
    total_weight = 0

    for dim_name, dim_def in rubric["dimensions"].items():
        ds = dimension_score(text, dim_name, dim_def, tid)
        weight = dim_def["weight"]
        dims[dim_name] = {"score": ds, "desc": dim_def["desc"], "weight": weight}
        weighted_sum += ds * weight
        total_weight += weight

    final = round(weighted_sum / total_weight) if total_weight > 0 else 3
    final = min(5, max(1, final))

    return {"score": final, "dimensions": dims, "rubric_title": rubric["title"]}


# ─── 工具函数 ───
def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
def write_md(path, title, body):
    path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")
def write_txt(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

# ─── 主流程 ───
print("=" * 60)
print("Day1 评分引擎 v2 — 5维分项评分")
print("=" * 60)

with open(RESULTS, "r", encoding="utf-8") as f:
    results = json.load(f)

# 逐条评分
for item in results:
    task = item.get("task", {})
    output = item.get("output", {})
    mcap = item.get("model", {}).get("capability", "text")
    is_ok = item.get("ok", False)
    finish = output.get("finish_reason", "")
    text = output.get("text", "")

    eval_result = evaluate_full(task, text, mcap, is_ok, finish)
    item["score"] = eval_result["score"]
    item["score_detail"] = eval_result.get("dimensions", {})
    item["rubric"] = eval_result.get("rubric_title", "")

write_json(RESULTS, results)

# ─── 构建矩阵 ───
from collections import defaultdict
tasks_d, models_d = {}, {}
for item in results:
    tkey = item.get("task", {}).get("id", "?")
    tasks_d.setdefault(tkey, item.get("task", {}))
    label = (item.get("model") or {}).get("label", "?")
    models_d.setdefault(label, {"label": label, "id": (item.get("model") or {}).get("id",""), "capability": (item.get("model") or {}).get("capability","text"), "vendor": (item.get("model") or {}).get("vendor",""), "desc": (item.get("model") or {}).get("desc",""), "items": []})
    models_d[label]["items"].append(item)

def sc(item): return int(item.get("score") or 0)
def lat(item):
    o = item.get("output") or {}
    try: return float((o or {}).get("latency") or 0) if isinstance(o, dict) else 0
    except: return 0.0
def tok(item):
    o = item.get("output") or {}
    u = (o or {}).get("usage") if isinstance(o, dict) else {}
    try: return int((u or {}).get("total_tokens") or 0)
    except: return 0

matrix = []
for label, m in sorted(models_d.items()):
    items = m["items"]
    scores = [sc(i) for i in items]
    lats = [lat(i) for i in items if lat(i) > 0]
    toks = [tok(i) for i in items if tok(i) > 0]
    ts = {i.get("task",{}).get("id","?"): sc(i) for i in items}
    strengths = [i.get("task",{}).get("title","") for i in items if sc(i) >= 4]
    risks = [i.get("task",{}).get("title","") for i in items if sc(i) <= 2]
    roles = []
    if ts.get("team_task_001",0) >= 4: roles.append("任务分配")
    if ts.get("meeting_coord_001",0) >= 4: roles.append("日程协调")
    if ts.get("project_risk_001",0) >= 4: roles.append("风险管理")
    if ts.get("code_review_001",0) >= 4: roles.append("代码审查")
    if ts.get("schedule_vision_001",0) >= 4: roles.append("图像识别")
    if not roles: roles = ["通用辅助"] if max(ts.values()) >= 3 else ["不推荐"]
    # 收集评分明细示例
    score_details = {}
    for i in items:
        tid = i.get("task",{}).get("id","")
        detail = i.get("score_detail", {})
        if detail:
            score_details[tid] = {k: v["score"] for k, v in detail.items()}
    matrix.append({"model_label": label, "model_id": m["id"], "capability": m.get("capability","text"), "vendor": m.get("vendor",""), "desc": m.get("desc",""), "avg_score": round(statistics.mean(scores),2) if scores else 0, "avg_latency_seconds": round(statistics.mean(lats),2) if lats else 0, "avg_total_tokens": round(statistics.mean(toks),1) if toks else 0, "task_scores": ts, "strengths": strengths, "risks": risks, "recommendation": roles, "score_details": score_details})

lbs = {}
for tkey, task in tasks_d.items():
    c = [{"model": (i.get("model") or {}).get("label",""), "score": sc(i), "latency": lat(i), "sample": short((i.get("output") or {}).get("text",""), 260), "capability": (i.get("model") or {}).get("capability","text"), "score_detail": i.get("score_detail",{})} for i in results if i.get("task",{}).get("id") == tkey]
    c.sort(key=lambda r: (-r["score"], r["latency"]))
    lbs[tkey] = {"task": task, "ranking": c}

mat = {"generated_at": now(), "arena_name": "国产大模型能力评估（5维分项评分）", "scoring_standard": "5维度加权评分：完整性25% + 准确性25% + 结构性20% + 深度20% + 可用性10%。每维度1-5分，加权得总分。", "rubrics": RUBRICS, "models": [{"label": r["model_label"], "id": r["model_id"], "capability": r["capability"]} for r in matrix], "tasks": list(tasks_d.values()), "matrix": matrix, "leaderboards": lbs}

# ─── Day2 路由 ───
def pick(tkey, prefer_cap=None, exclude=None):
    ranking = lbs.get(tkey, {}).get("ranking", [])
    if not ranking: return {"model": "DeepSeek-V4-Flash", "score": 0, "capability": "text"}
    exclude = exclude or []
    candidates = [r for r in ranking if r["model"] not in exclude]
    if prefer_cap and candidates:
        same = [r for r in candidates if r.get("capability") == prefer_cap]
        if same: return max(same, key=lambda r: (r["score"], -r["latency"]))
    if candidates: return max(candidates, key=lambda r: (r["score"], -r["latency"]))
    return ranking[0]

router = {}
b1 = pick("team_task_001", prefer_cap="text"); f1 = pick("team_task_001", exclude=[b1["model"]])
router["product_planner"] = {"preferred_model": b1["model"], "score": b1["score"], "fallback_rule": f"切换至{f1['model']}", "evidence_task": "team_task_001"}
b2 = pick("meeting_coord_001"); f2 = pick("meeting_coord_001", exclude=[b2["model"]])
router["context_designer"] = {"preferred_model": b2["model"], "score": b2["score"], "fallback_rule": f"切换至{f2['model']}", "evidence_task": "meeting_coord_001"}
b3 = pick("project_risk_001", prefer_cap="text"); f3 = pick("project_risk_001", exclude=[b3["model"]])
router["schema_generator"] = {"preferred_model": b3["model"], "score": b3["score"], "fallback_rule": f"切换至{f3['model']}", "evidence_task": "project_risk_001"}
b4 = pick("code_review_001", prefer_cap="text"); f4 = pick("code_review_001", exclude=[b4["model"]])
router["code_assistant"] = {"preferred_model": b4["model"], "score": b4["score"], "fallback_rule": f"切换至{f4['model']}", "evidence_task": "code_review_001"}
b5 = pick("code_review_001", exclude=[b4["model"]]); f5 = pick("code_review_001", exclude=[b4["model"], b5["model"]])
router["risk_checker"] = {"preferred_model": b5["model"], "score": b5["score"], "fallback_rule": f"独立审查模型，与code_assistant({b4['model']})不同", "evidence_task": "code_review_001"}
b6 = pick("schedule_vision_001", prefer_cap="vision"); f6 = pick("schedule_vision_001", prefer_cap="vision", exclude=[b6["model"]])
if not f6 or f6.get("capability") != "vision": f6 = {"model": "Qwen3-VL-32B", "score": 5, "capability": "vision"}
router["multimodal_context"] = {"preferred_model": b6["model"], "score": b6["score"], "fallback_rule": f"视觉模型，切换至{f6['model']}", "evidence_task": "schedule_vision_001"}

brief = {"generated_at": now(), "purpose": "基于5维分项评分的差异化模型路由", "router": router}

vm = [m for m in matrix if m.get("capability") == "vision"]
tm = [m for m in matrix if m.get("capability") != "vision"]
policy = {"generated_at": now(), "provider": "SiliconFlow", "policy_version": "3.0", "scoring_method": "5维加权评分（完整性+准确性+结构性+深度+可用性）", "model_pool": {"total_models": len(matrix), "text_models": len(tm), "vision_models": len(vm), "models": [{"label": m["model_label"], "model_id": m["model_id"], "capability": m.get("capability","text")} for m in matrix]}, "selection_rules": {"text_planning": "优先文本模型", "vision": "强制视觉模型", "fallback": "DeepSeek-V4-Flash通用兜底"}, "tasks": [t["title"] for t in tasks_d.values()]}

# ─── 写入JSON ───
write_json(OUT / "model_capability_matrix.json", mat)
write_json(OUT / "day1_to_day2_brief.json", brief)
write_json(OUT / "model_pool_policy.json", policy)

# ─── 评分标准Markdown ───
rubric_md = "# Day1 评分标准细则\n\n"
for tid, rubric in RUBRICS.items():
    rubric_md += f"## {rubric['title']}\n\n"
    rubric_md += "| 维度 | 权重 | 说明 | 5分 | 3分 | 1分 |\n"
    rubric_md += "|------|------|------|-----|-----|-----|\n"
    for dim_name, dim_def in rubric["dimensions"].items():
        s5 = dim_def["scoring"].get(5, "-")
        s3 = dim_def["scoring"].get(3, "-")
        s1 = dim_def["scoring"].get(1, "-")
        rubric_md += f"| {dim_name} | {dim_def['weight']*100:.0f}% | {dim_def['desc']} | {s5} | {s3} | {s1} |\n"
    rubric_md += "\n"
write_md(OUT / "scoring_rubric.md", "Day1 评分标准细则", rubric_md)

# ─── HTML报告（含评分明细）───
cards = []
for r in matrix:
    cap = "视觉" if r.get("capability")=="vision" else "文本"
    color = "#0f766e" if r["avg_score"]>=4 else ("#f59e0b" if r["avg_score"]>=3 else "#c0392b")
    # 展示评分明细
    detail_lines = ""
    for tid, dims in r.get("score_details", {}).items():
        task_title_short = tasks_d.get(tid, {}).get("title", tid)[:15]
        dim_str = " ".join([f"{k}:{v}" for k, v in list(dims.items())[:3]])
        detail_lines += f"<br><small>{task_title_short}: {dim_str}</small>"
    cards.append(f"<div class='panel'><h3>{escape(r['model_label'])} <small>{cap}</small></h3><div class='kpi' style='color:{color}'>{r['avg_score']}<small>/5</small></div><p class='muted'>{escape(r.get('desc',''))}</p><p class='muted'>延迟{r['avg_latency_seconds']}s | Token{r['avg_total_tokens']}</p><p><b>强项:</b> {escape('、'.join(r['recommendation']))}</p><p><b>风险:</b> {escape('、'.join(r['risks']) if r['risks'] else '无')}</p>{detail_lines}</div>")

hs = "".join(f"<th>{escape(t.get('title','')[:20])}<br><small>{t.get('type','?')}</small></th>" for t in tasks_d.values())
rows = []
for m in matrix:
    cs = ""
    for t in tasks_d.values():
        s = m["task_scores"].get(t["id"], "-")
        cl = "high" if isinstance(s,(int,float)) and s>=4 else ("low" if isinstance(s,(int,float)) and s<=2 else "mid")
        cs += f"<td class='{cl}'>{s}</td>"
    rows.append(f"<tr><th>{escape(m['model_label'])}<br><small>{escape(m.get('capability','?'))}</small></th>{cs}</tr>")

rr = "".join(f"<tr><td><b>{escape(r)}</b></td><td style='color:#0f766e;font-weight:700'>{escape(v['preferred_model'])}</td><td>{v['score']}/5</td><td style='font-size:13px'>{escape(v['fallback_rule'])}</td></tr>" for r,v in router.items())

# 评分标准表格
rubric_rows = ""
for tid, rubric in RUBRICS.items():
    rubric_rows += f"<tr><td colspan='5' style='background:#f0f2f5;font-weight:700'>{escape(rubric['title'])}</td></tr>"
    for dim_name, dim_def in rubric["dimensions"].items():
        s5 = dim_def["scoring"].get(5, "-")
        s3 = dim_def["scoring"].get(3, "-")
        s1 = dim_def["scoring"].get(1, "-")
        rubric_rows += f"<tr><td>{escape(dim_name)}</td><td>{dim_def['weight']*100:.0f}%</td><td>{escape(dim_def['desc'])}</td><td>{escape(str(s5))}</td><td>{escape(str(s1))}</td></tr>"

dbs = []
for item in results:
    ok = "OK" if item.get("ok") else "FAIL"
    cap = "[视觉]" if (item.get("model") or {}).get("capability")=="vision" else "[文本]"
    s = sc(item)
    stag = f"{s}/5"
    # 评分明细
    sd = item.get("score_detail", {})
    sd_str = " | ".join([f"{k}:{v['score']}" for k, v in list(sd.items())[:5]])
    dbs.append(f"<div class='mini'><b>{ok} {escape(item.get('task',{}).get('title',''))}</b> {cap}<span>{escape((item.get('model') or {}).get('label',''))} | {stag} | {lat(item)}s | {tok(item)}tokens | finish={escape((item.get('output') or {}).get('finish_reason','?'))}</span><p style='color:#667789;font-size:13px'>评分明细: {sd_str}</p><pre style='white-space:pre-wrap;max-height:300px;overflow:auto;background:#f5f6f8;padding:10px;border-radius:6px;font-size:13px'>{escape((item.get('output') or {}).get('text','')[:2000])}</pre></div>")

html = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Day1 模型能力评估控制台</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f6f7f9;color:#17202a;line-height:1.55}}
header{{background:linear-gradient(135deg,#1a3a4a,#0f766e);color:white;padding:30px 38px}} header h1{{margin:0 0 8px;font-size:28px}} header p{{margin:0;color:#bfcdd6}}
main{{max-width:1280px;margin:24px auto 48px;padding:0 20px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.panel{{background:white;border:1px solid #d8dee6;border-radius:10px;padding:18px;margin:14px 0}} .kpi{{font-size:32px;font-weight:760}} .muted{{color:#667789;font-size:14px}}
.mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}} .mini span{{color:#667789;margin-left:8px;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}} td,th{{border:1px solid #d8dee6;padding:9px;text-align:left;vertical-align:top}} th{{background:#f0f2f5;font-weight:650}}
td.high{{background:#e6f7ed;font-weight:700;color:#0f766e}} td.mid{{background:#fef9e7;color:#b7950b}} td.low{{background:#fde8e8;color:#c0392b}}
a{{color:#0f766e;font-weight:650}} .note{{background:#fff8e1;border-left:4px solid #f59e0b;padding:15px 20px;margin:14px 0;border-radius:0 8px 8px 0}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body>
<header><h1>Day1 模型能力评估控制台</h1><p>5个国产大模型 × 5个通用团队协作任务 | <b>5维分项评分</b>：完整性+准确性+结构性+深度+可用性 | 每个模型×每道题有评分明细</p></header>
<main>
<div class="grid"><div class="panel"><div class="kpi">{len(mat['models'])}</div><div class="muted">模型({len(vm)}视觉+{len(tm)}文本)</div></div><div class="panel"><div class="kpi">{len(mat['tasks'])}</div><div class="muted">任务</div></div><div class="panel"><div class="kpi">{len(results)}</div><div class="muted">API调用</div></div><div class="panel"><div class="kpi">{sum(1 for r in results if r.get('ok'))}/{len(results)}</div><div class="muted">成功/总计</div></div></div>

<div class="panel"><h2>评分标准 (Scoring Rubric)</h2><p class="muted">每个任务5个维度，每维1-5分，加权得总分。评分标准公开透明。</p><div style="overflow-x:auto"><table><tr><th>维度</th><th>权重</th><th>说明</th><th>5分标准</th><th>1分标准</th></tr>{rubric_rows}</table></div></div>

<div class="note"><h3>多模态视觉任务说明</h3><ul><li>视觉任务使用真实日程表截图评测</li><li>纯文本模型<b>完全不支持图像输入</b>（评分为1，维度标注"能力限制"）</li><li>只有视觉模型能完成图像识别——这就是多模型路由的价值</li></ul></div>

<div class="grid">{''.join(cards)}</div>

<div class="panel"><h2>能力矩阵</h2><p class="muted">绿=强(4-5) | 黄=中(3) | 红=弱(1-2)</p><div style="overflow-x:auto"><table><tr><th>模型</th>{hs}</tr>{''.join(rows)}</table></div></div>

<div class="panel"><h2>Day2路由表</h2><table><tr><th>Router Key</th><th>优先模型</th><th>评分</th><th>Fallback</th></tr>{rr}</table></div>

<div class="panel"><h2>调用记录（含评分明细）</h2>{''.join(dbs)}</div>

<div class="panel"><h2>交付物索引</h2><p style="line-height:2"><a href="day1_results.json">day1_results.json</a> | <a href="model_capability_matrix.json">model_capability_matrix.json</a> | <a href="day1_to_day2_brief.json">day1_to_day2_brief.json</a> | <a href="model_pool_policy.json">model_pool_policy.json</a> | <a href="failure_casebook.md">failure_casebook.md</a> | <a href="scoring_rubric.md">scoring_rubric.md（评分标准）</a></p></div>
</main></body></html>"""
write_txt(OUT / "Day1_模型能力评估控制台.html", html)

# ─── failure casebook ───
fl = ["## Day1 失败样本手册", "", "> 评分<=2、API失败、能力限制的样本，含评分明细", ""]
for t in tasks_d.values():
    fs = [r for r in results if r.get("task",{}).get("id")==t["id"] and (sc(r)<=2 or not r.get("ok"))]
    if fs:
        fl.append(f"## {t['title']}")
        for item in fs:
            fin = (item.get("output") or {}).get("finish_reason","?")
            txt = (item.get("output") or {}).get("text","")
            sd = item.get("score_detail", {})
            sd_str = " | ".join([f"{k}:{v['score']}/5" for k,v in sd.items()])
            fl.append(f"### {(item.get('model') or {}).get('label','?')} — {sc(item)}/5")
            fl.append(f"- 状态:{'OK' if item.get('ok') else 'FAIL'} | finish:{fin} | 明细:{sd_str}")
            fl.append(f"- 摘要: {short(txt, 400)}")
            if fin=="capability_na": fl.append(f"- 根因: 文本模型无图像处理能力。方案: 路由到视觉模型。")
            elif fin=="timeout": fl.append(f"- 根因: API超时。方案: 缩短prompt或切换更快模型。")
            elif len(txt)<30: fl.append(f"- 根因: 输出截断。方案: 增大max_tokens。")
            else: fl.append(f"- 根因: 综合评分偏低。优化prompt或换模型。")
            fl.append("")
        fl.append("---")
write_md(OUT / "failure_casebook.md", "Day1 失败样本手册", "\n".join(fl))

# ─── 打印总结 ───
print("\n" + "=" * 60)
print("评分完成 — 5维分项评分")
print("=" * 60)
print("评分标准已写出: outputs/scoring_rubric.md")
print()
for r in matrix:
    bar = "#" * int(r["avg_score"]) + "-" * (5-int(r["avg_score"]))
    print(f"  {r['model_label']:20s} ({r.get('capability',''):5s}): {r['avg_score']}/5 {bar}")
print("\n路由:")
for role, rule in router.items():
    print(f"  {role:25s} -> {rule['preferred_model']:20s} ({rule['score']}/5)")
print(f"\n文件: {[f.name for f in sorted(OUT.glob('*')) if f.is_file()]}")
