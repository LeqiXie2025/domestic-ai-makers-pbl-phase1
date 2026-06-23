# Phase1 Day1：大模型能力矩阵实训包

> 🔍 **开场提问：你看过这种排行榜吗？**
> Chatbot Arena 的 Elo 分、MMLU、HumanEval……这些数字到底代表什么？不同的测评标准怎么来的？最重要的——**通用排名对你有什么意义？**
> Day1 不让你看排行榜，而是让你自己当裁判。从你关心的任务出发，测评国产大模型，做出**属于你自己的路由表**。

## 本日定位

Day1 负责让学生快速建立“国产大模型不是一个抽象名词，而是一组能力差异明显的工程工具”的直觉。

学生当天完成一个可展示、可复用的模型能力评估与路由包：参考答案保留 Kimi-K2.6、DeepSeek-V4-Flash、Qwen3.6-27B，学生也可以选择其他国产大模型作为候选。文本模型和多模态模型分开评估，比较它们在创意、结构化抽取、AI Coding、截图/图像理解和事实诚实性上的表现，并把结论导出给 Day2 能力模块使用。

## 主要产物

```text
day1_arena_builder.py
run_day1_arena.command
outputs/Day1_能力矩阵.html
outputs/Day1_模型能力评估控制台.html
outputs/model_pool_policy.json
outputs/day1_results.json
outputs/model_capability_matrix.json
outputs/day1_to_day2_brief.json
outputs/model_selection_playbook.md
outputs/failure_casebook.md
outputs/student_task_cards.md
```

## 课堂使用

1. 打开 `index.html`。
2. 如需重建证据包，运行 `run_day1_arena.command`。
3. 进入 `Day1_模型能力评估控制台.html`。
4. 用矩阵讲清楚：模型能力、任务适配、失败样本、工程选型。
5. 把 `day1_to_day2_brief.json` 交给 Day2 作为模型路由依据。

## Assessment 证据

- 每个模型对每个任务的原始返回。
- 学生选择候选模型的说明。
- 多模态模型的输入类型、适用边界和失败风险。
- 成功/失败统计。
- 模型差异与可靠性观察。
- 可解释的评分依据。
- Day2 能否使用 Day1 的模型路由，而不是重新凭感觉选模型。

# Day1 学生操作手册

> ⏱ 预计时间：25-35 分钟（含等模型返回的时间）
> 不需要会编程，跟着做就行。

---

## 开场：你看过这种排行榜吗？

你刷手机的时候有没有见过这种图：

```
Chatbot Arena 排行榜
#1  Gemini 2.5 Pro    Elo 1422
#2  GPT-5             Elo 1418
#3  Claude 4          Elo 1408
#4  DeepSeek R2       Elo 1395
...
```

这些分数代表什么？Elo 是什么？用什么题目测的？**最重要的是——这些排名对你来说有意义吗？**

> 🔍 不懂的词（Elo、MMLU、HumanEval、benchmark）→ 去 AI 教学平台搜。

---

## 今天的目标

不看排行榜，**你自己做裁判**。从你关心的实际问题出发，拿几个国产大模型来测一测，排出一张**属于你自己的路由表**。

做完后你会产出 `day1_to_day2_brief.json`——这张表明天会用到，告诉 Day2 "什么任务该用哪个模型"。

---

## 准备工作（5 分钟）

### ① 确保有 Python
打开终端（Windows 按 Win 键输入 `cmd` 回车；Mac 按 Command+空格输入 `终端` 回车）：

```
python --version
```

看到 `Python 3.8` 或更高 → 继续。
如果报错 → 去 https://www.python.org/downloads/ 下载安装（勾选"Add Python to PATH"），装完重启终端。

### ② 装依赖
```
python -m pip install requests
```
看到 `Successfully installed` 就行。

### ③ 打开入口
双击 `index.html`，看一眼今天的目标产物长什么样。

---

## 第一步：设计你的任务（5 分钟）

**我们要测评什么？不能凭空选模型，必须从你要它干的具体事情出发。**

想 5 个任务——挑你日常生活/学习中真正会遇到的事：

| 任务类型 | 举例 |
|---|---|
| 写点有创意的东西 | 「帮我写一条朋友圈文案，宣传我们社团招新」 |
| 整理信息 | 「把这段课堂笔记整理成 3 个要点」 |
| 查一段代码的问题 | 「这段 Python 哪里不对，帮我修」 |
| 判断事实对错 | 「有人说空腹喝牛奶伤胃，对吗」 |
| 看一张图/截图 | 「这张课程表截图里，周三下午有什么课」 |

> 要求：每个任务一句话说清楚。这些就是你的**测试题**。

---

## 第二步：选模型（2 分钟）

选 3 个国产大模型来跑你的题。老师提供了参考答案：
- **Kimi (Moonshot)** — moonshot.cn
- **DeepSeek** — deepseek.com
- **Qwen (Alibaba)** — tongyi.aliyun.com

你可以用这三个，也可以换别的。去它们的官网注册，拿到 **API Key**（一般在"控制台"→"API密钥"）。

> 🔍 不懂 API Key 是什么 → 去 AI 教学平台搜

