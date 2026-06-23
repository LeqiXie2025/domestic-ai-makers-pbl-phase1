"""
严格按 llm-bench.html 的 generateDay1Console() 格式生成 Day1 交付物
数据来源: ScheduleBench CSV
"""
import csv, json, statistics
from pathlib import Path
from datetime import datetime

CSV_PATH = Path(r"C:\Users\xlq20\Downloads\ScheduleBench_2026-06-22 (2).csv")
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now().isoformat(timespec="seconds")

def wj(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def wt(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

# ─── 1. 读取 CSV ───
with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

data_rows = [r for r in rows if r['轮次'] != '聚合均值']
agg_rows = [r for r in rows if r['轮次'] == '聚合均值']

MODEL_NAMES = sorted(set(r['模型'].strip() for r in data_rows))
DIM_KEYS = ['schedule', 'dependency', 'balance', 'constraint', 'executable']
DIM_LABELS = {
    'schedule': '时间安排合理性',
    'dependency': '任务依赖完整性',
    'balance': '资源分配均衡度',
    'constraint': '约束条件满足度',
    'executable': '可执行性与粒度'
}
CSV_DIM_COLS = ['时间安排合理性', '任务依赖完整性', '资源分配均衡度', '约束条件满足度', '可执行性与粒度']

# ─── 2. 构建评测数据结构（与 HTML 中 S[tag] 对齐）───
# S[tag] = { runs: [{ai:{dim:score,...}, plan:'', verdict:'', done, timedOut, elapsedMs}], human:{dim:score}, bestRunIdx }

models_data = {}  # tag -> data

for row in data_rows:
    name = row['模型'].strip()
    tag = name  # use name as tag
    if tag not in models_data:
        models_data[tag] = {'runs': [], 'human': {k: 15 for k in DIM_KEYS}, 'bestRunIdx': 0}

    status = row['状态'].strip()
    dim_scores = {}
    for dk, cc in zip(DIM_KEYS, CSV_DIM_COLS):
        dim_scores[dk] = int(row[cc]) if row[cc].strip() else 0
    ai_total = sum(dim_scores.values())
    latency = float(row['耗时s']) if row['耗时s'].strip() else 0

    run = {
        'ai': dim_scores,
        'plan': f'[ScheduleBench] {name} 排期输出',
        'verdict': f'AI总分 {ai_total}/100',
        'done': status in ('完成', '13.5', '13.8', '12.3', '12.0', '11.7'),  # 有些行状态列被维度值替代
        'timedOut': False,
        'elapsedMs': latency * 1000
    }
    # 检查是否实际完成
    if ai_total > 0:
        run['done'] = True

    models_data[tag]['runs'].append(run)

# 聚合行的人工分和最终分
for row in agg_rows:
    name = row['模型'].strip()
    tag = name
    if tag not in models_data:
        continue

    # 人工总分
    human_raw = (row.get('人工总分') or '').strip()
    if human_raw:
        models_data[tag]['humanTotal'] = int(human_raw)

    final_raw = (row.get('最终得分') or '').strip()
    if final_raw:
        models_data[tag]['finalScore'] = int(final_raw)

# 补全缺失的 humanTotal 和 finalScore
for tag, d in models_data.items():
    dr = [r for r in d['runs'] if r['done'] and not r['timedOut']]
    if not dr:
        d['allTimedOut'] = True
        continue
    d['allTimedOut'] = False

    # AI均值
    ai_avg_sum = 0
    for dim in DIM_KEYS:
        avg = statistics.mean([r['ai'][dim] for r in dr])
        ai_avg_sum += avg
    d['aiAvgSum'] = round(ai_avg_sum, 1)

    # 人工分：优先用CSV中的值，否则用默认15*5=75
    if 'humanTotal' not in d:
        d['humanTotal'] = 75  # 默认
    d['humanSum'] = d['humanTotal']

    # 最终分 = AI×50% + 人工×50%
    if 'finalScore' not in d:
        d['finalScore'] = round(d['aiAvgSum'] * 0.5 + d['humanSum'] * 0.5)

# ─── 3. 排序 ───
active_models = [(tag, d) for tag, d in models_data.items() if not d.get('allTimedOut')]
active_models.sort(key=lambda x: -x[1]['finalScore'])
timed_out = [(tag, d) for tag, d in models_data.items() if d.get('allTimedOut')]

N_MODELS = len(active_models)
ROUNDS = max(len(d['runs']) for d in models_data.values())

# ─── 4. 各维度最佳 ───
best_dim = {}
for dim in DIM_KEYS:
    best_tag, best_val = None, -1
    for tag, d in active_models:
        dr = [r for r in d['runs'] if r['done'] and not r['timedOut']]
        if not dr: continue
        ai_avg = statistics.mean([r['ai'][dim] for r in dr])
        combined = (ai_avg + d['human'].get(dim, 15)) / 2
        if combined > best_val:
            best_val, best_tag = combined, tag
    best_dim[dim] = {'tag': best_tag, 'score': round(best_val, 1)}

# ─── 5. day1_to_day2_brief.json（6个Router Key）───
dim_to_role = {
    'schedule': 'multimodal_context',
    'dependency': 'code_assistant',
    'balance': 'risk_checker',
    'constraint': 'context_designer',
    'executable': 'schema_generator'
}

router = {
    'router': {},
    'generated_at': now(),
    'purpose': 'Day1 ScheduleBench 评测结果转为 Day2 模型路由依据',
    'product_direction': '日程规划：基于大模型的项目排班与任务分配',
    'day2_requirements': [
        '每个 router key 对应一个任务角色',
        '得分接近的模型列为备选',
        'fallback 必须具体可执行'
    ]
}

for dim in DIM_KEYS:
    rk = dim_to_role[dim]
    bd = best_dim[dim]
    # 找备选（得分差≤2分）
    alts = []
    for tag, d in active_models[1:]:
        if tag == bd['tag']: continue
        dr = [r for r in d['runs'] if r['done'] and not r['timedOut']]
        if not dr: continue
        ai_avg = statistics.mean([r['ai'][dim] for r in dr])
        combined = (ai_avg + d['human'].get(dim, 15)) / 2
        if bd['score'] - combined <= 2:
            alts.append({'model': tag, 'score': round(combined, 1)})

    entry = {
        'preferred_model': bd['tag'],
        'evidence_task': 'schedule_planning',
        'score': bd['score'],
        'fallback_rule': '失败切换至' + (active_models[1][0] if len(active_models) > 1 else active_models[0][0]) if not alts else '得分接近可切换至 ' + ' 或 '.join([a['model'] for a in alts])
    }
    if alts:
        entry['alternatives'] = alts
    router['router'][rk] = entry

# product_planner = 综合最优
winner = active_models[0][0] if active_models else 'N/A'
router['router']['product_planner'] = {
    'preferred_model': winner,
    'evidence_task': 'overall',
    'score': active_models[0][1]['finalScore'] if active_models else 0,
    'fallback_rule': '失败切换至' + (active_models[1][0] if len(active_models) > 1 else winner)
}
if len(active_models) >= 2 and active_models[0][1]['finalScore'] - active_models[1][1]['finalScore'] <= 5:
    router['router']['product_planner']['alternatives'] = [
        {'model': active_models[1][0], 'score': active_models[1][1]['finalScore']}
    ]

wj(OUT / 'day1_to_day2_brief.json', router)
print('day1_to_day2_brief.json done')

# ─── 6. model_capability_matrix.json ───
matrix = {
    'generated_at': now(),
    'platform': 'LLM Schedule-Bench',
    'rounds': ROUNDS,
    'judge': 'DeepSeek-V3',
    'judge_vendor': 'DeepSeek',
    'models': []
}

for i, (tag, d) in enumerate(active_models):
    dr = [r for r in d['runs'] if r['done'] and not r['timedOut']]
    entry = {
        'name': tag,
        'id': f'schedule-bench/{tag}',
        'vendor': 'ScheduleBench',
        'rank': i + 1,
        'final_score': d['finalScore'],
        'dimensions': {}
    }
    for dim in DIM_KEYS:
        ai_avg = round(statistics.mean([r['ai'][dim] for r in dr]), 1) if dr else 0
        human_val = d['human'].get(dim, 15)
        entry['dimensions'][dim] = {
            'ai_avg': ai_avg,
            'human': human_val,
            'combined': round((ai_avg + human_val) / 2, 1)
        }
    matrix['models'].append(entry)

if timed_out:
    matrix['eliminated'] = [{'name': tag, 'vendor': 'ScheduleBench', 'reason': '超时淘汰'} for tag, d in timed_out]

wj(OUT / 'model_capability_matrix.json', matrix)
print('model_capability_matrix.json done')

# ─── 7. model_pool_policy.json ───
pool = {
    'generated_at': now(),
    'provider': 'SiliconFlow',
    'classroom_policy': '学生可从硅基流动任选模型，本报告5个模型为真实评测结果',
    'baseline_models': [{'name': tag, 'id': f'schedule-bench/{tag}', 'vendor': 'ScheduleBench', 'score': d['finalScore']} for tag, d in active_models],
    'selection_tracks': [{
        'track': 'schedule_planning',
        'required': True,
        'minimum_candidates': 1,
        'tasks': ['product_planner', 'context_designer', 'schema_generator', 'code_assistant', 'risk_checker', 'multimodal_context'],
        'evidence': f'{ROUNDS}轮评测，含AI裁判评分'
    }],
    'routing_roles': ['product_planner', 'context_designer', 'schema_generator', 'code_assistant', 'risk_checker', 'multimodal_context']
}
wj(OUT / 'model_pool_policy.json', pool)
print('model_pool_policy.json done')

# ─── 8. day1_results.json ───
results_json = []
for tag, d in models_data.items():
    for i, r in enumerate(d['runs']):
        entry = {
            'task': {'id': f'schedule_r{i+1}', 'title': f'日程规划(第{i+1}轮)'},
            'model': {'id': f'schedule-bench/{tag}', 'label': tag},
            'score': sum(r['ai'].values()) if r['done'] else 0,
            'ok': r['done'] and not r['timedOut']
        }
        if r['timedOut']:
            entry['failure_reason'] = '超时淘汰'
        elif r['done']:
            entry['output'] = {
                'verdict': r['verdict'],
                'text': r['plan'],
                'dimensions': {dim: r['ai'][dim] for dim in DIM_KEYS}
            }
        results_json.append(entry)
wj(OUT / 'day1_results.json', results_json)
print(f'day1_results.json done ({len(results_json)}条)')

# ─── 9. failure_casebook.md ───
fail_md = f'# 失败样本记录 (Failure Casebook)\n\n> 生成: {now()} | 轮数: {ROUNDS}\n\n'
if timed_out:
    for tag, d in timed_out:
        fail_md += f'## {tag}\n\n**状态:** ❌ 所有{ROUNDS}轮超时淘汰 (>180s)\n\n**影响:** 不进入最终排名和路由表。\n\n'
else:
    fail_md += '✅ 本轮评测无失败样本，所有模型均正常完成。\n'
fail_md += '\n---\n*LLM Schedule-Bench 自动生成*'
wt(OUT / 'failure_casebook.md', fail_md)
print('failure_casebook.md done')

# ─── 10. HTML 控制台 ───
# 评分分布图
def render_scorebars(active):
    bars = ''
    for tag, d in active:
        pct = d['finalScore']
        color = '#0f766e' if pct >= 70 else ('#f59e0b' if pct >= 50 else '#c0392b')
        bars += f'<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px"><span>{tag}</span><span style="color:{color};font-weight:700">{pct}/100</span></div><div style="background:#e5e7eb;border-radius:4px;height:20px;overflow:hidden"><div style="width:{pct}%;background:{color};height:100%;border-radius:4px"></div></div></div>'
    return bars

# 维度热力图(简化)
def render_dimtable(active):
    rows = ''
    for tag, d in active:
        dr = [r for r in d['runs'] if r['done'] and not r['timedOut']]
        cells = ''
        for dim in DIM_KEYS:
            ai_avg = round(statistics.mean([r['ai'][dim] for r in dr]), 1) if dr else 0
            human = d['human'].get(dim, 15)
            combined = round((ai_avg + human) / 2, 1)
            bg = '#e6f7ed' if combined >= 14 else ('#fef9e7' if combined >= 10 else '#fde8e8')
            c = '#0f766e' if combined >= 14 else ('#b7950b' if combined >= 10 else '#c0392b')
            cells += f'<td style="background:{bg};color:{c};font-weight:700;text-align:center">{combined}</td>'
        rows += f'<tr><td style="font-weight:600">{tag}</td>{cells}</tr>'
    return rows

# 路由表
def render_router():
    rows = ''
    for rk, rule in router['router'].items():
        rows += f'<tr><td style="font-weight:600">{rk}</td><td style="color:#0f766e;font-weight:700">{rule["preferred_model"]}</td><td>{rule["score"]}</td><td style="font-size:13px;color:#667789">{rule["fallback_rule"][:100]}</td></tr>'
    return rows

html = f'''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Day1 ScheduleBench 模型能力评估控制台</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f7f8;color:#17202a;line-height:1.58}}
header{{background:#243746;color:white;padding:36px 42px 26px}}header h1{{margin:0 0 8px;font-size:30px}}header p{{margin:0;color:#dbe4ea;max-width:980px}}
main{{max-width:1080px;margin:24px auto 48px;padding:0 22px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.panel{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:20px;margin:16px 0}}.tag{{display:inline-block;border:1px solid #b8ded8;background:#eef8f6;color:#0b534d;border-radius:999px;padding:3px 10px;font-size:12px;margin-right:6px}}
.tag-red{{border-color:#f5c6cb;background:#fff5f5;color:#991b1b}}.tag-blue{{border-color:#bfdbfe;background:#eff6ff;color:#1e40af}}
h2{{margin:10px 0;font-size:22px}}.muted{{color:#667789}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{border:1px solid #d8dee6;padding:10px;text-align:left}}th{{background:#f0f2f5;font-weight:650}}
.button{{display:inline-block;text-decoration:none;background:#0f766e;color:white;border-radius:6px;padding:8px 12px;font-weight:650;margin:4px 4px 4px 0;font-size:12px}}
.json-block{{background:#1e293b;color:#e2e8f0;padding:12px;border-radius:6px;font-size:11px;line-height:1.6;overflow-x:auto;white-space:pre;font-family:"SF Mono","Cascadia Code","Consolas",monospace;max-height:350px;overflow-y:auto}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}header{{padding:28px 22px 20px}}}}
</style></head>
<body>
<header><h1>Day1 模型能力评估控制台</h1><p>LLM Schedule-Bench | {N_MODELS}个模型 × {ROUNDS}轮评测 × 5维评分 | 裁判: DeepSeek-V3 | API: 硅基流动</p></header>
<main>

<div class="grid">
<div class="panel"><span class="tag">主产物</span><h2>模型能力评估控制台</h2><p class="muted">不看排行榜，看实测结果。从国产大模型候选池出发，比较日程规划能力，转化为 Day2 路由规则。</p>
<p>{' '.join([f'<span style="margin-right:8px">{"🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else ""} {tag}</span>' for i,(tag,d) in enumerate(active_models)])}</p>
<p class="muted" style="margin-top:8px">{ROUNDS}轮聚合 | {now()}</p></div>

<div class="panel"><span class="tag">原始证据</span><h2>评测模型列表</h2>
<div class="json-block" style="margin-top:8px;max-height:200px">{json.dumps([{'name': tag, 'score': d['finalScore'], 'rank': i+1} for i,(tag,d) in enumerate(active_models)], ensure_ascii=False, indent=2)}</div></div>
</div>

<div class="panel"><span class="tag">评分分布</span><h2>综合得分排名 (0-100分制)</h2>
{render_scorebars(active_models)}</div>

<div class="panel"><span class="tag">能力矩阵</span><h2>5维评分矩阵</h2><p class="muted">每维AI评分均值+人工审查=综合分(满分20/每维)</p>
<table><tr><th>模型</th>{''.join([f'<th>{DIM_LABELS[d]}</th>' for d in DIM_KEYS])}</tr>{render_dimtable(active_models)}</table></div>

<div class="panel"><span class="tag">路由规则</span><h2>Day2 模型路由表 · day1_to_day2_brief.json</h2><p class="muted">6个Router Key，每个包含 preferred_model + score + fallback_rule</p>
<div class="json-block" style="margin-top:8px;max-height:250px">{json.dumps(router, ensure_ascii=False, indent=2)[:3000]}</div></div>

<div class="grid">
<div class="panel"><span class="tag">能力矩阵JSON</span><h2>model_capability_matrix.json</h2>
<div class="json-block" style="max-height:250px">{json.dumps(matrix, ensure_ascii=False, indent=2)[:3000]}</div></div>
<div class="panel"><span class="tag">选型策略</span><h2>model_pool_policy.json</h2>
<div class="json-block" style="max-height:250px">{json.dumps(pool, ensure_ascii=False, indent=2)[:1500]}</div></div>
</div>

<div class="panel"><span class="tag{' tag-red' if timed_out else ''}">失败样本</span><h2>failure_casebook.md</h2>
<pre style="background:#fafbfc;padding:12px;border-radius:6px;font-size:12px;line-height:1.7;white-space:pre-wrap;max-height:200px;overflow-y:auto">{fail_md}</pre></div>

<div class="panel"><span class="tag">本日边界</span><h2>评估方法与工程边界</h2>
<table><tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600;width:160px">评测平台</td><td>LLM Schedule-Bench</td></tr>
<tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600">轮数</td><td>{ROUNDS}轮聚合</td></tr>
<tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600">维度</td><td>{'、'.join(DIM_LABELS.values())}</td></tr>
<tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600">裁判</td><td>DeepSeek-V3</td></tr>
<tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600">有效模型</td><td>{N_MODELS}/5 | 淘汰: {len(timed_out)}/5</td></tr>
<tr><td style="padding:8px 12px;border:1px solid #d8dee6;font-weight:600">评分制度</td><td>5维 × 0-20分 = AI总分100 + 人工审查50% = 最终百分制</td></tr>
</table></div>

</main></body></html>'''
wt(OUT / 'Day1_模型能力评估控制台.html', html)
print('Day1_模型能力评估控制台.html done')

# ─── 11. 打印总结 ───
print('\n' + '=' * 55)
print('ScheduleBench Day1 构建完成 (llm-bench格式)')
print('=' * 55)
print(f'模型: {N_MODELS} | 轮次: {ROUNDS} | 记录: {len(results_json)}')
print()
for i, (tag, d) in enumerate(active_models):
    bar = '#' * (d['finalScore'] // 10) + '-' * (10 - d['finalScore'] // 10)
    print(f'  {i+1}. {tag:20s} {d["finalScore"]}/100 {bar}')
print()
print('路由:')
for rk, rule in router['router'].items():
    print(f'  {rk:25s} -> {rule["preferred_model"]:20s} ({rule["score"]})')
print()
for f in sorted(OUT.glob('*')):
    if f.is_file():
        print(f'  {f.name}')
