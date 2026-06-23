# Phase1 Day2：AI 学习产品能力模块实训包

## 本日定位

Day2 负责把 Prompt Engineering、Context Engineering、结构化输出、多模态上下文抽取和 AI Coding 从“技巧清单”变成一个可被 Day3 调用的 AI 学习产品能力模块。

学生当天产物是 StudyFlow S3 的 AI Learning Capability Module：它有提示词库、上下文包、JSON Schema、多模态上下文 Schema、评测用例、可运行能力模块和 Day3 Agent Handoff Contract。

## 主要产物

```text
run_day2_engine.command
pocket_review_engine.py
outputs/Day2_产品控制台.html
outputs/Day2_产品Demo.html
outputs/product_spec.json
outputs/prompt_library.json
outputs/context_pack/
outputs/schemas/
outputs/eval_cases.json
outputs/engine_run_report.json
outputs/agent_handoff/day2_agent_contract.json
outputs/engineering_critique.md
outputs/demo_run_before_day3.txt
outputs/demo_run_after_day3.txt
outputs/pocket_review_cli.py
```

## 课堂使用

1. 打开 `index.html`。
2. 如需重建能力模块，运行 `run_day2_engine.command`。
3. 先看 `Day2_产品控制台.html`，让学生感知 Prompt-to-Product 的工程结果。
4. 再打开 `prompt_library.json`、`schemas/`、`eval_cases.json` 和 `agent_handoff/day2_agent_contract.json`。
5. 说明 Day3 如何读取 Day2 的能力模块，并把它放入 Tool Use/RAG。

## Assessment 证据

- Prompt Library 是否覆盖系统提示词、任务提示词、修复提示词和 handoff 提示词。
- Context Pack 是否包含 Day1 模型路由、设备限制和多模态上下文要求。
- JSON Schema 是否能约束复习卡、答题评分和 Agent handoff。
- 多模态上下文 Schema 是否能约束截图、图像、板书或设备界面的抽取结果。
- Eval Cases 是否能检查格式稳定性和回答质量。
- Day3 是否能读取 `agent_handoff/day2_agent_contract.json`。

# Day2 学生操作手册

> ⏱ 预计时间：10-15 分钟
> 不做编码，只看成果。你要理解"把一段文字描述变成一个能被程序调用的产品功能"是怎么回事。

---

## 你的目标

> 昨天你评测出了哪个模型擅长什么。今天你要把评测结果**变成 4 个真正能用的 AI 功能**——复习卡生成、答题评分、多模态上下文抽取、Agent 交接。
> 这 4 个功能以 JSON 文件的形式存在，Day3 的 Agent 会直接读取使用。

看不懂的词？→ 去 AI 平台搜"JSON"、"Schema"、"Prompt Engineering"

---

## 准备工作（跳过，Day1 做过了）

如果 Day1 装过 Python 和依赖了，直接开始。

---

## 第一步：看看今天的产物（2 分钟）

**操作：** 双击打开 `index.html`

**你在看什么：**
- **产品控制台** — 汇总展示今天所有产出
- **Prompt Library** — 6 条写好的 Prompt（提示词）
- **Agent Handoff** — 给 Day3 的"合同文件"

> 🔍 不懂"Prompt"？去 AI 平台搜

---

## 第二步：打开能力展示页面（5 分钟）

**操作：** 点击**打开能力展示**（或直接打开 `outputs/Day2_能力模块展示.html`）

**你在看什么：**
这个页面有 6 个 Tab，从头看到尾：

### 📊 总览
- 顶部的数字：**6 条 Prompt、4 个能力定义、4 个评测用例**
- 下面的表格：Day1 的路由表（哪个任务用哪个模型）
- Agent 合同摘要：Day3 会用到哪 4 个动作

### ⚡ 4 个能力
点开看每个能力卡片的输入和输出：

| 能力 | 输入 | 输出 |
|---|---|---|
| 复习卡生成 | 课程资料 | 一组复习卡（JSON） |
| 答题评分 | 题目 + 学生答案 | 分数和评语 |
| 多模态上下文 | 截图描述 | 结构化观察结果 |
| 设备回复 | 用户意图 | 短文本回复 |

**这一步告诉你：**
- 每个功能都定义了"输入什么、输出什么、写到哪里"
- Day3 的 Agent 按照这个定义来干活

### 📝 Prompt 库
6 条 Prompt 分别干什么：
- **system 类型** — 定义助手角色和规则
- **task 类型** — 具体任务的指令
- **repair 类型** — JSON 出错时自动修复
- **handoff 类型** — 告诉 Agent 有哪些功能可用

