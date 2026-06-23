import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


TEXT_SUFFIXES = {".md", ".txt", ".json"}
GENERATED_SKIP_NAMES = {
    "chunk_index.json",
    "retrieval_result.json",
    "agent_run_report.json",
    "latest_device_reply.txt",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def short(text: str, limit: int = 120) -> str:
    clean = " ".join((text or "").strip().split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def compact_args(args: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, value in args.items():
        if key == "content" and isinstance(value, str):
            compact[key] = {"chars": len(value), "preview": short(value, 180)}
        elif isinstance(value, str) and len(value) > 240:
            compact[key] = short(value, 240)
        else:
            compact[key] = value
    return compact


def safe_path(root: Path, relative: str) -> Path:
    text = str(relative or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("agent_workspace/"):
        text = text[len("agent_workspace/") :]
    text = text.lstrip("/") or "output.md"
    path = (root / text).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError(f"unsafe path: {relative}")
    return path


def relpath(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def append_trace(trace_path: Optional[Path], event_type: str, payload: Dict[str, Any]) -> None:
    if trace_path is None:
        return
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": now(), "type": event_type, "payload": payload}, ensure_ascii=False) + "\n")


def emit(
    event_type: str,
    payload: Dict[str, Any],
    *,
    log_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    trace_path: Optional[Path] = None,
) -> None:
    append_trace(trace_path, event_type, payload)
    if log_event:
        log_event(event_type, payload)


def call_optional_llm(
    call_llm: Optional[Callable[..., str]],
    prompt: str,
    *,
    model: Optional[str],
    max_tokens: int,
) -> str:
    if call_llm is None:
        return ""
    try:
        return (call_llm(prompt, model=model, max_tokens=max_tokens) or "").strip()
    except TypeError:
        return (call_llm(prompt) or "").strip()


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())


def split_chunks(text: str, *, chunk_size: int = 760, overlap: int = 120) -> List[str]:
    clean = "\n".join(line.rstrip() for line in (text or "").splitlines()).strip()
    if not clean:
        return []
    if len(clean) <= chunk_size:
        return [clean]
    chunks: List[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def is_indexable_file(root: Path, path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    if path.name in GENERATED_SKIP_NAMES:
        return False
    relative_parts = set(path.resolve().relative_to(root.resolve()).parts)
    if "knowledge" in relative_parts or "cards" in relative_parts or "reports" in relative_parts:
        return False
    return True


@dataclass
class ToolResult:
    ok: bool
    data: Any
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


class ToolRegistry:
    def __init__(
        self,
        workspace: Path,
        *,
        log_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        trace_path: Optional[Path] = None,
    ) -> None:
        self.workspace = workspace
        self.log_event = log_event
        self.trace_path = trace_path
        self.calls: List[Dict[str, Any]] = []
        self._tools: Dict[str, Callable[..., ToolResult]] = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "search_workspace": self.search_workspace,
            "write_file": self.write_file,
            "move_file": self.move_file,
        }

    def manifest(self) -> List[Dict[str, str]]:
        return [
            {"name": "list_files", "description": "列出 workspace 内的文件，用于感知环境。"},
            {"name": "read_file", "description": "读取 workspace 内的文本文件，用于获得事实。"},
            {"name": "search_workspace", "description": "基于本地 chunk_index 做关键词检索，用于最小 RAG。"},
            {"name": "write_file", "description": "向 workspace 写入摘要、待办、风险、卡片等产物。"},
            {"name": "move_file", "description": "在 workspace 内移动文件；默认实验不主动使用，作为可扩展工具。"},
        ]

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        started = time.time()
        if name not in self._tools:
            result = ToolResult(False, None, f"unknown tool: {name}")
        else:
            try:
                result = self._tools[name](**kwargs)
            except Exception as exc:
                result = ToolResult(False, None, f"{type(exc).__name__}: {exc}")

        event = {
            "tool": name,
            "args": compact_args(kwargs),
            "ok": result.ok,
            "error": result.error,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
        }
        if isinstance(result.data, (list, dict)):
            event["result_preview"] = json.dumps(result.data, ensure_ascii=False)[:600]
        else:
            event["result_preview"] = short(str(result.data), 240)
        self.calls.append(event)
        emit(f"tool.{name}", event, log_event=self.log_event, trace_path=self.trace_path)
        return result

    def list_files(self, path: str = ".") -> ToolResult:
        base = safe_path(self.workspace, path)
        if not base.exists():
            return ToolResult(False, [], f"path not found: {path}")
        files = []
        for item in sorted(base.rglob("*") if base.is_dir() else [base]):
            if item.is_file():
                files.append({"path": relpath(self.workspace, item), "bytes": item.stat().st_size})
        return ToolResult(True, files)

    def read_file(self, path: str, limit: int = 6000) -> ToolResult:
        file_path = safe_path(self.workspace, path)
        if not file_path.exists() or not file_path.is_file():
            return ToolResult(False, "", f"file not found: {path}")
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return ToolResult(True, {"path": relpath(self.workspace, file_path), "text": text[:limit], "chars": len(text)})

    def search_workspace(self, query: str, top_k: int = 5) -> ToolResult:
        index_path = self.workspace / "knowledge" / "chunk_index.json"
        if not index_path.exists():
            return ToolResult(False, [], "knowledge index not found")
        chunks = json.loads(index_path.read_text(encoding="utf-8"))
        results = rank_chunks(chunks, query, top_k=top_k)
        return ToolResult(True, results)

    def write_file(self, path: str, content: str) -> ToolResult:
        file_path = safe_path(self.workspace, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return ToolResult(True, {"path": relpath(self.workspace, file_path), "chars": len(content)})

    def move_file(self, src: str, dst: str) -> ToolResult:
        src_path = safe_path(self.workspace, src)
        dst_path = safe_path(self.workspace, dst)
        if not src_path.exists() or not src_path.is_file():
            return ToolResult(False, None, f"file not found: {src}")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.replace(dst_path)
        return ToolResult(True, {"src": src, "dst": relpath(self.workspace, dst_path)})


def build_knowledge_index(workspace: Path, course_context: str = "") -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    chunk_id = 1
    for path in sorted(workspace.rglob("*")):
        if not is_indexable_file(workspace, path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for idx, chunk in enumerate(split_chunks(text), start=1):
            chunks.append(
                {
                    "chunk_id": f"C{chunk_id:04d}",
                    "source_path": relpath(workspace, path),
                    "source_type": "workspace_file",
                    "chunk_index": idx,
                    "text": chunk,
                }
            )
            chunk_id += 1

    if course_context.strip():
        for idx, chunk in enumerate(split_chunks(course_context, chunk_size=900, overlap=160), start=1):
            chunks.append(
                {
                    "chunk_id": f"C{chunk_id:04d}",
                    "source_path": "__runtime_course_context__/day2_day3_context.md",
                    "source_type": "runtime_context",
                    "chunk_index": idx,
                    "text": chunk,
                }
            )
            chunk_id += 1
    return chunks


def rank_chunks(chunks: Iterable[Dict[str, Any]], query: str, *, top_k: int = 5) -> List[Dict[str, Any]]:
    query_terms = set(tokenize(query))
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for chunk in chunks:
        terms = set(chunk.get("tokens") or tokenize(chunk.get("text", "")))
        if not terms:
            continue
        overlap = query_terms & terms
        score = (len(overlap) * 2.0) / (len(query_terms) + 1.0)
        if any(term in chunk.get("text", "") for term in ["Agent", "工具", "RAG", "知识库", "Prompt", "Day4", "S3"]):
            score += 0.05
        if score <= 0:
            continue
        item = {
            "chunk_id": chunk["chunk_id"],
            "source_path": chunk["source_path"],
            "source_type": chunk.get("source_type", "workspace_file"),
            "score": round(score, 4),
            "matched_terms": sorted(overlap)[:20],
            "excerpt": short(chunk.get("text", ""), 260),
        }
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["source_path"], pair[1]["chunk_id"]))
    return [item for _, item in scored[:top_k]]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def call_siliconflow_direct(prompt: str, *, model: Optional[str] = None, max_tokens: int = 1200) -> str:
    if os.environ.get("MOCK_LLM") == "1":
        return ""
    api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key:
        return ""
    try:
        import requests

        base_url = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
        model_id = model or os.environ.get("MODEL_AGENT") or os.environ.get("MODEL_B") or "deepseek-ai/DeepSeek-V4-Flash"
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是学生手搓的桌面Agent Core。回答必须基于给定资料，输出短、准、可执行的中文Markdown。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.25,
                "max_tokens": max_tokens,
            },
            timeout=80,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0].get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return str(content).strip()
    except Exception:
        return ""


def build_agent_prompt(intent: str, retrieval: List[Dict[str, Any]], course_context: str) -> str:
    sources = []
    for item in retrieval:
        sources.append(
            f"- [{item['chunk_id']}] {item['source_path']} score={item['score']}\n  {item['excerpt']}"
        )
    source_text = "\n".join(sources) if sources else "无检索命中，请根据已知上下文谨慎输出。"
    return f"""
你是Day3学生手搓的最小桌面Agent Core。

边界：
- 你负责调用国产大模型、读取本地workspace、生成结构化学习资料。
- 你不处理ESP-Claw、微信、CoreS3配置。
- 你不暴露 /v1/chat/completions；这个接口属于Day4 Device Gateway。
- 你的输出必须能被Day4设备触发网关继续追问。

用户意图：
{intent}

RAG检索命中的资料片段：
{source_text}

运行时课程上下文补充：
{(course_context or "")[:2500]}

请输出Markdown，严格包含以下四个二级标题：
## 课程摘要
## 待办清单
## 风险清单
## 引用来源
"""


def fallback_summary(retrieval: List[Dict[str, Any]]) -> str:
    source_lines = "\n".join(
        f"- {item['chunk_id']}：{item['source_path']}（score={item['score']}）" for item in retrieval[:5]
    )
    if not source_lines:
        source_lines = "- 未命中具体文件，使用课程默认上下文。"
    return f"""## 课程摘要
Day3 的产品是一个最小桌面 Agent Core：它使用 Day1 的模型路由和 Day2 的 AI Learning Capability Module，通过工具层感知 workspace，基于本地知识库做 RAG 检索，调用硅基流动 LLM 生成摘要、待办、风险和复习卡，并把每一步写入 trace。设备触发网关放在 Day4。

## 待办清单
- 检查 `knowledge/chunk_index.json` 和 `knowledge/retrieval_result.json`，确认 Agent 知道自己检索了什么。
- 检查 Day2 的 `agent_handoff/day2_agent_contract.json`，确认能力模块已变成 Agent 可用动作合约。
- 检查 `summaries/` 和 `cards/`，确认所有写文件动作都留在 workspace 内。
- 将 Day4 的设备触发只调用 `run_day3_agent_core()`，不要把设备网关逻辑写回 Day3。

## 风险清单
- 文件工具如果没有 workspace 边界，会导致越权读写。
- RAG 命中不足时，模型可能用常识补全，必须展示引用来源和 trace。
- Day4 语音或微信入口可能重复触发，所以真正执行文件整理前需要二次确认和幂等记录。

## 引用来源
{source_lines}
"""


def extract_section(markdown: str, title: str, fallback: str) -> str:
    pattern = re.compile(rf"^##\s*{re.escape(title)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return fallback.strip()
    start = match.end()
    next_match = re.search(r"^##\s+", markdown[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip() or fallback.strip()


def build_review_cards(
    summary: str,
    *,
    call_llm: Optional[Callable[..., str]] = None,
    model_text: Optional[str] = None,
    log_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    trace_path: Optional[Path] = None,
) -> List[Dict[str, str]]:
    prompt = f"""
根据下面Day3课程摘要，为 M5Stack CoreS3 复习设备生成3张复习卡。只输出JSON数组，每项包含 question, answer, hint。

课程摘要：
{summary[:4000]}
"""
    raw = call_optional_llm(call_llm, prompt, model=model_text, max_tokens=900)
    if raw:
        try:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                data = json.loads(raw[start : end + 1])
                if isinstance(data, list) and data:
                    cards = [
                        {
                            "question": str(item.get("question", ""))[:140],
                            "answer": str(item.get("answer", ""))[:240],
                            "hint": str(item.get("hint", ""))[:140],
                        }
                        for item in data[:3]
                        if isinstance(item, dict)
                    ]
                    if cards:
                        return cards
        except Exception as exc:
            emit(
                "day3_core.cards_parse_error",
                {"error": f"{type(exc).__name__}: {exc}", "raw": raw[:600]},
                log_event=log_event,
                trace_path=trace_path,
            )

    return [
        {
            "question": "Day3 的 Tool Use 最小闭环包含哪些工具？",
            "answer": "至少包含列目录、读文件、检索知识库、写文件，以及可选的安全移动文件；所有工具都必须限制在 workspace 内。",
            "hint": "感知、检索、行动、安全边界。",
        },
        {
            "question": "Day3 的最小 RAG 是怎么工作的？",
            "answer": "先把本地文本切成 chunk 并写入 chunk_index.json，再按用户意图检索 top-k 片段，把命中片段连同来源交给 LLM 生成结果。",
            "hint": "chunk index + top-k retrieval + sources。",
        },
        {
            "question": "Day3 Agent Core 和 Day4 Device Gateway 的边界是什么？",
            "answer": "Day3 负责 LLM、工具调用、RAG 和本地文件产物；Day4 负责 ESP-Claw/微信/OpenAI-compatible 接口、二次确认、去重和设备日志。",
            "hint": "业务执行在 Day3，设备网关在 Day4。",
        },
    ]


def build_tasks_md(generated: str) -> str:
    extracted = extract_section(
        generated,
        "待办清单",
        "- 检查知识库索引。\n- 检查工具调用 trace。\n- 准备 Day4 设备桥接。",
    )
    return "# Day3 Agent Core 待办\n\n" + extracted + "\n"


def build_risks_md(generated: str) -> str:
    extracted = extract_section(
        generated,
        "风险清单",
        "- 工具越权读写。\n- RAG来源不足导致幻觉。\n- 设备入口重复触发。",
    )
    return "# Day3 Agent Core 风险\n\n" + extracted + "\n"


def render_dashboard(
    package_root: Path,
    workspace: Path,
    result: Dict[str, Any],
    *,
    trace_path: Optional[Path] = None,
) -> None:
    output_path = package_root / "outputs" / "Day3_Agent控制台.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    retrieval = result.get("retrieval", [])
    tools = result.get("tool_calls", [])
    outputs = result.get("outputs", [])
    index_count = result.get("knowledge_chunks", 0)
    rows = []
    trace_lines: List[str] = []
    if trace_path and trace_path.exists():
        trace_lines = trace_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-40:]
    for line in trace_lines:
        try:
            item = json.loads(line)
            rows.append(
                f"<tr><td>{escape(item.get('ts',''))}</td><td>{escape(item.get('type',''))}</td>"
                f"<td><pre>{escape(json.dumps(item.get('payload',{}), ensure_ascii=False, indent=2)[:900])}</pre></td></tr>"
            )
        except Exception:
            rows.append(f"<tr><td colspan='3'><pre>{escape(line)}</pre></td></tr>")

    retrieval_cards = "".join(
        f"<div class='mini'><b>{escape(item['chunk_id'])}</b> <span>{escape(item['source_path'])}</span>"
        f"<p>{escape(item['excerpt'])}</p><em>score={item['score']}</em></div>"
        for item in retrieval
    )
    tool_cards = "".join(
        f"<div class='mini'><b>{escape(call['tool'])}</b><span>{' OK' if call.get('ok') else ' FAIL'}</span>"
        f"<p>{escape(str(call.get('result_preview','')))}</p></div>"
        for call in tools
    )
    output_links = "".join(
        f"<li><a href='agent_workspace/{escape(path)}'>{escape(path)}</a></li>"
        for path in outputs
        if not str(path).startswith("reports/")
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Day3 AgentCore 控制台</title>
  <style>
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#f6f7f9;color:#17202a;line-height:1.55}}
    header{{background:#243746;color:white;padding:30px 38px}} header h1{{margin:0 0 8px;font-size:30px}} header p{{margin:0;color:#dbe4ea;max-width:980px}}
    main{{max-width:1180px;margin:24px auto 48px;padding:0 20px}} .grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
    .panel{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:18px;margin:14px 0}} .kpi{{font-size:26px;font-weight:760}} .muted{{color:#667789}}
    .flow{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;align-items:stretch}} .step{{background:#eef8f6;border:1px solid #b8ded8;border-radius:8px;padding:14px;text-align:center;font-weight:700}}
    .mini{{border:1px solid #d8dee6;background:#fbfcfd;border-radius:8px;padding:12px;margin:8px 0}} .mini span{{color:#667789;margin-left:8px}} .mini p{{margin:8px 0;color:#314252}} .mini em{{color:#667789}}
    .toolbar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} button{{appearance:none;border:0;background:#0f766e;color:white;border-radius:6px;padding:9px 12px;font-weight:700;cursor:pointer}} button.secondary{{background:#334155}} label{{display:flex;gap:6px;align-items:center;color:#334155}}
    .live-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} .status{{color:#667789;font-size:13px}} .warn{{color:#9a3412;background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:10px;margin-top:10px}}
    table{{width:100%;border-collapse:collapse}} td,th{{border:1px solid #d8dee6;padding:8px;vertical-align:top}} pre{{white-space:pre-wrap;word-break:break-word;background:#f8fafc;padding:10px;border-radius:6px;max-height:320px;overflow:auto}}
    a{{color:#0f766e;font-weight:650}} @media(max-width:920px){{.grid,.flow,.live-grid{{grid-template-columns:1fr}}header{{padding:26px 22px}}}}
  </style>
</head>
<body>
<header>
  <h1>Day3 AgentCore 控制台</h1>
  <p>最小桌面 Agent：工具调用、知识库检索、LLM 生成、本地写文件、trace 证据都在一个 workspace 内闭环。</p>
</header>
<main>
  <div class="grid">
    <div class="panel"><div class="kpi">{index_count}</div><div class="muted">知识片段</div></div>
    <div class="panel"><div class="kpi">{len(retrieval)}</div><div class="muted">RAG命中</div></div>
    <div class="panel"><div class="kpi">{len(tools)}</div><div class="muted">工具调用</div></div>
    <div class="panel"><div class="kpi">{len(outputs)}</div><div class="muted">输出产物</div></div>
  </div>
  <div class="panel toolbar">
    <button onclick="loadLiveFiles()">读取最新文件</button>
    <button class="secondary" onclick="location.reload()">刷新页面快照</button>
    <label><input id="autoRefresh" type="checkbox"> 每5秒自动读取</label>
    <span id="liveStatus" class="status">页面加载时间：{escape(now())}</span>
  </div>
  <div class="panel">
    <h2>实时文件快照</h2>
    <p class="muted">这里直接读取 workspace 下的摘要、RAG结果和运行报告。若浏览器阻止 file:// 读取，请运行 `run_day3_agent.command` 后点击“刷新页面快照”。</p>
    <div id="liveWarning"></div>
    <div class="live-grid">
      <div><h3>最新摘要</h3><pre id="liveSummary">等待读取...</pre></div>
      <div><h3>最新运行报告</h3><pre id="liveReport">等待读取...</pre></div>
    </div>
    <h3>最新RAG命中</h3>
    <pre id="liveRetrieval">等待读取...</pre>
  </div>
  <div class="panel">
    <h2>Agent 循环</h2>
    <div class="flow"><div class="step">Perceive<br>列目录/读资料</div><div class="step">Retrieve<br>知识库Top-K</div><div class="step">Reason<br>LLM生成</div><div class="step">Act<br>写文件</div><div class="step">Reflect<br>trace/报告</div></div>
  </div>
  <div class="panel"><h2>Tool Use</h2>{tool_cards or '<p class="muted">暂无工具调用。</p>'}</div>
  <div class="panel"><h2>RAG 检索结果</h2>{retrieval_cards or '<p class="muted">暂无检索命中。</p>'}</div>
  <div class="panel"><h2>Workspace 产物</h2><ul>{output_links}</ul></div>
  <div class="panel"><h2>最近 Trace</h2><table><tr><th>时间</th><th>事件</th><th>内容</th></tr>{''.join(rows)}</table></div>
</main>
<script>
const liveFiles = {{
  summary: "agent_workspace/summaries/course_summary.md",
  retrieval: "agent_workspace/knowledge/retrieval_result.json",
  report: "agent_workspace/reports/agent_run_report.json"
}};
let autoTimer = null;
function textOf(value) {{
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}}
async function readFile(path) {{
  const response = await fetch(path + "?t=" + Date.now(), {{cache: "no-store"}});
  if (!response.ok) throw new Error(path + " HTTP " + response.status);
  return await response.text();
}}
function setText(id, value) {{
  document.getElementById(id).textContent = value;
}}
async function loadLiveFiles() {{
  const status = document.getElementById("liveStatus");
  const warning = document.getElementById("liveWarning");
  warning.innerHTML = "";
  status.textContent = "正在读取最新文件...";
  try {{
    const summary = await readFile(liveFiles.summary);
    const retrievalRaw = await readFile(liveFiles.retrieval);
    const reportRaw = await readFile(liveFiles.report);
    const retrieval = JSON.parse(retrievalRaw);
    const report = JSON.parse(reportRaw);
    setText("liveSummary", summary.slice(0, 2400));
    setText("liveRetrieval", retrieval.map((item, idx) => `${{idx + 1}}. ${{item.chunk_id}} | ${{item.source_path}} | score=${{item.score}}\\n${{item.excerpt}}`).join("\\n\\n"));
    setText("liveReport", JSON.stringify({{
      ts: report.ts,
      intent: report.intent,
      generation_source: report.generation_source,
      knowledge_chunks: report.knowledge_chunks,
      retrieval_hits: (report.retrieval || []).length,
      tool_calls: (report.tool_calls || []).length,
      outputs: report.outputs
    }}, null, 2));
    status.textContent = "已读取最新文件：" + new Date().toLocaleTimeString();
  }} catch (err) {{
    warning.innerHTML = '<div class="warn">当前浏览器阻止直接读取本地文件，或文件尚未生成。可以重新运行 run_day3_agent.command，再点击“刷新页面快照”。错误：' + String(err.message || err) + '</div>';
    status.textContent = "读取失败：" + new Date().toLocaleTimeString();
  }}
}}
document.getElementById("autoRefresh").addEventListener("change", function(event) {{
  if (event.target.checked) {{
    loadLiveFiles();
    autoTimer = setInterval(loadLiveFiles, 5000);
  }} else if (autoTimer) {{
    clearInterval(autoTimer);
    autoTimer = null;
  }}
}});
loadLiveFiles();
</script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def run_day3_agent_core(
    *,
    intent: str,
    workspace: Path,
    course_context: str,
    call_llm: Optional[Callable[..., str]] = None,
    model_agent: Optional[str] = None,
    model_text: Optional[str] = None,
    device_id: str = "local",
    source: str = "manual",
    log_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    trace_path: Optional[Path] = None,
    package_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Day3 Desktop Agent Core.

    It owns LLM calls, local tool use, RAG, workspace outputs, and trace.
    It deliberately does not expose HTTP APIs, ESP-Claw adapters, WeChat
    handlers, or S3 configuration; those belong to Day4.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    for sub in ["summaries", "cards", "knowledge", "reports"]:
        (workspace / sub).mkdir(parents=True, exist_ok=True)

    emit(
        "day3_core.start",
        {"intent": intent, "device_id": device_id, "source": source},
        log_event=log_event,
        trace_path=trace_path,
    )
    tools = ToolRegistry(workspace, log_event=log_event, trace_path=trace_path)
    tools.call("list_files", path=".")

    chunks = build_knowledge_index(workspace, course_context)
    index_content = json.dumps(chunks, ensure_ascii=False, indent=2)
    tools.call("write_file", path="knowledge/chunk_index.json", content=index_content)
    emit(
        "knowledge.index_built",
        {"chunks": len(chunks), "workspace": str(workspace)},
        log_event=log_event,
        trace_path=trace_path,
    )

    query = f"{intent}\nDay2 AI Learning Capability Module agent_handoff 模型路由 多模态上下文 Agent Tool Use RAG 知识库 文件操作 Day4 S3"
    retrieval_result = tools.call("search_workspace", query=query, top_k=6)
    retrieval: List[Dict[str, Any]] = retrieval_result.data if retrieval_result.ok else []
    tools.call("write_file", path="knowledge/retrieval_result.json", content=json.dumps(retrieval, ensure_ascii=False, indent=2))
    emit(
        "rag.retrieve",
        {"query": short(query, 180), "hits": len(retrieval), "top_sources": [item["source_path"] for item in retrieval[:3]]},
        log_event=log_event,
        trace_path=trace_path,
    )

    for item in retrieval[:3]:
        if item["source_type"] == "workspace_file":
            tools.call("read_file", path=item["source_path"], limit=1600)

    prompt = build_agent_prompt(intent, retrieval, course_context)
    generated = call_optional_llm(call_llm, prompt, model=model_agent, max_tokens=1400)
    generation_source = "siliconflow_llm" if generated else "deterministic_fallback"
    if not generated:
        generated = fallback_summary(retrieval)
    emit(
        "llm.generate",
        {"source": generation_source, "model": model_agent or "", "chars": len(generated)},
        log_event=log_event,
        trace_path=trace_path,
    )

    summary_md = "# Day3 Agent Core 课程摘要\n\n" + generated.strip() + "\n"
    tasks_md = build_tasks_md(generated)
    risks_md = build_risks_md(generated)
    cards = build_review_cards(summary_md, call_llm=call_llm, model_text=model_text, log_event=log_event, trace_path=trace_path)
    reply = "Day3桌面Agent已整理完成：摘要、待办、风险和复习卡已更新。可以说“给我一道复习题”。"

    output_files = [
        "summaries/course_summary.md",
        "summaries/tasks.md",
        "summaries/risks.md",
        "cards/review_cards.json",
        "latest_device_reply.txt",
    ]
    tools.call("write_file", path="summaries/course_summary.md", content=summary_md)
    tools.call("write_file", path="summaries/tasks.md", content=tasks_md)
    tools.call("write_file", path="summaries/risks.md", content=risks_md)
    tools.call("write_file", path="cards/review_cards.json", content=json.dumps(cards, ensure_ascii=False, indent=2))
    tools.call("write_file", path="latest_device_reply.txt", content=reply)

    report = {
        "ts": now(),
        "intent": intent,
        "device_id": device_id,
        "source": source,
        "generation_source": generation_source,
        "knowledge_chunks": len(chunks),
        "retrieval": retrieval,
        "tool_manifest": tools.manifest(),
        "tool_calls": tools.calls,
        "outputs": output_files + ["knowledge/chunk_index.json", "knowledge/retrieval_result.json"],
    }
    tools.call("write_file", path="reports/agent_run_report.json", content=json.dumps(report, ensure_ascii=False, indent=2))

    result = {
        "reply": reply,
        "display_text": short(reply),
        "executed": True,
        "outputs": output_files + ["knowledge/chunk_index.json", "knowledge/retrieval_result.json", "reports/agent_run_report.json"],
        "cards": cards,
        "retrieval": retrieval,
        "knowledge_chunks": len(chunks),
        "tool_manifest": tools.manifest(),
        "tool_calls": tools.calls,
        "source": "day3_agent_core",
        "generation_source": generation_source,
        "ts": now(),
    }
    emit(
        "day3_core.completed",
        {"outputs": result["outputs"], "knowledge_chunks": len(chunks), "tool_calls": len(tools.calls)},
        log_event=log_event,
        trace_path=trace_path,
    )

    if package_root is not None:
        render_dashboard(Path(package_root), workspace, result, trace_path=trace_path)

    return result


def read_workspace_context(workspace: Path, limit: int = 12000) -> str:
    parts: List[str] = []
    for path in sorted(workspace.rglob("*")):
        if not is_indexable_file(workspace, path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        parts.append(f"# {relpath(workspace, path)}\n{text[:2500]}")
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n\n".join(parts)[:limit]


def read_upstream_context(package_root: Path, limit: int = 8000) -> str:
    content_root = package_root.parent
    files = [
        content_root / "day1-model-evaluation" / "outputs" / "day1_to_day2_brief.json",
        content_root / "day1-model-evaluation" / "outputs" / "model_selection_playbook.md",
        content_root / "day2-capability-modules" / "outputs" / "product_spec.json",
        content_root / "day2-capability-modules" / "outputs" / "prompt_library.json",
        content_root / "day2-capability-modules" / "outputs" / "context_pack" / "course_seed.md",
        content_root / "day2-capability-modules" / "outputs" / "eval_cases.json",
        content_root / "day2-capability-modules" / "outputs" / "agent_handoff" / "day2_agent_contract.json",
    ]
    parts: List[str] = []
    for path in files:
        if not path.exists():
            continue
        label = str(path.relative_to(content_root)).replace("\\", "/")
        parts.append(f"# upstream/{label}\n{path.read_text(encoding='utf-8', errors='ignore')[:2200]}")
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n\n".join(parts)[:limit]


def main() -> None:
    package_root = Path(__file__).resolve().parent
    default_workspace = package_root / "outputs" / "agent_workspace"
    parser = argparse.ArgumentParser(description="Run Phase1 Day3 desktop AgentCore.")
    parser.add_argument("--intent", default="请整理今天资料，并说明你用了哪些工具和哪些知识来源。")
    parser.add_argument("--workspace", default=str(default_workspace))
    parser.add_argument("--trace", default=str(package_root / "outputs" / "trace_log.jsonl"))
    parser.add_argument("--mock-llm", action="store_true", help="Do not call SiliconFlow; use deterministic fallback output.")
    args = parser.parse_args()

    load_env_file(package_root.parent / "local_siliconflow.env")
    if args.mock_llm:
        os.environ["MOCK_LLM"] = "1"
    os.environ.setdefault("MODEL_AGENT", os.environ.get("MODEL_B", "deepseek-ai/DeepSeek-V4-Flash"))
    os.environ.setdefault("MODEL_TEXT", os.environ.get("MODEL_A", "Pro/moonshotai/Kimi-K2.6"))

    workspace = Path(args.workspace)
    trace_path = Path(args.trace)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")
    context = "\n\n".join(part for part in [read_workspace_context(workspace), read_upstream_context(package_root)] if part.strip())
    call_llm = None if os.environ.get("MOCK_LLM") == "1" else call_siliconflow_direct
    result = run_day3_agent_core(
        intent=args.intent,
        workspace=workspace,
        course_context=context,
        call_llm=call_llm,
        model_agent=os.environ.get("MODEL_AGENT"),
        model_text=os.environ.get("MODEL_TEXT"),
        device_id="student-local",
        source="day3_cli",
        trace_path=trace_path,
        package_root=package_root,
    )
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
