# Phase1 Day3：桌面 Agent Core 实训包

## 本日定位

Day3 负责让学生手搓一个最小桌面 Agent Core。

这个 Agent Core 调用大模型 API，读取和操作本地 workspace，生成摘要、待办、风险、复习卡和 trace。它必须真实体现三件事：

- Tool Use：通过工具注册表调用 `list_files`、`read_file`、`search_workspace`、`write_file`、`move_file`。
- 最小 RAG：把 workspace 文本切成 chunk，写入 `knowledge/chunk_index.json`，再按意图检索 top-k 写入 `knowledge/retrieval_result.json`。
- 安全边界：所有工具只能操作 `outputs/agent_workspace/` 或 Day4 传入的受控 workspace。

它不处理 ESP-Claw、微信、S3，也不暴露 `/v1/chat/completions`。这些设备接入能力固定放到 Day4。

## 主要产物

```text
day3_agent_core.py
run_day3_agent.command
outputs/Day3_Agent控制台.html
outputs/agent_workspace/
outputs/trace_log.jsonl
outputs/after_review.md
outputs/memory.json
```

## 课堂使用

1. 打开 `index.html`。
2. 如需重新生成产物，双击或运行 `run_day3_agent.command`。
3. 进入 `outputs/Day3_Agent控制台.html` 看 Agent 循环；页面顶部有“读取最新文件”“刷新页面快照”和“每5秒自动读取”。
4. 查看 `outputs/agent_workspace/knowledge/` 中的知识库索引和检索结果。
5. 查看 `outputs/agent_workspace/summaries/` 中的摘要、待办、风险。
6. 查看 `outputs/trace_log.jsonl` 解释 Agent 的感知、检索、生成、执行和反馈。

说明：Day3 控制台是本地静态页。浏览器允许时，它会直接读取 `agent_workspace` 下的最新文件；如果浏览器阻止 `file://` 文件读取，就运行 `run_day3_agent.command` 后刷新页面。

## Assessment 证据

- Agent 是否只操作 workspace。
- 是否通过工具注册表完成文件读取、检索和写入。
- 是否生成可解释的最小 RAG 索引和检索结果。
- 是否调用 LLM 生成结构化内容，或在离线模式下给出确定性兜底。
- 是否生成摘要、待办、风险和复习卡。
- 是否保留可追踪 trace。
- 是否明确不承担 Day4 的设备网关职责。

# Day3 实验手册：桌面 Agent Core

> ⏱ 预计时间：20-25 分钟
> 你要把 Day2 定义好的 4 个能力，装进一个真正的"桌面 Agent"里。

---

## 背景

前两天你已经做好了模型选型（Day1）和能力定义（Day2）。但"能力定义"只是纸面上的 JSON 文件——它们还不能自己运行。今天你要写（或运行）一个 Agent 程序，让它真的去读文件、检索知识、调用模型、写结果。

这个 Agent 就是你的产品的大脑。它跑在你的电脑上，工作的区域叫 workspace。

---

## 你的目标

让 Agent 在 workspace 里自主完成一轮任务：读课程资料 → RAG 检索 → 调用模型 → 生成摘要/待办/风险/复习卡 → 写入文件。

做完后 Day4 的设备入口（S3 智能终端/微信）可以触发这个 Agent。

---

## 核心概念

Agent 的工作方式遵循 **ReAct 模式**（Think → Act → Observe → Repeat）：

1. **思考**：LLM 分析当前状态，决定"下一步该调用哪个工具？还是直接回答？"
2. **行动**：执行工具（list/read/search/write），把结果送回 LLM
3. **观察**：LLM 根据工具返回结果，判断继续循环还是任务完成

这个循环可能跑好几轮——Agent 不是一条直线走到底，而是在思考和行动之间反复。

## 操作步骤

### 第一步：看看今天的产物（2 分钟）

双击打开 `index.html`，看看 Agent 控制台长什么样。里面会展示每次 Agent 运行的结果。

### 第二步：运行 Agent（3 分钟）

