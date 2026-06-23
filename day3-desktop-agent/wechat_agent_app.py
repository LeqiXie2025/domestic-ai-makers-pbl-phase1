"""
Day3 微信风格桌面对话窗口 — 完整版
==================================
独立的原生 Windows 桌面应用。

功能：
  剪贴板自动监控    — 每3秒检测，有聊天内容自动提示
  文件输入            — 监控 wechat_input/ 文件夹
  智能排程引擎        — LLM解析 → 任务分配+会议+交付物+风险
  Workspace 写入     — 所有产物落入 outputs/scheduling_workspace/
  Trace 记录          — 每步操作写入 trace_log
  仪表盘自动生成      — 生成 Scheduling_Agent控制台.html
  对话导出            — 保存聊天记录为 .txt
  配置面板            — 查看 API 状态、模型信息

用法：
  python wechat_agent_app.py           # 正常启动
  pythonw wechat_agent_app.py          # 无终端窗口
  python wechat_agent_app.py --mock    # 离线模式
"""

import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 环境 & 配置
# ============================================================
PACKAGE_ROOT = Path(__file__).resolve().parent
ENV_PATH = PACKAGE_ROOT.parent / "resources" / "local_siliconflow.env"
CONFIG_PATH = PACKAGE_ROOT / ".project_config.json"

# 运行时设置（由项目选择器设置）
PROJECT_ROOT: Path = Path.home() / "Desktop" / "小组作业"
WORKSPACE: Path = PROJECT_ROOT / "排程结果"
INPUT_DIR: Path = PROJECT_ROOT / "聊天记录"
TRACE_PATH: Path = PROJECT_ROOT / "运行记录" / "trace_log.jsonl"
DASHBOARD_PATH: Path = PROJECT_ROOT / "排程结果" / "排程面板.html"

MOCK_LLM = "--mock" in sys.argv
MODEL_NAME = "deepseek-ai/DeepSeek-V4-Flash"

def load_env():
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env()
if MOCK_LLM:
    os.environ["MOCK_LLM"] = "1"

API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
MODEL_NAME = os.environ.get("MODEL_B", MODEL_NAME)

# ── Windows 剪贴板 ──
try:
    import win32clipboard
    import win32con
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

# ── Tkinter ──
import tkinter as tk
from tkinter import font as tkfont, messagebox, scrolledtext, ttk

# ============================================================
# 工具函数
# ============================================================
def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")

def now_time() -> str:
    return datetime.now().strftime("%H:%M")

def short(text: str, n: int = 120) -> str:
    t = " ".join((text or "").strip().split())
    return t if len(t) <= n else t[:n-1] + "…"

def append_trace(event_type: str, payload: Dict):
    try:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": now_ts(), "type": event_type, "payload": payload},
                ensure_ascii=False) + "\n")
    except Exception:
        pass

def read_clipboard() -> Optional[str]:
    if not HAS_CLIP:
        return None
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data if data and len(data) > 10 else None
        win32clipboard.CloseClipboard()
    except Exception:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    return None

def scan_input_dir() -> List[Path]:
    if not INPUT_DIR.exists():
        return []
    return sorted(
        f for f in INPUT_DIR.glob("*")
        if f.is_file() and f.suffix.lower() in {".txt", ".md"}
        and not f.name.startswith("_processed_")
    )

def safe_file_op(path: Path) -> Path:
    """确保文件操作不超出项目范围."""
    resolved = path.resolve()
    boundary = PROJECT_ROOT.resolve()
    if boundary not in resolved.parents and resolved != boundary:
        raise PermissionError(f"拒绝访问：{path} 不在 {PROJECT_ROOT} 内")
    return resolved

def set_project(path: Path):
    """切换工作项目."""
    global PROJECT_ROOT, WORKSPACE, INPUT_DIR, TRACE_PATH, DASHBOARD_PATH
    PROJECT_ROOT = Path(path).resolve()
    WORKSPACE = PROJECT_ROOT / "排程结果"
    INPUT_DIR = PROJECT_ROOT / "聊天记录"
    TRACE_PATH = PROJECT_ROOT / "运行记录" / "trace_log.jsonl"
    DASHBOARD_PATH = PROJECT_ROOT / "排程结果" / "排程面板.html"
    # 确保子目录存在
    for d in [INPUT_DIR, WORKSPACE, PROJECT_ROOT / "运行记录"]:
        d.mkdir(parents=True, exist_ok=True)
    # 保存配置
    CONFIG_PATH.write_text(json.dumps({"project": str(PROJECT_ROOT)}), encoding="utf-8")

def load_last_project() -> Optional[Path]:
    """读取上次选择的项目."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            p = Path(data.get("project", ""))
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    return None

def create_new_project(parent_dir: Path, name: str) -> Path:
    """创建新项目文件夹（含标准子目录）."""
    proj = (parent_dir / name).resolve()
    for sub in ["聊天记录", "排程结果", "运行记录"]:
        (proj / sub).mkdir(parents=True, exist_ok=True)
    return proj

def scan_project_folders(parent_dir: Path) -> List[Path]:
    """扫描父目录下已有的项目文件夹（含聊天记录/排程结果/运行记录之一的才算）."""
    if not parent_dir.exists():
        return []
    projects = []
    for d in sorted(parent_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        subs = {p.name for p in d.iterdir() if p.is_dir()}
        if "聊天记录" in subs or "排程结果" in subs or "运行记录" in subs:
            projects.append(d)
    return projects

# ============================================================
# LLM 引擎
# ============================================================
def call_llm_api(messages: List[Dict], max_tokens: int = 2000) -> Tuple[str, Optional[str]]:
    """调用 API。返回 (content, error)."""
    if MOCK_LLM or not API_KEY:
        return "", "mock_mode"

    try:
        import requests
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"].get("content", "").strip()
        return content, None
    except Exception as e:
        return "", str(e)

def call_llm_chat(messages: List[Dict]) -> str:
    content, err = call_llm_api(messages, max_tokens=2000)
    if err == "mock_mode":
        return mock_chat_reply(messages[-1]["content"] if messages else "")
    if err:
        return f"⚠️ API 调用失败：{err}\n\n{mock_chat_reply(messages[-1]['content'] if messages else '')}"
    return content

def call_llm_schedule(raw_input: str) -> str:
    """专用排程调用 — 强调时间线和会议记录."""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""你是小组项目排程专家。请从以下聊天/输入中提取所有信息，生成完整排程方案。

当前日期：{today}

## 原始输入
{raw_input.strip()[:8000]}

严格按以下格式输出（每个 ## 都不能缺）：

## 📋 信息提取
- 组员列表（姓名、技能、偏好、空闲时间）
- 任务列表（名称、工作量、依赖关系）
- 时间约束（各人空闲/忙碌、整体截止日期）

## 🕐 项目时间线
以时间轴形式列出关键节点（从今天到截止日），每个节点包括：
- 日期和时间
- 节点类型（会议 / 提交截止 / 里程碑）
- 具体内容
示例：
| 日期 | 时间 | 类型 | 内容 | 参与人 |
|------|------|------|------|--------|
| 6月24日 周一 | 20:00 | 📅 启动会 | 确认分工+排期 | 全员 |
| 6月26日 周三 | 17:00 | 📦 提交 | 市场调研报告 | 张三、赵六 |

## 👥 任务分配
表格：| 任务名称 | 负责人 | 协助人 | 工时(h) | 开始日期 | 截止日期 | 优先级 |

## 📅 会议记录
每次会议单独列出：
**第1次 — 启动会**
- 时间：（具体日期+时间段）
- 形式：（线上/线下）
- 议程：
  1. ...
  2. ...
- 本次需提交：（会前要准备好的东西）
- 会后待办：（会议产生的行动项）

**第2次 — 中期同步**
- 时间：...
（至少列出2次会议）

## 📦 交付物清单
表格：| 交付物 | 负责人 | 格式 | 提交日期 | 提交给谁 | 验收标准 |

## ⚠️ 风险与备注
- 风险点 + 对应负责人
- 需确认事项"""

    messages = [
        {"role": "system", "content": "你是小组排程专家。输出结构化Markdown。用中文。精确到具体日期。考虑技能匹配和时间约束。每条会议记录都有时间和议程。"},
        {"role": "user", "content": prompt},
    ]
    content, err = call_llm_api(messages, max_tokens=3200)
    if err == "mock_mode":
        return mock_schedule_reply(raw_input)
    if err:
        return f"⚠️ API 调用失败：{err}\n\n{mock_schedule_reply(raw_input)}"
    return content