---

## 第三步：跑评测（10 分钟）

**你需要让每个模型回答你的每个题目。有几种做法：**

**方案A（最简单）：用老师提供的 Python 脚本自动跑**
1. 打开 `resources/local_siliconflow.env`，把你的 API Key 填进去
2. 把 `MOCK_LLM=0` 改成 `MOCK_LLM=0`（真跑模式）
3. 双击 `run_day1_arena.command`（Mac）或 `run_day1_arena.bat`（Windows）
4. 等待终端跑完，每个模型对每个题目的回答都会记录下来

**方案B（自己调用）：**
写一个简单的 Python 调 API（去 AI 教学平台搜「Python 调用大模型 API 示例」），或者去模型官网的「体验中心」手动输入题目，把每个结果截图保存。

> 关键：**每个模型×每个题目的回答，都要保留原始文本。** 这是评测证据。

---

## 第四步：打分（5 分钟）

跑完之后，打开 `outputs/day1_results.json`，你会看到类似这样的数据：

```
任务：社团招新文案 → Kimi → 5分
任务：社团招新文案 → DeepSeek → 4分
任务：社团招新文案 → Qwen → 3分
...
```

**给每个结果打分（1-5）：**
- 5 分：完全符合要求，可以直接用
- 3 分：方向对，但需要改
- 1 分：完全不对，或者跑崩了

如果你用的是方案B（手动跑），就用 Python 处理模型回答，把分数和原始回答整理成 `day1_results.json` 的格式。然后把真实的回答填进去。

> 如果有空文件或没法解析的 JSON → 标记 1 分。失败样本和成功样本同样重要！

---

## 第五步：看结果，做决策（5 分钟）

运行 `python3 day1_arena_builder.py`，程序会读取你的 `day1_results.json` 并生成：

- `Day1_模型能力评估控制台.html` — 可视化矩阵
- `day1_to_day2_brief.json` — **路由表**（明天要用）

打开控制台 HTML，回答三个问题：

1. **哪个模型在什么任务上表现最好？** 举例：Kimi 写文案强，DeepSeek 写代码强
2. **有没有模型在某个任务上翻车？** 为什么会翻车？
3. **如果明天只能让一个模型做所有事，什么会出问题？** → 所以需要路由

把你的结论写成 `student_task_cards.md`（已经有模板）。

---

## 检查自己学会了什么

- 排行榜上的 Elo 分数和你的测评结果有什么关系？→ **排行榜是通用场景，你的测评针对你自己的需求**
- 有没有一个模型在所有任务上都最强？→ **没有，所以要路由**
- 你做的路由表，明天谁会用到？→ **Day2 的能力模块**

---

## 常见问题

**双击 .bat 闪了一下就没了**
→ Python 没装好或没勾选"Add Python to PATH"，重装

**终端报错 `ModuleNotFoundError`**
→ 运行 `python -m pip install requests`

**我就是不想写代码**
→ 用方案B：去模型官网的网页端逐个输入题目，截图保存，然后对照 `day1_results.json` 的格式手动填一张表（共15行：3个模型×5个任务）

**我拿到 API Key 但不知道往哪填**
→ 打开 `resources/local_siliconflow.env`，把 `sk-xxx` 替换成你的 key


---

## 交付清单

| 必须提交 | 文件名 | 干什么用 |
|---|---|---|
| 原始评测数据 | `day1_results.json` | 保留每个模型×每道题的原始回答 |
| 路由决策表 | `day1_to_day2_brief.json` | Day2 读这个选模型 |
| 评测矩阵 | `model_capability_matrix.json` | 展示用 |
| 失败样本 | `failure_casebook.md` | 记录翻车案例 |

## 展示方式

结束后打开 `Day1_模型能力评估控制台.html`，投屏展示：
1. 你选了哪几个模型、为什么
2. 能力矩阵里哪个模型在哪项任务上最强
3. 有没有翻车的案例，你的 fallback 方案是什么
4. 你的路由表交给 Day2 后，Day2 能用它做什么

> 提示：展示时重点讲**你的判断**，而不是照着念数据。

# Day1 学生操作手册

> ⏱ 预计时间：25-35 分钟（含等模型返回的时间）
> 不需要会编程，跟着做就行。

---

## 开场：你看过这种排行榜吗？

你刷手机的时候有没有见过这种图：

```
Chatbot Arena 排行榜
#1  Gemini 2.5 Pro    Elo 1422
#2  GPT-5             Elo 1418
#3  Claude 4          Elo 1408
#4  DeepSeek R2       Elo 1395
...
```

这些分数代表什么？Elo 是什么？用什么题目测的？**最重要的是——这些排名对你来说有意义吗？**

> 🔍 不懂的词（Elo、MMLU、HumanEval、benchmark）→ 去 AI 教学平台搜。

---

## 今天的目标

不看排行榜，**你自己做裁判**。从你关心的实际问题出发，拿几个国产大模型来测一测，排出一张**属于你自己的路由表**。

做完后你会产出 `day1_to_day2_brief.json`——这张表明天会用到，告诉 Day2 "什么任务该用哪个模型"。