**Windows:** 双击 `run_day3_agent.bat`
**Mac:** 双击 `run_day3_agent.command`

你会在终端看到 Agent 一步步执行：列出文件 → 检索知识 → 调用模型 → 写摘要 → 写待办 → 写复习卡。每一步都会被记录在 trace_log 里。

### 第三步：看 Agent 的工作成果（5 分钟）

打开 `Day3_Agent控制台.html`，你会看到：

- **摘要** — Agent 读了哪些资料，总结出了什么
- **待办** — Agent 建议你接下来检查什么
- **风险** — Agent 发现了哪些潜在问题
- **复习卡** — Agent 生成了哪些复习题
- **Trace** — 每一步调了什么工具、用了什么知识来源

### 第四步：理解 Agent 的三个核心机制（10 分钟）

| 机制 | 在做什么 | 对应文件 |
|---|---|---|
| Tool Use | 列出目录、读文件、检索知识库、写文件 | 看 trace_log.jsonl 里的 tool 调用 |
| RAG | 把文本切成 chunk，按意图检索 top-k 片段 | `knowledge/chunk_index.json` + `retrieval_result.json` |
| Trace | 每一步都可追踪、可复盘 | `trace_log.jsonl` |

打开 `trace_log.jsonl`，逐条看 Agent 干了什么。

---

## 交付清单

| 必须提交 | 文件路径 | 干什么用 |
|---|---|---|
| 课程摘要 | `agent_workspace/summaries/course_summary.md` | → Day4 读取 |
| 待办 | `agent_workspace/summaries/tasks.md` | 展示用 |
| 风险 | `agent_workspace/summaries/risks.md` | 展示用 |
| 复习卡 | `agent_workspace/cards/review_cards.json` | → Day4 设备展示用 |
| 知识库索引 | `agent_workspace/knowledge/chunk_index.json` | 证据 |
| 检索结果 | `agent_workspace/knowledge/retrieval_result.json` | 证据 |
| 执行记录 | `trace_log.jsonl` | 评估用 |

## 展示方式

打开 `Day3_Agent控制台.html` 投屏，展示：
1. Agent 跑完之后 workspace 里多了哪些文件
2. 挑一个 Tool Use 步骤讲清楚：输入是什么、输出是什么
3. 挑一个 RAG 检索结果：Agent 从哪里找到了相关知识
4. 生成的复习卡能不能在 Day4 设备上用

> 核心问题：如果没有 trace_log，你还能讲清楚 Agent 每一步在干什么吗？

# Day3 学生操作手册

> ⏱ 预计时间：15-20 分钟
> 今天你要跑一个"桌面助手"（Agent）。它不是一个聊天框，是**一个能在你电脑文件夹里读文件、查资料、写结果的程序**。

---

## 你的目标

> 今天你要亲手跑起来一个**最小桌面 Agent**。它做的事是：
> 1. 读你 workspace 里的资料
> 2. 把资料建成知识库
> 3. 根据指令检索相关内容
> 4. 调大模型生成摘要、待办、风险、复习卡
> 5. 把结果写回文件
> 6. 记录每一步做了什么（方便检查）

看不懂的词？→ 去 AI 平台搜"Agent"、"Tool Use"、"RAG"

---

## 准备工作（跳过，前两天的依赖还在）

从 Day1 到现在，你需要的是：
- Python 3.8+（已装）
- `requests` 库（已装）

---

## 第一步：看看今天的目标（1 分钟）

**操作：** 双击打开 `index.html`

**你在看什么：**
- **Agent 控制台** — 跑完之后看成果的地方
- **day3_agent_core.py** — Agent 的源代码（不用改）

---

## 第二步：找到输入文件（1 分钟）

打开 `outputs/agent_workspace/` 文件夹，看看里面有什么：
- `lecture_notes.txt` — 要整理的课程笔记
- `cards/` — 复习卡（Day3 自己生成的）
- `knowledge/` — 知识库（Agent 自己建的）
- `summaries/` — 摘要、待办、风险（Agent 生成的）

**这一步告诉你：** Agent 能操作的只有 workspace 这个文件夹，不会动你电脑上别的东西。