# ============================================================
# Mock / 兜底回复
# ============================================================
def mock_chat_reply(msg: str) -> str:
    m = msg.lower()
    if is_schedule_intent(msg):
        return mock_schedule_reply(msg)
    if any(k in m for k in ["agent", "tool use", "rag", "trace"]):
        return ("🔧 **Agent** = 自主决策AI（思考→行动→观察→循环）\n"
                "🛠️ **Tool Use** = list_files / read_file / search_workspace / write_file\n"
                "📚 **RAG** = 切chunk→建索引→检索top-k→LLM生成→保留来源\n"
                "📝 **Trace** = 飞行记录器，每步工具调用都记录在 trace_log.jsonl\n\n"
                "（离线模式。接入 API Key 后获得完整智能。）")
    if any(k in m for k in ["day", "课程", "phase"]):
        return ("📅 **Phase1 四天结构**\n"
                "Day1 模型评估 → Day2 能力定义 → Day3 Agent Core → Day4 设备网关\n"
                "Day3 是核心：把前两天的能力变成真正能跑的程序。")
    return f"收到！💡\n• 粘贴小组聊天 → 生成排程方案\n• 问 Agent/RAG/Tool Use\n• 问 Phase1 课程\n\n（离线模式）"

def mock_schedule_reply(raw: str) -> str:
    names = list(dict.fromkeys(re.findall(r"([一-鿿]{2,3})(?:[：:说])", raw)))
    if not names:
        names = ["组员A", "组员B", "组员C", "组员D"]
    tasks = re.findall(r"[A-E][.、]\s*([^（\n]+)", raw)
    if not tasks:
        tasks = ["需求分析", "原型设计", "前端开发", "后端开发", "答辩准备"]

    today = datetime.now()
    d1 = today.strftime("%m/%d")
    d3 = (today + timedelta(days=2)).strftime("%m/%d")
    d5 = (today + timedelta(days=4)).strftime("%m/%d")
    d7 = (today + timedelta(days=6)).strftime("%m/%d")

    task_rows = ""
    for i, t in enumerate(tasks):
        o = names[i % len(names)]
        h = names[(i+1) % len(names)] if len(names) > 1 else "-"
        start_d = [d1, d1, d3, d3, d5][i] if i < 5 else d1
        end_d = [d3, d3, d5, d5, d7][i] if i < 5 else d7
        task_rows += f"| {t} | {o} | {h} | {(i+1)*5}h | {start_d} | {end_d} | P{i%3} |\n"

    # Timeline rows
    tl_rows = (
        f"| {d1} | 20:00 | 📅 启动会 | 确认分工+排期+环境搭建 | 全员 |\n"
        f"| {d3} | 17:00 | 📦 提交 | {tasks[0] if tasks else '任务A'}完成 | {names[0]} |\n"
        f"| {d3} | 21:00 | 📅 同步会 | 进度检查+阻塞讨论 | 全员 |\n"
        f"| {d5} | 17:00 | 📦 提交 | {tasks[2] if len(tasks)>2 else '开发'}初版 | {names[2] if len(names)>2 else names[0]} |\n"
        f"| {d7} | 16:00 | 📅 验收会 | 最终验收+答辩演练 | 全员 |\n"
        f"| {d7} | 17:00 | 📦 提交 | 全部交付物 | 全员 |\n"
    )

    return f"""## 📋 信息提取
- 识别到 {len(names)} 名组员：{'、'.join(names)}
- 识别到 {len(tasks)} 个任务
- 项目周期：{d1} ~ {d7}

## 🕐 项目时间线
| 日期 | 时间 | 类型 | 内容 | 参与人 |
|------|------|------|------|--------|
{tl_rows}
## 👥 任务分配
| 任务名称 | 负责人 | 协助人 | 工时(h) | 开始日期 | 截止日期 | 优先级 |
|----------|--------|--------|---------|----------|----------|--------|
{task_rows}
## 📅 会议记录
**第1次 — 启动会**
- 时间：{d1} 周一 20:00-20:45
- 形式：线上腾讯会议
- 议程：
  1. 确认任务分配和各自职责
  2. 同步各人空闲时间
  3. 确定协作工具（GitHub/Figma/腾讯文档）
- 本次需提交：无（会前准备好个人技能介绍）
- 会后待办：各人开始执行分配的任务

**第2次 — 中期同步会**
- 时间：{d3} 周三 21:00-21:20
- 形式：线上快速站会
- 议程：
  1. 各人进度同步（3分钟/人）
  2. 阻塞问题讨论
  3. 是否需要调整分工
- 本次需提交：{tasks[0] if tasks else '任务A'} 已完成
- 会后待办：继续推进开发任务

**第3次 — 最终验收会**
- 时间：{d7} 周五 16:00-16:30
- 形式：线上
- 议程：
  1. 全部交付物检查
  2. 答辩PPT预演
  3. 最终提交确认
- 本次需提交：全部交付物
- 会后待办：根据反馈做最后修改

## 📦 交付物清单
| 交付物 | 负责人 | 格式 | 提交日期 | 提交给谁 | 验收标准 |
|--------|--------|------|----------|----------|----------|
| 需求文档 | {names[0]} | Markdown | {d3} | 全员 | 覆盖所有需求点 |
| 原型稿 | {names[1] if len(names)>1 else names[0]} | Figma链接 | {d3} | 组长 | 主要页面完成 |
| 核心代码 | {names[2] if len(names)>2 else names[0]} | GitHub PR | {d5} | 全员Review | 功能可用 |
| 答辩PPT | {names[-1]} | PPT | {d7} | 全员 | 覆盖项目全流程 |

## ⚠️ 风险与备注
- 需确认各人真实空闲时间（当前为推测）
- 依赖链：UI原型→前端开发，后端开发→联调
- 预留缓冲：周五上午作为缓冲时间
> 💡 离线兜底模式。接入 API 可获基于真实日期的精准排程。"""

# ============================================================
# 排程意图检测
# ============================================================
def is_schedule_intent(msg: str) -> bool:
    m = msg.lower()
    explicit = ["排程", "安排任务", "分配任务", "帮我排", "生成安排", "整理任务"]
    if any(k in m for k in explicit):
        return True
    if len(msg) > 150:
        content_kw = ["任务", "开会", "截止", "ddl", "谁来做", "项目", "分工",
                       "分配", "小组", "交付", "空闲时间", "我可以", "我擅长"]
        if sum(1 for k in content_kw if k in m) >= 3:
            return True
    if len(msg) > 300:
        return True  # 长文本很可能是聊天记录
    return False

# ============================================================
# Workspace 保存
# ============================================================
def _extract_project_name(raw_input: str) -> str:
    """从输入中提取简短项目名."""
    # 尝试匹配常见模式
    patterns = [
        r'(?:项目|课题|作业|大作业)[：:\s]*[「「]?(.{2,20}?)[」」]?(?:[，。,\.\s]|$])?',
        r'(?:第[一二三四五六七八九十\d]+[周次])\s*(?:项目|任务)?[：:\s]*(.{2,20}?)(?:[，。,\.\s]|$)',
        r'【(.{2,20}?)】',
    ]
    for pat in patterns:
        m = re.search(pat, raw_input)
        if m:
            name = m.group(1).strip()
            if name and len(name) <= 20:
                return name
    # fallback: 用前几个字
    first_line = raw_input.strip().split("\n")[0][:30]
    first_line = re.sub(r'[【】\[\]（）()「」""]', '', first_line).strip()
    return first_line if len(first_line) <= 20 else first_line[:20]

def save_schedule_to_workspace(raw_input: str, generated: str, source: str = "wechat_app"):
    ts = now_ts()
    project = _extract_project_name(raw_input)
    # 清理非法 Windows 文件名字符
    project = re.sub(r'[<>:\"/\\|?*]', '', project)[:30]
    date_str = datetime.now().strftime("%m%d")
    dirname = f"{date_str}_{project}" if project else f"{date_str}_排程"
    session_dir = WORKSPACE / dirname
    session_dir.mkdir(parents=True, exist_ok=True)

    # 原始输入
    (session_dir / "原始输入.txt").write_text(raw_input, encoding="utf-8")

    # 按 ## 拆分到扁平文件
    sections: Dict[str, str] = {}
    cur_title = ""
    cur_lines: List[str] = []
    for line in generated.splitlines():
        if line.startswith("## "):
            if cur_title and cur_lines:
                sections[cur_title] = "\n".join(cur_lines).strip()
            cur_title = line[3:].strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_title and cur_lines:
        sections[cur_title] = "\n".join(cur_lines).strip()

    # 扁平映射：一个 section → 一个文件
    flat_mapping = {
        "🕐 项目时间线": "时间线.md",
        "👥 任务分配": "任务分配.md",
        "📅 会议记录": "会议记录.md",
        "📅 会议安排": "会议记录.md",
        "📦 交付物清单": "交付物清单.md",
        "⚠️ 风险与备注": "风险备注.md",
        "📋 信息提取": "信息提取.md",
        # 无 emoji fallback
        "任务分配": "任务分配.md",
        "会议记录": "会议记录.md",
        "会议安排": "会议记录.md",
        "交付物清单": "交付物清单.md",
        "风险与备注": "风险备注.md",
    }
    written = set()
    for title, filename in flat_mapping.items():
        if filename in written:
            continue
        content = sections.get(title, "")
        if not content:
            clean = title.split(" ", 1)[-1] if " " in title else title
            for k, v in sections.items():
                if clean in k:
                    content = v
                    break
        if content:
            (session_dir / filename).write_text(f"# {title}\n\n{content}", encoding="utf-8")
            written.add(filename)

    # Trace + Word + 面板
    append_trace("schedule.generated", {"source": source, "project": dirname, "chars": len(generated)})
    docx_path = session_dir / "小组排程方案.docx"
    try:
        generate_docx(raw_input, generated, docx_path)
    except Exception:
        append_trace("schedule.docx_error", {"error": "generate_docx failed"})
    try:
        generate_dashboard(raw_input, generated, session_dir / "排程面板.html")
    except Exception:
        pass

    return {"ts": ts, "source": source, "dir": dirname}