**关键理解：** Prompt 不只是"问问题"，它是**工程接口**——规定了模型必须输出什么格式、不能做什么。

> 🔍 不懂"system prompt"？去 AI 平台搜

### 📐 数据格式
每个 Schema 定义了输出的 JSON 必须长什么样——哪些字段必须有、字段是什么类型。

**关键理解：** Schema 就是"格式合同"。模型不按这个格式输出，Day3 的 Agent 就读不懂。

> 🔍 不懂"JSON Schema"？去 AI 平台搜

### ✅ 评测用例
每个测试用例展示：输入了什么 → 期望输出什么 → 实际输出了什么

**关键理解：** 这些测试用例保证了 Day2 产出的 Prompt 是可靠的。如果某条 Prompt 跑出来的结果不符合预期，需要修改。

---

## 第三步：看 Day3 会拿到什么（3 分钟）

**操作：** 打开 `outputs/agent_handoff/day2_agent_contract.json`

**你在看什么：**
这是一个"交接合同"，Day3 的 Agent 启动时读它。里面写着：

```json
"actions": [
  {"name": "generate_review_cards", "input": "...", "output": "...", "writes": "..."},
  {"name": "grade_answer", "input": "...", "output": "...", "writes": "..."},
  ...
]
```

**这一步告诉你：** Day2 和 Day3 的接口就是一份 JSON 文件。Day3 不需要关心 Day2 内部怎么实现的，只要知道"我有 4 个动作可以用，每个动作的输入输出是什么"就够了。

---

## 第四步：做你的检查（5 分钟）

打开 `学生任务卡.md`，回答：

1. **Prompt 库够用吗？** 所有场景都覆盖了吗
2. **Schema 写全了吗？** 如果缺少某个字段，Day3 会读不到
3. **评测用例通过了吗？** 打开 `eval_cases.json` 看看
4. **最关键的问题：如果没有这些 JSON 文件（没有格式定义、没有 Prompt 库），Day3 的 Agent 能干活吗？** → 不能，这就是 Day2 存在的意义

---

## 检查自己学会了什么

问自己三个问题：
- Day2 产出的"4 个能力"是运行着的程序吗？→ **不是，是定义文件（JSON），Day3 才真正运行**
- 为什么要把输出格式定义成 JSON？→ **因为机器读得懂，Day3 的 Agent 可以自动处理**
- 你和隔壁组的合同文件能互换吗？→ **如果 Schema 一样就能，这就是"接口标准化"**

---

## 常见问题

**能力展示页面是空白的**
→ 确保打开了正确的文件路径 `outputs/Day2_能力模块展示.html`

**看不懂 JSON 格式**
→ 去 AI 平台搜"JSON 格式入门"

**什么是 Handoff？**
→ 就是"交接"。Day2 写一份说明书交给 Day3，说"我有这些功能，你拿去用"



---

## 交付清单

| 必须提交 | 文件名 | 干什么用 |
|---|---|---|
| 产品规格 | `product_spec.json` | 你的产品叫什么、解决什么问题 |
| Prompt 库 | `prompt_library.json` | 至少 4 条系统/任务 Prompt |
| 评测用例 | `eval_cases.json` | 证明你的 Prompt 能跑出预期结果 |
| **Agent 合同** | `agent_handoff/day2_agent_contract.json` | → Day3 直接读 |
| 复习卡 Schema | `schemas/review_card.schema.json` | 格式约束 |
| 答题评分 Schema | `schemas/answer_grading.schema.json` | 格式约束 |
| 多模态 Schema | `schemas/multimodal_observation.schema.json` | 格式约束 |

## 展示方式

打开 `Day2_产品控制台.html`，投屏展示：
1. 你的产品叫什么、给谁用、解决什么问题
2. 4 个能力分别输入什么、输出什么
3. Prompt Library 里最关键的那条 Prompt，展示输入→输出
4. Agent 合同文件——Day3 会怎么用你的这 4 个动作

> 核心问题：如果没有 Prompt 库和 Schema，Day3 的 Agent 能正确执行吗？

# Day2 学生操作手册

> ⏱ 预计时间：10-15 分钟
> 不做编码，只看成果。你要理解"把一段文字描述变成一个能被程序调用的产品功能"是怎么回事。

---

## 你的目标

> 昨天你评测出了哪个模型擅长什么。今天你要把评测结果**变成 4 个真正能用的 AI 功能**——复习卡生成、答题评分、多模态上下文抽取、Agent 交接。
> 这 4 个功能以 JSON 文件的形式存在，Day3 的 Agent 会直接读取使用。

看不懂的词？→ 去 AI 平台搜"JSON"、"Schema"、"Prompt Engineering"

---

## 准备工作（跳过，Day1 做过了）