> 🔍 不懂"workspace"？去 AI 平台搜

---

## 第三步：运行 Agent（3 分钟）

**操作：** Windows 双击 `run_day3_agent.bat`，Mac 双击 `run_day3_agent.command`

**你会在终端里看到什么（简化示意）：**
```
📂 list_files → 找到了 lecture_notes.txt、knowledge/
📖 read_file → 读取了课程资料
🔍 search_workspace → 切分知识库、建立索引
🤖 call_llm → 调用大模型生成摘要
✍️ write_file → 写入 summaries/course_summary.md
✓ 完成：生成了摘要、待办、风险、复习卡
```

**这一步在干嘛：**
Agent 在工作区里完整跑了一次"感知→检索→推理→行动→记录"的循环。每一步都打印出来了，你可以看到它做了什么、用了什么工具。

**你要注意什么：**
- Agent 调用了哪些工具？（list_files、read_file、search_workspace、write_file）
- 它是怎么把课程资料变成复习卡的？
- trace 记录在哪里？

> 🔍 不懂"trace"？去 AI 平台搜"Agent Trace"

---

## 第四步：看 Agent 干了什么（5 分钟）

**操作：** 点击 `index.html` 里的 **Agent 控制台**

**你在看什么：**
这个页面展示了完整的 Agent 执行记录：

### Tool Use（工具调用）
| 工具 | 做了什么 | 结果 |
|---|---|---|
| list_files | 列出工作区文件 | 找到了 10 个文件 |
| read_file | 读取课程笔记 | 成功 |
| search_workspace | 检索相关知识 | 命中 3 块内容 |
| write_file | 写复习卡 | 成功 |

### RAG（知识检索）
- 建立了多少块知识索引
- 检索时命中了哪些内容

### 产出文件
- `summaries/course_summary.md` — 课程摘要
- `summaries/tasks.md` — 待办事项
- `summaries/risks.md` — 风险点
- `cards/review_cards.json` — 复习卡

> 🔍 不懂"RAG"？去 AI 平台搜"RAG 检索增强生成"

---

## 第五步：对比 Day2 的合同（3 分钟）

**操作：** 打开 `outputs/agent_workspace/cards/review_cards.json`，看看内容是 JSON 格式吗？

再打开 Day2 的 `outputs/agent_handoff/day2_agent_contract.json`，对比一下：
- Day2 说"复习卡应该长这样" → Day3 真的按这个格式生成了
- 这就是 **Day2 定义、Day3 执行** 的工程分工

> 🔍 不懂"工程分工"？去 AI 平台搜"前后端分离"（原理类似）

---

## 第六步：做你的检查（5 分钟）

打开 `学生任务卡.md`，回答：

1. **Agent 只动了 workspace 里的文件吗？** 检查有没有写到别的地方
2. **它用了哪些工具？** 看控制台的 Tool Use 列表
3. **RAG 检索到了什么？** 打开 `knowledge/retrieval_result.json`
4. **如果没有 Day2 的合同，Agent 知道怎么输出复习卡吗？** → 不知道，所以 Day2 必须先做

---

## 检查自己学会了什么

问自己三个问题：
- Agent 和普通聊天机器人有什么区别？→ **Agent 能操作文件、调用工具、留记录，不只是说话**
- Day3 能不能没有 Day2？→ **不能，没有 Day2 的合同，Agent 不知道输出格式**
- 如果我今天写的资料明天变了，Agent 需要改代码吗？→ **不需要，它每次重新读文件就行，这就是"数据驱动"**

---

## 常见问题

**Agent 跑的时候出现红色报错**
→ 可能是 API Key 没填对。打开 `local_siliconflow.env` 检查 `SILICONFLOW_API_KEY`

**不想调真实模型（怕花钱）**
→ 打开 `local_siliconflow.env`，把 `MOCK_LLM=0` 改成 `MOCK_LLM=1`，再跑一次

**Agent 控制台是空的**
→ 确保先跑了一次程序，让 outputs 文件夹里有生成的文件