# ============================================================
# 仪表盘生成
# ============================================================
def _count_table_rows(text: str) -> int:
    if not text:
        return 0
    pipe_pattern = re.compile(r'\|')
    return sum(1 for line in text.splitlines() if pipe_pattern.search(line) and not re.match(r'^\|\s*[-: ]+\|', line.strip()))


def generate_dashboard(raw_input: str, generated: str, output_path: Optional[Path] = None):
    try:
        from html import escape as hescape
        ts = now_ts()

        sections = {}
        cur_title = ""
        cur_lines = []
        for line in generated.splitlines():
            if line.startswith("## "):
                if cur_title and cur_lines:
                    sections[cur_title] = "\n".join(cur_lines).strip()
                cur_title = line[3:].strip()
                cur_lines = []
            else:
                cur_lines.append(line)
        if cur_title and cur_lines:
            sections[cur_title] = "\n".join(cur_lines).strip()

        mode_label = "API" if (not MOCK_LLM and API_KEY) else "离线"
        timeline_text = sections.get("🕐 项目时间线", "")
        meetings_text = sections.get("📅 会议记录", "")
        tasks_text = sections.get("👥 任务分配", "")
        deliverables_text = sections.get("📦 交付物清单", "")
        risks_text = sections.get("⚠️ 风险与备注", "")

        # ── 解析时间线表格为可视化节点 ──
        timeline_nodes = _parse_timeline_table(timeline_text)

        # ── 构建 HTML ──
        html = f"""<!doctype html><html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>小组排程面板 · 时间线</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.58}}
header{{background:linear-gradient(135deg,#0c4a6e,#0f766e);color:white;padding:24px 36px}} h1{{margin:0;font-size:24px}} header p{{margin:4px 0 0;opacity:.75;font-size:13px}}
main{{max-width:1000px;margin:20px auto 48px;padding:0 20px}}
.panel{{background:white;border-radius:12px;padding:22px;margin:16px 0;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
h2{{font-size:18px;margin:0 0 14px;padding-bottom:8px;border-bottom:2px solid #0f766e;display:flex;align-items:center;gap:8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}} td,th{{border:1px solid #e5e7eb;padding:8px 10px;text-align:left}} th{{background:#f9fafb;font-weight:650}}
pre{{white-space:pre-wrap;background:#f8fafc;padding:14px;border-radius:8px;font-size:12px;line-height:1.7;overflow-x:auto}}

/* ── 时间线 ── */
.timeline{{position:relative;padding:10px 0 20px 36px}}
.timeline::before{{content:'';position:absolute;left:15px;top:0;bottom:0;width:3px;background:#e5e7eb;border-radius:2px}}
.tl-node{{position:relative;margin-bottom:20px;padding-left:10px}}
.tl-node::before{{content:'';position:absolute;left:-27px;top:10px;width:14px;height:14px;border-radius:50%;border:3px solid white;box-shadow:0 0 0 3px #0f766e;background:#0f766e;z-index:1}}
.tl-node.meeting::before{{background:#f59e0b;box-shadow:0 0 0 3px #f59e0b}}
.tl-node.deadline::before{{background:#ef4444;box-shadow:0 0 0 3px #ef4444}}
.tl-node.milestone::before{{background:#8b5cf6;box-shadow:0 0 0 3px #8b5cf6}}
.tl-date{{font-size:11px;color:#667789;font-weight:650;margin-bottom:2px}}
.tl-type{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;margin-bottom:4px}}
.tl-type.meeting{{background:#fef3c7;color:#92400e}}
.tl-type.deadline{{background:#fee2e2;color:#991b1b}}
.tl-type.milestone{{background:#ede9fe;color:#6d28d9}}
.tl-content{{font-size:13px;color:#1a1a2e;font-weight:600}}
.tl-people{{font-size:11px;color:#8899aa;margin-top:2px}}

/* ── 会议卡片 ── */
.meeting-card{{border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:12px 0;background:#fbfcfd}}
.meeting-card h3{{margin:0 0 8px;font-size:15px;color:#0f766e}}
.meeting-card .meta{{font-size:11px;color:#8899aa;margin-bottom:8px}}
.meeting-card ul{{margin:4px 0;padding-left:18px;font-size:12px;line-height:1.8}}
.meeting-card .submit-before{{background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:8px 12px;font-size:11px;margin-top:8px;color:#9a3412}}
.meeting-card .action-after{{background:#eef8f6;border:1px solid #b8ded8;border-radius:6px;padding:8px 12px;font-size:11px;margin-top:6px;color:#0b534d}}

/* KPI */
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}
.kpi{{background:white;border-radius:12px;padding:18px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.kpi-val{{font-size:30px;font-weight:760;color:#0f766e}} .kpi-lbl{{font-size:11px;color:#8899aa;margin-top:2px}}

@media(max-width:720px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}header{{padding:20px 22px}}}}
</style></head><body>
<header>
<h1>📋 小组排程面板</h1>
<p>生成时间：{hescape(ts)} ｜ 输入 {len(raw_input)} 字 ｜ {mode_label} 模式</p>
</header>
<main>

<div class="kpi-row">
<div class="kpi"><div class="kpi-val">{len(timeline_nodes)}</div><div class="kpi-lbl">时间线节点</div></div>
<div class="kpi"><div class="kpi-val">{len([1 for n in timeline_nodes if n[2]=='📅'])}</div><div class="kpi-lbl">会议</div></div>
<div class="kpi"><div class="kpi-val">{len([1 for n in timeline_nodes if n[2]=='📦'])}</div><div class="kpi-lbl">提交节点</div></div>
<div class="kpi"><div class="kpi-val">{_count_table_rows(tasks_text)}</div><div class="kpi-lbl">任务行</div></div>
</div>
"""

        # ── 🕐 时间线面板（核心） ──
        html += '<div class="panel"><h2>🕐 项目时间线</h2><div class="timeline">\n'
        if timeline_nodes:
            for date_str, time_str, node_type, content, people in timeline_nodes:
                css_class = ""
                if "📅" in node_type:
                    css_class = "meeting"
                elif "📦" in node_type:
                    css_class = "deadline"
                elif any(k in node_type for k in ["里程碑", "🚩"]):
                    css_class = "milestone"
                html += f"""<div class="tl-node {css_class}">
<div class="tl-date">{hescape(date_str)} {hescape(time_str)}</div>
<span class="tl-type {css_class}">{hescape(node_type)}</span>
<div class="tl-content">{hescape(content)}</div>
<div class="tl-people">{hescape(people)}</div>
</div>\n"""
        else:
            html += '<p style="color:#999">（运行真实排程后自动填充时间线）</p>'
        html += '</div></div>\n'

        # ── 📅 会议记录面板（每次开会的详细内容） ──
        if meetings_text:
            html += '<div class="panel"><h2>📅 会议记录</h2>\n'
            # 按 **第X次 分割
            meeting_blocks = re.split(r'\*\*第(\d+)次[—\-—](.+?)\*\*', meetings_text)
            # 得到的列表: [before, num1, title1, content1, num2, title2, content2, ...]
            i = 1
            processed = False
            while i < len(meeting_blocks) - 1:
                try:
                    num = meeting_blocks[i]
                    mt_title = meeting_blocks[i+1].strip()
                    mt_content = meeting_blocks[i+2] if i+2 < len(meeting_blocks) else ""
                    i += 3
                except (IndexError, ValueError):
                    i += 1
                    continue
                processed = True

                # 提取关键字段
                time_match = re.search(r'时间[：:]\s*(.+)', mt_content)
                form_match = re.search(r'形式[：:]\s*(.+)', mt_content)
                time_str_m = time_match.group(1).strip() if time_match else "待定"
                form_str = form_match.group(1).strip() if form_match else "线上"

                # 提取议程
                agenda_items = re.findall(r'\d+\.\s*(.+)', mt_content)

                # 提取需提交内容
                submit_match = re.search(r'本次需提交[：:]\s*(.+)', mt_content)
                submit_str = submit_match.group(1).strip() if submit_match else ""

                # 提取会后待办
                action_match = re.search(r'会后待办[：:]\s*(.+)', mt_content)
                action_str = action_match.group(1).strip() if action_match else ""

                html += f"""<div class="meeting-card">
<h3>📅 第{hescape(num)}次 — {hescape(mt_title)}</h3>
<div class="meta">🕐 {hescape(time_str_m)} ｜ 📍 {hescape(form_str)}</div>
"""
                if agenda_items:
                    html += "<ul>" + "".join(f"<li>{hescape(a)}</li>" for a in agenda_items[:6]) + "</ul>"
                if submit_str:
                    html += f'<div class="submit-before">📥 <b>本次需提交：</b>{hescape(submit_str)}</div>'
                if action_str:
                    html += f'<div class="action-after">✅ <b>会后待办：</b>{hescape(action_str)}</div>'
                html += '</div>\n'

            if not processed:
                html += f"<pre>{hescape(meetings_text[:3000])}</pre>"
            html += '</div>\n'

        # ── 👥 任务分配 ──
        if tasks_text:
            html += f'<div class="panel"><h2>👥 任务分配</h2><pre>{hescape(tasks_text[:5000])}</pre></div>\n'

        # ── 📦 交付物清单 ──
        if deliverables_text:
            html += f'<div class="panel"><h2>📦 交付物清单</h2><pre>{hescape(deliverables_text[:5000])}</pre></div>\n'

        # ── ⚠️ 风险 ──
        if risks_text:
            html += f'<div class="panel"><h2>⚠️ 风险与备注</h2><pre>{hescape(risks_text[:3000])}</pre></div>\n'

        html += f'<footer style="text-align:center;color:#999;font-size:11px;margin-top:32px">小组排程 Agent · Day3 Desktop · {hescape(ts)}</footer></main></body></html>'

        out = output_path or DASHBOARD_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        append_trace("dashboard.generated", {"path": str(out), "nodes": len(timeline_nodes)})
    except Exception as e:
        append_trace("dashboard.error", {"error": str(e)})