如果 Day1 装过 Python 和依赖了，直接开始。

---

## 第一步：看看今天的产物（2 分钟）

**操作：** 双击打开 `index.html`

**你在看什么：**
- **产品控制台** — 汇总展示今天所有产出
- **Prompt Library** — 6 条写好的 Prompt（提示词）
- **Agent Handoff** — 给 Day3 的"合同文件"

> 🔍 不懂"Prompt"？去 AI 平台搜

---

## 第二步：打开能力展示页面（5 分钟）

**操作：** 点击**打开能力展示**（或直接打开 `outputs/Day2_能力模块展示.html`）

**你在看什么：**
这个页面有 6 个 Tab，从头看到尾：

### 📊 总览
- 顶部的数字：**6 条 Prompt、4 个能力定义、4 个评测用例**
- 下面的表格：Day1 的路由表（哪个任务用哪个模型）
- Agent 合同摘要：Day3 会用到哪 4 个动作

### ⚡ 4 个能力
点开看每个能力卡片的输入和输出：

| 能力 | 输入 | 输出 |
|---|---|---|
| 复习卡生成 | 课程资料 | 一组复习卡（JSON） |
| 答题评分 | 题目 + 学生答案 | 分数和评语 |
| 多模态上下文 | 截图描述 | 结构化观察结果 |
| 设备回复 | 用户意图 | 短文本回复 |

**这一步告诉你：**
- 每个功能都定义了"输入什么、输出什么、写到哪里"
- Day3 的 Agent 按照这个定义来干活

### 📝 Prompt 库
6 条 Prompt 分别干什么：
- **system 类型** — 定义助手角色和规则
- **task 类型** — 具体任务的指令
- **repair 类型** — JSON 出错时自动修复
- **handoff 类型** — 告诉 Agent 有哪些功能可用

**关键理解：** Prompt 不只是"问问题"，它是**工程接口**——规定了模型必须输出什么格式、不能做什么。

> 🔍 不懂"system prompt"？去 AI 平台搜

### 📐 数据格式
每个 Schema 定义了输出的 JSON 必须长什么样——哪些字段必须有、字段是什么类型。

**关键理解：** Schema 就是"格式合同"。模型不按这个格式输出，Day3 的 Agent 就读不懂。

> 🔍 不懂"JSON Schema"？去 AI 平台搜

### ✅ 评测用例
每个测试用例展示：输入了什么 → 期望输出什么 → 实际输出了什么

**关键理解：** 这些测试用例保证了 Day2 产出的 Prompt 是可靠的。如果某条 Prompt 跑出来的结果不符合预期，需要修改。

---

## 第三步：看 Day3 会拿到什么（3 分钟）

**操作：** 打开 `outputs/agent_handoff/day2_agent_contract.json`

**你在看什么：**
这是一个"交接合同"，Day3 的 Agent 启动时读它。里面写着：

```json
"actions": [
  {"name": "generate_review_cards", "input": "...", "output": "...", "writes": "..."},
  {"name": "grade_answer", "input": "...", "output": "...", "writes": "..."},
  ...
]
```

**这一步告诉你：** Day2 和 Day3 的接口就是一份 JSON 文件。Day3 不需要关心 Day2 内部怎么实现的，只要知道"我有 4 个动作可以用，每个动作的输入输出是什么"就够了。

---

## 第四步：做你的检查（5 分钟）

打开 `学生任务卡.md`，回答：

1. **Prompt 库够用吗？** 所有场景都覆盖了吗
2. **Schema 写全了吗？** 如果缺少某个字段，Day3 会读不到
3. **评测用例通过了吗？** 打开 `eval_cases.json` 看看
4. **最关键的问题：如果没有这些 JSON 文件（没有格式定义、没有 Prompt 库），Day3 的 Agent 能干活吗？** → 不能，这就是 Day2 存在的意义

---

## 检查自己学会了什么

问自己三个问题：
- Day2 产出的"4 个能力"是运行着的程序吗？→ **不是，是定义文件（JSON），Day3 才真正运行**
- 为什么要把输出格式定义成 JSON？→ **因为机器读得懂，Day3 的 Agent 可以自动处理**
- 你和隔壁组的合同文件能互换吗？→ **如果 Schema 一样就能，这就是"接口标准化"**

---

## 常见问题

**能力展示页面是空白的**
→ 确保打开了正确的文件路径 `outputs/Day2_能力模块展示.html`

**看不懂 JSON 格式**
→ 去 AI 平台搜"JSON 格式入门"

**什么是 Handoff？**
→ 就是"交接"。Day2 写一份说明书交给 Day3，说"我有这些功能，你拿去用"