---

## 准备工作（5 分钟）

### ① 确保有 Python
打开终端（Windows 按 Win 键输入 `cmd` 回车；Mac 按 Command+空格输入 `终端` 回车）：

```
python --version
```

看到 `Python 3.8` 或更高 → 继续。
如果报错 → 去 https://www.python.org/downloads/ 下载安装（勾选"Add Python to PATH"），装完重启终端。

### ② 装依赖
```
python -m pip install requests
```
看到 `Successfully installed` 就行。

### ③ 打开入口
双击 `index.html`，看一眼今天的目标产物长什么样。

---

## 第一步：设计你的任务（5 分钟）

**我们要测评什么？不能凭空选模型，必须从你要它干的具体事情出发。**

想 5 个任务——挑你日常生活/学习中真正会遇到的事：

| 任务类型 | 举例 |
|---|---|
| 写点有创意的东西 | 「帮我写一条朋友圈文案，宣传我们社团招新」 |
| 整理信息 | 「把这段课堂笔记整理成 3 个要点」 |
| 查一段代码的问题 | 「这段 Python 哪里不对，帮我修」 |
| 判断事实对错 | 「有人说空腹喝牛奶伤胃，对吗」 |
| 看一张图/截图 | 「这张课程表截图里，周三下午有什么课」 |

> 要求：每个任务一句话说清楚。这些就是你的**测试题**。

---

## 第二步：选模型（2 分钟）

选 3 个国产大模型来跑你的题。老师提供了参考答案：
- **Kimi (Moonshot)** — moonshot.cn
- **DeepSeek** — deepseek.com
- **Qwen (Alibaba)** — tongyi.aliyun.com

你可以用这三个，也可以换别的。去它们的官网注册，拿到 **API Key**（一般在"控制台"→"API密钥"）。

> 🔍 不懂 API Key 是什么 → 去 AI 教学平台搜

---

## 第三步：跑评测（10 分钟）

**你需要让每个模型回答你的每个题目。有几种做法：**

**方案A（最简单）：用老师提供的 Python 脚本自动跑**
1. 打开 `resources/local_siliconflow.env`，把你的 API Key 填进去
2. 把 `MOCK_LLM=0` 改成 `MOCK_LLM=0`（真跑模式）
3. 双击 `run_day1_arena.command`（Mac）或 `run_day1_arena.bat`（Windows）
4. 等待终端跑完，每个模型对每个题目的回答都会记录下来

**方案B（自己调用）：**
写一个简单的 Python 调 API（去 AI 教学平台搜「Python 调用大模型 API 示例」），或者去模型官网的「体验中心」手动输入题目，把每个结果截图保存。

> 关键：**每个模型×每个题目的回答，都要保留原始文本。** 这是评测证据。

---

## 第四步：打分（5 分钟）

跑完之后，打开 `outputs/day1_results.json`，你会看到类似这样的数据：

```
任务：社团招新文案 → Kimi → 5分
任务：社团招新文案 → DeepSeek → 4分
任务：社团招新文案 → Qwen → 3分
...
```

**给每个结果打分（1-5）：**
- 5 分：完全符合要求，可以直接用
- 3 分：方向对，但需要改
- 1 分：完全不对，或者跑崩了

如果你用的是方案B（手动跑），就用 Python 处理模型回答，把分数和原始回答整理成 `day1_results.json` 的格式。然后把真实的回答填进去。

> 如果有空文件或没法解析的 JSON → 标记 1 分。失败样本和成功样本同样重要！

---

## 第五步：看结果，做决策（5 分钟）

运行 `python3 day1_arena_builder.py`，程序会读取你的 `day1_results.json` 并生成：

- `Day1_模型能力评估控制台.html` — 可视化矩阵
- `day1_to_day2_brief.json` — **路由表**（明天要用）

打开控制台 HTML，回答三个问题：

1. **哪个模型在什么任务上表现最好？** 举例：Kimi 写文案强，DeepSeek 写代码强
2. **有没有模型在某个任务上翻车？** 为什么会翻车？
3. **如果明天只能让一个模型做所有事，什么会出问题？** → 所以需要路由

把你的结论写成 `student_task_cards.md`（已经有模板）。

---

## 检查自己学会了什么

- 排行榜上的 Elo 分数和你的测评结果有什么关系？→ **排行榜是通用场景，你的测评针对你自己的需求**
- 有没有一个模型在所有任务上都最强？→ **没有，所以要路由**
- 你做的路由表，明天谁会用到？→ **Day2 的能力模块**

---

## 常见问题

**双击 .bat 闪了一下就没了**
→ Python 没装好或没勾选"Add Python to PATH"，重装

**终端报错 `ModuleNotFoundError`**
→ 运行 `python -m pip install requests`

**我就是不想写代码**
→ 用方案B：去模型官网的网页端逐个输入题目，截图保存，然后对照 `day1_results.json` 的格式手动填一张表（共15行：3个模型×5个任务）

**我拿到 API Key 但不知道往哪填**
→ 打开 `resources/local_siliconflow.env`，把 `sk-xxx` 替换成你的 key