def _parse_timeline_table(text: str) -> List[Tuple[str, str, str, str, str]]:
    """从 Markdown 时间线表格提取节点列表."""
    nodes = []
    if not text:
        return nodes
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.split("|") if c.strip()]
        if len(cells) < 4:
            continue
        if cells[0] in ("日期", "------"):
            continue
        if any(k in cells[0] for k in ["日期", "---"]):
            continue
        date_str = cells[0] if len(cells) > 0 else ""
        time_str = cells[1] if len(cells) > 1 else ""
        node_type = cells[2] if len(cells) > 2 else ""
        content = cells[3] if len(cells) > 3 else ""
        people = cells[4] if len(cells) > 4 else ""
        nodes.append((date_str, time_str, node_type, content, people))
    return nodes


# ============================================================
# Word 文档生成
# ============================================================
def generate_docx(raw_input: str, generated: str, output_path: Path):
    """生成格式化的 Word 排程文档."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml.ns import qn

        doc = Document()

        # 页面设置
        section = doc.sections[0]
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

        # 样式
        style = doc.styles['Normal']
        style.font.name = '微软雅黑'
        style.font.size = Pt(10.5)
        style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

        # ── 标题 ──
        title = doc.add_heading('小组项目排程方案', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.size = Pt(22)

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(f'生成时间：{now_ts()}    模式：{"API" if not MOCK_LLM and API_KEY else "离线"}')
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x88, 0x99, 0xaa)

        doc.add_paragraph()

        # 解析 sections
        sections = {}
        cur_title = ""
        cur_lines = []
        for line in generated.splitlines():
            if line.startswith("## "):
                if cur_title and cur_lines:
                    sections[cur_title] = "\n".join(cur_lines).strip()
                cur_title = line[3:].strip()
                cur_lines = []
            else:
                cur_lines.append(line)
        if cur_title and cur_lines:
            sections[cur_title] = "\n".join(cur_lines).strip()

        # ── 1. 项目时间线 ──
        timeline_text = sections.get("🕐 项目时间线", "")
        doc.add_heading('一、项目时间线', level=1)
        nodes = _parse_timeline_table(timeline_text)
        if nodes:
            table = doc.add_table(rows=1, cols=5)
            table.style = 'Light Grid Accent 1'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            hdr = table.rows[0].cells
            for i, h in enumerate(["日期", "时间", "类型", "内容", "参与人"]):
                hdr[i].text = h
                for p in hdr[i].paragraphs:
                    for r in p.runs:
                        r.font.bold = True
                        r.font.size = Pt(9)
            for date_str, time_str, node_type, content, people in nodes:
                row = table.add_row().cells
                row[0].text = date_str
                row[1].text = time_str
                row[2].text = node_type
                row[3].text = content
                row[4].text = people
        else:
            doc.add_paragraph('（运行真实排程后自动填充）')

        doc.add_paragraph()

        # ── 2. 会议记录 ──
        meetings_text = sections.get("📅 会议记录", "")
        if meetings_text:
            doc.add_heading('二、会议记录', level=1)
            blocks = re.split(r'\*\*第(\d+)次[—\-—](.+?)\*\*', meetings_text)
            i = 1
            while i < len(blocks) - 1:
                try:
                    num = blocks[i]
                    mt_title = blocks[i+1].strip()
                    mt_content = blocks[i+2] if i+2 < len(blocks) else ""
                    i += 3
                except (IndexError, ValueError):
                    i += 1
                    continue

                doc.add_heading(f'第{num}次 — {mt_title}', level=2)

                time_match = re.search(r'时间[：:]\s*(.+)', mt_content)
                form_match = re.search(r'形式[：:]\s*(.+)', mt_content)
                if time_match:
                    doc.add_paragraph(f'时间：{time_match.group(1).strip()}')
                if form_match:
                    doc.add_paragraph(f'形式：{form_match.group(1).strip()}')

                # 议程
                agenda = re.findall(r'\d+\.\s*(.+)', mt_content)
                if agenda:
                    p = doc.add_paragraph('议程：')
                    for a in agenda[:8]:
                        doc.add_paragraph(a, style='List Bullet')

                # 需提交
                submit_match = re.search(r'本次需提交[：:]\s*(.+)', mt_content)
                if submit_match:
                    p = doc.add_paragraph()
                    run = p.add_run('📥 本次需提交：')
                    run.font.bold = True
                    p.add_run(submit_match.group(1).strip())

                # 会后待办
                action_match = re.search(r'会后待办[：:]\s*(.+)', mt_content)
                if action_match:
                    p = doc.add_paragraph()
                    run = p.add_run('✅ 会后待办：')
                    run.font.bold = True
                    p.add_run(action_match.group(1).strip())

        doc.add_paragraph()

        # ── 3. 任务分配 ──
        tasks_text = sections.get("👥 任务分配", "")
        if tasks_text:
            doc.add_heading('三、任务分配', level=1)
            task_lines = [l.strip() for l in tasks_text.splitlines() if l.strip().startswith("|") and not l.strip().startswith("|-")]
            if task_lines:
                header_cells = [c.strip() for c in task_lines[0].split("|") if c.strip()]
                table = doc.add_table(rows=1, cols=len(header_cells) if header_cells else 5)
                table.style = 'Light Grid Accent 1'
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                for i, h in enumerate(header_cells):
                    table.rows[0].cells[i].text = h
                    for p in table.rows[0].cells[i].paragraphs:
                        for r in p.runs:
                            r.font.bold = True
                            r.font.size = Pt(9)
                for row_line in task_lines[1:]:
                    cells = [c.strip() for c in row_line.split("|") if c.strip()]
                    if cells:
                        row = table.add_row().cells
                        for j, cell_text in enumerate(cells):
                            if j < len(row):
                                row[j].text = cell_text

        doc.add_paragraph()

        # ── 4. 交付物清单 ──
        dlv_text = sections.get("📦 交付物清单", "")
        if dlv_text:
            doc.add_heading('四、交付物清单', level=1)
            dlv_lines = [l.strip() for l in dlv_text.splitlines() if l.strip().startswith("|") and not l.strip().startswith("|-")]
            if dlv_lines:
                header_cells = [c.strip() for c in dlv_lines[0].split("|") if c.strip()]
                table = doc.add_table(rows=1, cols=len(header_cells) if header_cells else 5)
                table.style = 'Light Grid Accent 1'
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                for i, h in enumerate(header_cells):
                    table.rows[0].cells[i].text = h
                    for p in table.rows[0].cells[i].paragraphs:
                        for r in p.runs:
                            r.font.bold = True
                            r.font.size = Pt(9)
                for row_line in dlv_lines[1:]:
                    cells = [c.strip() for c in row_line.split("|") if c.strip()]
                    if cells:
                        row = table.add_row().cells
                        for j, cell_text in enumerate(cells):
                            if j < len(row):
                                row[j].text = cell_text

        doc.add_paragraph()

        # ── 5. 风险与备注 ──
        risks_text = sections.get("⚠️ 风险与备注", "")
        if risks_text:
            doc.add_heading('五、风险与备注', level=1)
            for line in risks_text.splitlines():
                s = line.strip()
                if s.startswith("- "):
                    doc.add_paragraph(s[2:], style='List Bullet')
                elif s:
                    doc.add_paragraph(s)

        # ── 原始输入 ──
        doc.add_page_break()
        doc.add_heading('附录：原始输入', level=1)
        p = doc.add_paragraph()
        run = p.add_run(raw_input[:5000])
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        # 保存
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        append_trace("docx.generated", {"path": str(output_path)})
        return True
    except Exception as e:
        append_trace("docx.error", {"error": str(e)})
        return False

# ============================================================
# 导出对话
# ============================================================
def export_conversation(messages: List[Tuple[str, str]], path: Optional[Path] = None):
    """导出对话为 .txt."""
    if not path:
        path = PACKAGE_ROOT / "outputs" / f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"小组排程助手 — 对话记录\n导出时间：{now_ts()}\n{'='*50}\n\n")
        for role, text in messages:
            prefix = "🤖 AI" if role == "ai" else "👤 用户"
            f.write(f"{prefix} [{len(text)}字]:\n{text}\n\n---\n\n")
    return path

# ============================================================
# 演示数据
# ============================================================
DEMO_DATA = (
    "【小组聊天记录 — 第3周项目分工讨论】\n\n"
    "张三：这周的项目大家分一下工吧。我有后端经验，Python和FastAPI熟，性能优化也可以搞。\n"
    "李四：我做前端，React还行。但UI设计不太会，需要有人配合出原型。\n"
    "王五：我会Figma，可以做原型和UI设计。另外提醒一下我周三下午要去医院复查，那个时间段不行。\n"
    "赵六：我比较擅长写文档和做PPT，技术不太行但可以做调研和整理。\n\n"
    "张三：任务大概这几个：\n"
    "  A.市场调研(需要2人,估计20h)\n"
    "  B.UI原型(15h)\n"
    "  C.前端开发(2人,25h)\n"
    "  D.后端开发(2人,20h)\n"
    "  E.答辩PPT(10h)\n\n"
    "李四：我们周五前能全部搞完吗？时间好紧。\n"
    "张三：周五下午5点截止，大家说下自己的空闲时间？\n"
    "王五：我周一全天、周二上午可以。周三下午去医院，其他时间都行。\n"
    "李四：我周一到周四晚上7点后都有空，周末全天可以肝。\n"
    "赵六：时间比较灵活，除了周二上午有课，其他时间都行。\n"
    "张三：我都可以。那周一晚上先开个会？\n"
    "李四：好的，周一晚上8点线上？\n"
    "王五：OK\n"
    "赵六：没问题"
)

# ============================================================
# 消息气泡 Widget
# ============================================================
class ChatBubble(tk.Frame):
    """单条聊天气泡."""

    COLORS = {
        "ai": {"bg": "#ffffff", "avatar_bg": "#07c160", "avatar": "🤖", "side": "left"},
        "user": {"bg": "#95ec69", "avatar_bg": "#1485cc", "avatar": "👤", "side": "right"},
        "system": {"bg": "#fff3cd", "avatar_bg": "#f59e0b", "avatar": "📢", "side": "left"},
    }

    def __init__(self, parent, text: str, role: str = "ai", on_copy=None):
        super().__init__(parent, bg="#f5f5f5")
        cfg = self.COLORS.get(role, self.COLORS["ai"])
        side = cfg["side"]

        # 头像
        avatar = tk.Label(self, text=cfg["avatar"], font=("Segoe UI Emoji", 13),
                          bg="#f5f5f5")
        avatar.pack(side=side, anchor="n", padx=(0, 6) if side == "left" else (6, 0))

        # 气泡
        bubble_bg = cfg["bg"]
        is_schedule = ("## " in text and
                       any(k in text for k in ["任务分配", "会议", "交付物", "信息提取", "排程"]))

        if is_schedule:
            self._render_schedule(text, cfg)
        else:
            bubble = tk.Frame(self, bg=bubble_bg, bd=0,
                              highlightbackground="#e8e8e8", highlightthickness=1)
            bubble.pack(side=side, anchor="n")

            lbl = tk.Label(bubble, text=text, font=("Microsoft YaHei UI", 10),
                           bg=bubble_bg, fg="#333333", justify="left",
                           wraplength=380, padx=12, pady=10)
            lbl.pack()

        # 时间戳
        ts = now_time()
        tk.Label(self, text=ts, font=("Microsoft YaHei UI", 7),
                 bg="#f5f5f5", fg="#b0b0b0").pack(side=side, padx=6, pady=(2, 0))

    def _render_schedule(self, text, cfg):
        """渲染排程结果卡片."""
        container = tk.Frame(self, bg=cfg["bg"], bd=0,
                             highlightbackground="#e0e0e0", highlightthickness=1)
        container.pack(side=cfg["side"], anchor="n", padx=0, pady=2)

        lines = text.split("\n")
        buf = []
        in_table = False

        for line in lines:
            s = line.strip()
            if s.startswith("## "):
                if buf:
                    self._flush(container, buf)
                    buf = []
                title = s[3:]
                tk.Label(container, text=title,
                         font=("Microsoft YaHei UI", 11, "bold"),
                         bg=cfg["bg"], fg="#333", anchor="w", justify="left",
                         wraplength=380, padx=10, pady=(8, 2)).pack(fill="x")
            elif s.startswith("|"):
                if not in_table:
                    in_table = True
                    if buf:
                        self._flush(container, buf)
                        buf = []
                cells = [c.strip() for c in s.split("|") if c.strip()]
                if all(re.match(r"^[-: ]+$", c) for c in cells):
                    continue
                row = tk.Frame(container, bg=cfg["bg"])
                row.pack(fill="x", padx=10)
                for cell in cells:
                    is_h = any(k in cell for k in ["任务", "负责人", "交付", "工时", "优先级"])
                    tk.Label(row, text=cell,
                             font=("Microsoft YaHei UI", 8, "bold" if is_h else 8),
                             bg="#f9fafb" if is_h else cfg["bg"],
                             fg="#333", anchor="w", justify="left",
                             padx=4, pady=2, relief="solid", bd=1,
                             highlightbackground="#e5e7eb").pack(side="left", fill="x", expand=True)
            else:
                if in_table:
                    in_table = False
                if s:
                    buf.append(s)
                elif buf:
                    self._flush(container, buf)
                    buf = []
        if buf:
            self._flush(container, buf)

    def _flush(self, parent, lines):
        text = "\n".join(lines)
        if text.strip():
            # Bold markers
            text = text.replace("**", "")
            tk.Label(parent, text=text,
                     font=("Microsoft YaHei UI", 9),
                     bg=parent["bg"], fg="#555", anchor="w", justify="left",
                     wraplength=400, padx=10, pady=2).pack(fill="x")


# ============================================================
# 主窗口
# ============================================================
# ============================================================
# 项目选择对话框
# ============================================================
def show_project_selector() -> Optional[Path]:
    """启动时选择/创建项目文件夹。返回选中的路径，None=退出."""
    root = tk.Tk()
    root.title("选择项目文件夹")
    root.geometry("560x500")
    root.resizable(False, False)
    root.configure(bg="#f0f2f5")
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"560x500+{(sw-560)//2}+{(sh-500)//2}")

    result = {"path": None}

    # 先定义所有回调函数
    parent_var = tk.StringVar(value=str(Path.home() / "Desktop"))
    new_var = tk.StringVar()
    listbox = None  # 稍后赋值

    def _select_existing():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先双击列表中的一个项目，或新建一个。")
            return
        text = listbox.get(sel[0])
        name = text.strip().split("  →")[0].strip()
        parent = Path(parent_var.get())
        proj = parent / name
        if proj.exists():
            result["path"] = proj
            root.destroy()

    def _create_and_go():
        name = new_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入项目名称。")
            return
        parent = Path(parent_var.get())
        proj = create_new_project(parent, name)
        result["path"] = proj
        root.destroy()

    def _refresh_list():
        listbox.delete(0, "end")
        parent = Path(parent_var.get())
        projects = scan_project_folders(parent)
        if not projects:
            listbox.insert("end", "  （暂无项目，请在下方创建）")
        for p in projects:
            subs = [d.name for d in p.iterdir() if d.is_dir()]
            listbox.insert("end", f"  {p.name}  →  {', '.join(subs[:3])}")

    def _browse_parent():
        from tkinter import filedialog
        d = filedialog.askdirectory(title="选择项目存放目录", initialdir=parent_var.get())
        if d:
            parent_var.set(d)
            _refresh_list()

    # ── 现在构建 UI ──

    # 标题
    tk.Label(root, text="📂 选择工作项目", font=("Microsoft YaHei UI", 16, "bold"),
             bg="#f0f2f5", fg="#1a1a2e").pack(pady=(24, 4))
    tk.Label(root, text="选择一个已有的项目文件夹，或新建一个。\n所有操作将限定在该文件夹内。",
             font=("Microsoft YaHei UI", 9), bg="#f0f2f5", fg="#8899aa").pack(pady=(0, 16))

    # 父目录选择
    parent_frame = tk.Frame(root, bg="white", bd=0, highlightbackground="#e0e0e0", highlightthickness=1)
    parent_frame.pack(fill="x", padx=24, pady=(0, 8))
    tk.Label(parent_frame, text="项目存放位置：", font=("Microsoft YaHei UI", 10),
             bg="white", fg="#333").pack(side="left", padx=12, pady=10)
    parent_entry = tk.Entry(parent_frame, textvariable=parent_var, font=("Microsoft YaHei UI", 9),
                            bg="white", relief="flat", width=35)
    parent_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=10)
    tk.Button(parent_frame, text="浏览…", font=("Microsoft YaHei UI", 8),
              bg="#e0e0e0", relief="flat",
              command=_browse_parent).pack(side="right", padx=8, pady=10)

    # 已有项目列表
    list_frame = tk.Frame(root, bg="white", bd=0, highlightbackground="#e0e0e0", highlightthickness=1)
    list_frame.pack(fill="both", expand=True, padx=24, pady=8)
    list_frame.pack_propagate(False)
    list_frame.configure(height=150)

    tk.Label(list_frame, text="已有项目：", font=("Microsoft YaHei UI", 10, "bold"),
             bg="white", fg="#333").pack(anchor="w", padx=12, pady=(10, 4))

    listbox = tk.Listbox(list_frame, font=("Microsoft YaHei UI", 10), bg="white", fg="#333",
                         selectbackground="#07c160", selectforeground="white",
                         relief="flat", bd=0, activestyle="none")
    listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    listbox.bind("<Double-Button-1>", lambda e: _select_existing())

    _refresh_list()

    # 新建项目
    new_frame = tk.Frame(root, bg="white", bd=0, highlightbackground="#e0e0e0", highlightthickness=1)
    new_frame.pack(fill="x", padx=24, pady=(0, 8))
    tk.Label(new_frame, text="新建项目名：", font=("Microsoft YaHei UI", 10),
             bg="white", fg="#333").pack(side="left", padx=12, pady=10)
    new_entry = tk.Entry(new_frame, textvariable=new_var, font=("Microsoft YaHei UI", 10),
                         bg="white", relief="flat", width=20)
    new_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=10)
    new_entry.bind("<Return>", lambda e: _create_and_go())

    tk.Button(new_frame, text="＋ 创建", font=("Microsoft YaHei UI", 9, "bold"),
              bg="#07c160", fg="white", relief="flat", padx=14, pady=4,
              command=_create_and_go).pack(side="right", padx=8, pady=10)

    # 底部按钮
    btn_frame = tk.Frame(root, bg="#f0f2f5")
    btn_frame.pack(fill="x", padx=24, pady=(4, 16))
    tk.Button(btn_frame, text="✓ 选择已有项目", font=("Microsoft YaHei UI", 10, "bold"),
              bg="#0f766e", fg="white", relief="flat", padx=20, pady=8,
              command=_select_existing).pack(side="right", padx=4)
    tk.Button(btn_frame, text="✕ 退出", font=("Microsoft YaHei UI", 10),
              bg="#e0e0e0", fg="#555", relief="flat", padx=16, pady=8,
              command=root.destroy).pack(side="right", padx=4)

    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass
    return result["path"]


class WeChatApp:
    def __init__(self, project_path: Optional[Path] = None):
        if project_path:
            set_project(project_path)

        self.proj_name = PROJECT_ROOT.name

        self.root = tk.Tk()
        self.root.title(f"小组排程助手 — {self.proj_name}")
        self.root.geometry("860x640")
        self.root.minsize(620, 420)
        self.root.configure(bg="#f5f5f5")

        # 居中
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 860, 640
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 对话历史
        self.chat_messages: List[Tuple[str, str]] = []  # (role, text)
        self.api_chat_history: List[Dict] = [
            {"role": "system", "content": (
                "你是小组任务排程助手+学习伙伴。简洁中文回复，用 Markdown 结构化信息。"
                "如果检测到排程需求（聊天记录中有组员+任务+时间），"
                "生成完整方案（任务分配表格+会议安排+交付物+风险）。"
            )}
        ]
        self.is_loading = False
        self.last_clipboard = ""

        self._build_ui()
        self._add_welcome()

        # 快捷键
        self.root.bind("<Control-Return>", lambda e: self.send_message())
        self.root.bind("<Escape>", lambda e: self.text_input.focus_set())

        # 启动后台任务
        self._start_background_tasks()

    # ── UI 构建 ──
    def _build_ui(self):
        # 标题栏
        self.titlebar = tk.Frame(self.root, bg="#2e2e2e", height=30)
        self.titlebar.pack(fill="x", side="top")
        self.titlebar.pack_propagate(False)
        tk.Label(self.titlebar, text="💬  小组排程助手  ·  Day3 Desktop Agent",
                 bg="#2e2e2e", fg="white", font=("Microsoft YaHei UI", 9),
                 padx=12).pack(side="left")
        self.status_label = tk.Label(self.titlebar, text="🟢 就绪",
                                     bg="#2e2e2e", fg="#aaa",
                                     font=("Microsoft YaHei UI", 8), padx=12)
        self.status_label.pack(side="right")

        # 主体
        main = tk.Frame(self.root, bg="#f5f5f5")
        main.pack(fill="both", expand=True)

        # ── 左侧栏 ──
        sidebar = tk.Frame(main, bg="#e8e8e8", width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # 头像区
        profile = tk.Frame(sidebar, bg="#e8e8e8", padx=14, pady=14)
        profile.pack(fill="x")
        tk.Label(profile, text="👤", font=("Segoe UI Emoji", 24),
                 bg="#e8e8e8").pack(side="left")
        info_frame = tk.Frame(profile, bg="#e8e8e8")
        info_frame.pack(side="left", padx=10)
        tk.Label(info_frame, text="组长（你）", font=("Microsoft YaHei UI", 11, "bold"),
                 bg="#e8e8e8", fg="#333").pack(anchor="w")
        mode_text = "🔴 离线" if MOCK_LLM or not API_KEY else "🟢 API · DeepSeek"
        self.mode_label = tk.Label(info_frame, text=mode_text,
                                    font=("Microsoft YaHei UI", 8),
                                    bg="#e8e8e8", fg="#999")
        self.mode_label.pack(anchor="w")

        # 联系人列表
        contacts = tk.Frame(sidebar, bg="#e8e8e8")
        contacts.pack(fill="both", expand=True)
        for icon, name, desc, tag in [
            ("🤖", "排程 AI", "聊天·排程·问答", "ai"),
            ("📋", "排程面板", "查看任务与会议", "schedule"),
            ("📖", "文件存储", "查看所有传入文件", "files"),
            ("⚙️", "文件夹设置", f"选择/新建工作文件夹", "settings"),
        ]:
            self._contact_item(contacts, icon, name, desc, tag)

        # 底部按钮
        bottom = tk.Frame(sidebar, bg="#e8e8e8", padx=10, pady=10)
        bottom.pack(fill="x", side="bottom")
        for text, cmd in [
            ("⚙️ 设置", self._show_config),
            ("💾 导出对话", self._export),
            ("📂 打开文件夹", self._open_workspace),
        ]:
            tk.Button(bottom, text=text, font=("Microsoft YaHei UI", 8),
                      bg="#e0e0e0", fg="#555", relief="flat",
                      command=cmd, cursor="hand2").pack(fill="x", pady=2)

        # ── 聊天区 ──
        chat_area = tk.Frame(main, bg="#f5f5f5")
        chat_area.pack(side="left", fill="both", expand=True)

        # 标题
        chat_header = tk.Frame(chat_area, bg="#f5f5f5", height=48,
                               highlightbackground="#e0e0e0", highlightthickness=1)
        chat_header.pack(fill="x", side="top")
        chat_header.pack_propagate(False)
        self.chat_title = tk.Label(chat_header, text="🤖 小组排程 AI",
                                   font=("Microsoft YaHei UI", 12, "bold"),
                                   bg="#f5f5f5", fg="#333")
        self.chat_title.pack(side="left", padx=16, pady=12)

        # 按钮
        btn_bar = tk.Frame(chat_header, bg="#f5f5f5")
        btn_bar.pack(side="right", padx=8)
        for text, cmd in [
            ("📋 粘贴", self._paste),
            ("📥 演示", self._demo),
            ("🗑️ 清空", self._clear),
        ]:
            tk.Button(btn_bar, text=text, font=("Microsoft YaHei UI", 8),
                      bg="white", fg="#555", relief="solid", bd=1,
                      command=cmd, cursor="hand2").pack(side="left", padx=2)

        # 消息区
        msg_container = tk.Frame(chat_area, bg="#f5f5f5")
        msg_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(msg_container, bg="#f5f5f5",
                                highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(msg_container, orient="vertical",
                                      command=self.canvas.yview)
        self.msg_frame = tk.Frame(self.canvas, bg="#f5f5f5")

        self.msg_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.msg_frame, anchor="nw",
                                  tags="inner_frame")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        def _wheel(event):
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        self.canvas.bind("<MouseWheel>", _wheel)
        self.canvas.bind("<Configure>",
            lambda e: self.canvas.itemconfig("inner_frame", width=e.width))

        # ── 输入区 ──
        input_frame = tk.Frame(chat_area, bg="#f5f5f5",
                               highlightbackground="#e0e0e0", highlightthickness=1)
        input_frame.pack(fill="x", side="bottom")

        # 快捷标签
        quick = tk.Frame(input_frame, bg="#f5f5f5")
        quick.pack(fill="x", padx=12, pady=(6, 0))
        for text, cmd in [
            ("📦 演示排程", self._demo),
            ("📋 粘贴聊天", self._paste),
            ("📁 上传文件", self._upload_file),
            ("📂 查看文件", lambda: self._contact_action("files")),
        ]:
            lbl = tk.Label(quick, text=text, font=("Microsoft YaHei UI", 8),
                           bg="#eef8f6", fg="#0b534d", padx=8, pady=2, cursor="hand2")
            lbl.pack(side="left", padx=2)
            lbl.bind("<Button-1>", lambda e, c=cmd: c())

        # 输入行
        input_row = tk.Frame(input_frame, bg="#f5f5f5")
        input_row.pack(fill="x", padx=12, pady=8)

        self.text_input = tk.Text(input_row, height=2,
                                  font=("Microsoft YaHei UI", 10),
                                  bg="white", fg="#333", relief="flat", bd=1,
                                  wrap="word", padx=10, pady=8)
        self.text_input.pack(side="left", fill="x", expand=True)

        self.send_btn = tk.Button(input_row, text="发送 (Ctrl+Enter)",
                                  font=("Microsoft YaHei UI", 10, "bold"),
                                  bg="#07c160", fg="white", relief="flat",
                                  padx=16, pady=6, bd=0, cursor="hand2",
                                  activebackground="#06ad56", activeforeground="white",
                                  command=self.send_message)
        self.send_btn.pack(side="right", padx=(8, 0))

        # 剪贴板状态
        self.cb_label = tk.Label(input_frame, text="📋 剪贴板监控中…",
                                 font=("Microsoft YaHei UI", 7),
                                 bg="#f5f5f5", fg="#b0b0b0")
        self.cb_label.pack(side="left", padx=12, pady=(0, 4))

        self.text_input.focus_set()
        self.text_input.bind("<Return>",
            lambda e: (self.send_message() if not e.state & 1 else None) or "break")
        self.text_input.bind("<Shift-Return>",
            lambda e: self.text_input.insert("insert", "\n") or "break")

    def _contact_item(self, parent, icon, name, desc, tag):
        f = tk.Frame(parent, bg="#e8e8e8", padx=14, pady=8,
                     highlightbackground="#e0e0e0", highlightthickness=1,
                     cursor="hand2")
        f.pack(fill="x")
        tk.Label(f, text=icon, font=("Segoe UI Emoji", 14),
                 bg="#e8e8e8").pack(side="left")
        info = tk.Frame(f, bg="#e8e8e8")
        info.pack(side="left", padx=8)
        tk.Label(info, text=name, font=("Microsoft YaHei UI", 10, "bold"),
                 bg="#e8e8e8", fg="#333").pack(anchor="w")
        tk.Label(info, text=desc, font=("Microsoft YaHei UI", 8),
                 bg="#e8e8e8", fg="#999").pack(anchor="w")
        f.bind("<Button-1>", lambda e, t=tag: self._contact_action(t))
        for child in f.winfo_children():
            child.bind("<Button-1>", lambda e, t=tag: self._contact_action(t))
            if isinstance(child, tk.Frame):
                for c in child.winfo_children():
                    c.bind("<Button-1>", lambda e, t=tag: self._contact_action(t))

    def _contact_action(self, tag):
        if tag == "schedule":
            self._show_schedule_inline()
        elif tag == "files":
            self._show_files_inline()
        elif tag == "settings":
            self._switch_project()
        elif tag == "input":
            files = scan_input_dir()
            if files:
                text = files[0].read_text(encoding="utf-8", errors="ignore")
                self.text_input.delete("1.0", "end")
                self.text_input.insert("1.0", text)
                self._add_system_msg(f"📄 已加载: {files[0].name} ({len(text)}字)")

    def _show_files_inline(self):
        """列出文件，支持点击加载到输入框."""
        all_files = sorted(
            [f for f in PROJECT_ROOT.rglob("*") if f.is_file() and not f.name.startswith("~$")],
            key=lambda f: f.stat().st_mtime, reverse=True
        )

        if not all_files:
            self._add_system_msg(
                "📂 暂无文件\n\n"
                "💡 上传文件的方式：\n"
                "  1. 拖入 桌面\\小组作业\\聊天记录\\\n"
                "  2. 点底部 📁上传文件 选择文件\n"
                "  3. 在微信中复制 → 📋粘贴聊天")
            return

        by_dir: Dict[str, List[Path]] = {}
        for f in all_files:
            rel = str(f.parent.relative_to(PROJECT_ROOT)) if PROJECT_ROOT in f.parents else ""
            by_dir.setdefault(rel, []).append(f)

        msg = "📂 文件列表（点击文件名加载到输入框）：\n\n"
        file_index = 0
        self._loaded_file_paths = []
        for dirname, files in sorted(by_dir.items()):
            label = dirname + "/" if dirname else ""
            msg += f"▸ {label}\n"
            for f in files[:15]:
                size_kb = f.stat().st_size / 1024
                mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%m/%d %H:%M")
                msg += f"  [{file_index}] {f.name}  ({size_kb:.1f}KB)\n"
                self._loaded_file_paths.append(f)
                file_index += 1
            msg += "\n"

        msg += (f"共 {len(all_files)} 个文件\n"
                "回复文件编号（如 [0]）即可加载文件内容到输入框，再次发送即可排程。\n"
                "💡 也可点 📁上传文件 选择本地文件自动复制到聊天记录/。")

        self._add_system_msg(msg)
        # 临时存储，用于后续匹配编号
        self._file_list_msg_id = len(self.chat_messages)

    def _latest_session_dir(self) -> Optional[Path]:
        """找最新排程目录（按修改时间）."""
        if not WORKSPACE.exists():
            return None
        dirs = [d for d in WORKSPACE.iterdir() if d.is_dir()]
        if not dirs:
            return None
        return max(dirs, key=lambda d: d.stat().st_mtime)

    def _show_schedule_inline(self):
        """打开最新排程的 Word 文档."""
        session = self._latest_session_dir()
        if session:
            docx_path = session / "小组排程方案.docx"
            if docx_path.exists():
                os.startfile(str(docx_path))
                self._add_system_msg(f"📄 已打开：{session.name}")
                return
        self._add_system_msg(
            "📋 还没有排程记录。\n"
            "请先粘贴小组聊天记录 → 发送，或点 📦演示 看示例。")

    # ── 消息操作 ──
    def _add_bubble(self, text: str, role: str = "ai"):
        bubble = ChatBubble(self.msg_frame, text, role)
        bubble.pack(fill="x", padx=10, pady=3)
        self._scroll_bottom()
        return bubble

    def _add_welcome(self):
        self._add_bubble(
            f"👋 你好！当前项目：**{PROJECT_ROOT.name}**\n\n"
            "📋 **粘贴微信群聊记录** → 自动生成排程方案\n"
            "📁 **上传文件** → 选 聊天记录/ 中的文件加载\n"
            "📦 **演示排程** → 看示例效果\n\n"
            f"📂 项目位置：{PROJECT_ROOT}\n"
            "  ├── 聊天记录/  ← 放聊天 .txt\n"
            "  ├── 排程结果/  ← 生成的排程方案\n"
            "  └── 运行记录/  ← trace_log",
            role="ai"
        )

    def _add_system_msg(self, text: str):
        self._add_bubble(text, role="system")

    def _scroll_bottom(self):
        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    # ── 发送 ──
    def send_message(self, text: Optional[str] = None):
        if self.is_loading:
            return

        if text is None:
            text = self.text_input.get("1.0", "end-1c").strip()
        if not text:
            return

        # 文件编号快捷加载：[0] [1] 等
        file_match = re.match(r'^\[(\d+)\]$', text.strip())
        if file_match and hasattr(self, '_loaded_file_paths'):
            idx = int(file_match.group(1))
            if idx < len(self._loaded_file_paths):
                fp = self._loaded_file_paths[idx]
                content = fp.read_text(encoding="utf-8", errors="ignore")
                self.text_input.delete("1.0", "end")
                self.text_input.insert("1.0", content)
                self._add_system_msg(f"📄 已加载 [{idx}] {fp.name} ({len(content)}字)\n按 Ctrl+Enter 发送排程。")
                return
            else:
                self._add_system_msg(f"❌ 编号 [{idx}] 超出范围（共 {len(self._loaded_file_paths)} 个文件）")
                return

        self.is_loading = True
        self.send_btn.config(text="…", bg="#b0b0b0")
        self.status_label.config(text="🟡 思考中…", fg="#f59e0b")
        self.text_input.delete("1.0", "end")

        # 用户气泡
        self._add_bubble(text, role="user")
        self.chat_messages.append(("user", text))

        # 后台处理
        def do_work():
            schedule_mode = is_schedule_intent(text)

            if schedule_mode:
                append_trace("schedule.request", {"chars": len(text)})
                reply = call_llm_schedule(text)
                save_schedule_to_workspace(text, reply, "wechat_app")
                generate_dashboard(text, reply)
                append_trace("schedule.completed", {"output_chars": len(reply)})
            else:
                self.api_chat_history.append({"role": "user", "content": text})
                reply = call_llm_chat(self.api_chat_history[-20:])
                self.api_chat_history.append({"role": "assistant", "content": reply})

            self.root.after(0, lambda: self._on_reply(reply, schedule_mode))

        threading.Thread(target=do_work, daemon=True).start()

    def _on_reply(self, reply: str, is_schedule: bool):
        self.is_loading = False
        self.send_btn.config(text="发送 (Ctrl+Enter)", bg="#07c160")
        status = "🟢 排程已保存" if is_schedule else "🟢 就绪"
        self.status_label.config(text=status, fg="#aaa")

        if is_schedule:
            session = self._latest_session_dir()
            if session:
                docx_path = session / "小组排程方案.docx"
                os.startfile(str(docx_path)) if docx_path.exists() else None
                self._add_system_msg(
                    f"✅ 排程方案已生成\n📂 {session.name}\n📄 小组排程方案.docx 已打开\n\n点击左侧 📋排程面板 再次打开"
                )
            else:
                self._add_system_msg("✅ 排程已完成")
        else:
            self._add_bubble(reply, role="ai")

        self.chat_messages.append(("ai", reply))

    def _quick(self, msg: str):
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", msg)
        self.send_message()

    def _demo(self):
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", DEMO_DATA)
        self.send_message()

    def _paste(self):
        # 优先从 win32 剪贴板读
        data = read_clipboard()
        if not data:
            try:
                data = self.root.clipboard_get()
            except Exception:
                pass
        if data and len(data) > 10:
            self.text_input.delete("1.0", "end")
            self.text_input.insert("1.0", data)
            self._add_system_msg(f"📋 已粘贴剪贴板内容 ({len(data)}字)。按 Ctrl+Enter 发送。")
            self.text_input.focus_set()
        else:
            self._add_system_msg("📋 剪贴板内容为空或太短。请在微信中 Ctrl+A→Ctrl+C 复制聊天记录后再试。")

    def _upload_file(self):
        """打开小组作业文件夹内的文件选择器，加载内容."""
        from tkinter import filedialog
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        paths = filedialog.askopenfilenames(
            title="选择小组作业内的文件",
            initialdir=str(PROJECT_ROOT),
            filetypes=[("文本文件", "*.txt *.md"), ("所有文件", "*.*")]
        )
        if not paths:
            return

        loaded = []
        boundary = PROJECT_ROOT.resolve()
        for p in paths:
            src = Path(p).resolve()
            # 只允许小组作业内的文件
            if boundary not in src.parents and src != boundary:
                self._add_system_msg(f"⛔ 拒绝：{src.name} 不在桌面\\小组作业\\ 内\n只能上传小组作业文件夹内的文件。")
                continue
            # 如果不在聊天记录/下，复制过去
            input_boundary = INPUT_DIR.resolve()
            if input_boundary not in src.parents:
                dst = INPUT_DIR / src.name
                if dst.exists():
                    dst = INPUT_DIR / f"{src.stem}_{datetime.now().strftime('%H%M%S')}{src.suffix}"
                dst.write_bytes(src.read_bytes())
                loaded.append(dst)
            else:
                loaded.append(src)

        if loaded:
            text = loaded[0].read_text(encoding="utf-8", errors="ignore")
            self.text_input.delete("1.0", "end")
            self.text_input.insert("1.0", text)
            names = ", ".join(f.name for f in loaded)
            self._add_system_msg(f"📁 已加载：{names}\n按 Ctrl+Enter 发送排程。")

    def _auto_schedule(self, msg: str):
        """剪贴板自动检测 → 直接排程."""
        self.cb_label.config(text=f"📋 检测到聊天内容 ({len(msg)}字) — 自动排程中...")
        self.status_label.config(text="🟡 自动排程中...", fg="#f59e0b")

        def do_work():
            gen = mock_schedule_reply(msg)
            try:
                save_schedule_to_workspace(msg, gen, "clipboard_auto")
            except Exception:
                pass
            # 后台调 LLM 更新
            try:
                real = call_llm_schedule(msg)
                if real and "##" in real:
                    save_schedule_to_workspace(msg, real, "clipboard_auto")
            except Exception:
                pass

            docx = self._latest_session_dir()
            docx_path = docx / "小组排程方案.docx" if docx else None

            def _update_ui():
                self.status_label.config(text="🟢 就绪", fg="#aaa")
                self.cb_label.config(text=f"📋 排程完成 ({len(msg)}字)")
                self._add_system_msg(
                    f"✅ 剪贴板内容已自动排程！\n"
                    f"📄 {docx_path if docx_path else '排程结果/小组排程方案.docx'}")
                if docx_path and docx_path.exists():
                    os.startfile(str(docx_path))
            self.root.after(0, _update_ui)

        threading.Thread(target=do_work, daemon=True).start()

    def _clear(self):
        if messagebox.askyesno("清空", "确定清空当前对话？\n（workspace 中的排程产物不受影响）"):
            for w in self.msg_frame.winfo_children():
                w.destroy()
            self.chat_messages.clear()
            self.api_chat_history = self.api_chat_history[:1]
            self._add_welcome()

    def _export(self):
        path = export_conversation(self.chat_messages)
        self._add_system_msg(f"💾 对话已导出到:\n{path}")

    def _switch_project(self):
        """重新打开项目选择器，切换到另一个项目."""
        new_proj = show_project_selector()
        if new_proj:
            set_project(new_proj)
            # 清空对话
            for w in self.msg_frame.winfo_children():
                w.destroy()
            self.chat_messages.clear()
            self.api_chat_history = self.api_chat_history[:1]
            # 更新标题
            self.root.title(f"小组排程助手 — {PROJECT_ROOT.name}")
            # 更新欢迎消息
            self._add_welcome()
            self._add_system_msg(f"✅ 已切换到项目：{PROJECT_ROOT.name}\n📂 {PROJECT_ROOT}")

    def _open_workspace(self):
        os.startfile(str(PROJECT_ROOT))

    def _show_config(self):
        info = (
            f"项目：{PROJECT_ROOT.name}\n"
            f"路径：{PROJECT_ROOT}\n\n"
            f"模型：{MODEL_NAME}\n"
            f"API Key：{'已设置' if API_KEY else '未设置（离线模式）'}\n"
            f"模式：{'离线/Mock' if MOCK_LLM or not API_KEY else '真实API'}\n"
            f"对话轮数：{len(self.chat_messages)}\n"
            f"\n⚠️ AI 只能读写 {PROJECT_ROOT.name}\\ 内的文件。"
        )
        messagebox.showinfo("⚙️ 配置信息", info)

    # ── 后台任务 ──
    def _start_background_tasks(self):
        def clipboard_watcher():
            """每2秒检测剪贴板，有排程内容自动处理."""
            while True:
                time.sleep(2)
                try:
                    data = read_clipboard()
                    if data and data != self.last_clipboard and len(data) > 30:
                        self.last_clipboard = data
                        score = sum(1 for k in
                            ["任务", "分配", "开会", "截止", "DDL", "项目", "分工",
                             "小组", "交付", "空闲", "我有", "我擅长", "@all"]
                            if k in data)
                        if score >= 2 or len(data) > 100:
                            self.root.after(0, lambda m=data: self._auto_schedule(m))
                        else:
                            self.root.after(0, lambda d=data:
                                self.cb_label.config(
                                    text=f"📋 剪贴板: {len(d)}字 — 复制排程内容自动处理"))

                    files = scan_input_dir()
                    if files:
                        self.root.after(0, lambda fs=files:
                            self.cb_label.config(
                                text=f"📂 输入文件夹有 {len(fs)} 个待处理文件"))
                except Exception:
                    pass

        t = threading.Thread(target=clipboard_watcher, daemon=True)
        t.start()
        self._clipboard_thread = t

    def _on_close(self):
        append_trace("app.close", {"messages": len(self.chat_messages)})
        self.root.destroy()

    def run(self):
        self.root.mainloop()



# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    # 加载上次项目或使用默认
    last = load_last_project()
    if last and last.exists():
        set_project(last)
    else:
        default = Path.home() / "Desktop" / "小组作业"
        for sub in ["聊天记录", "排程结果", "运行记录"]:
            (default / sub).mkdir(parents=True, exist_ok=True)
        set_project(default)

    # 启动主窗口
    app = WeChatApp()
    app.run()
