"""
多模型视觉识别对比测试
将同一张图片发给硅基流动上的多个视觉大模型，对比识别/描述能力。
"""

import base64
import json
import time
from datetime import datetime
from pathlib import Path

import requests

# ─── 配置 ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / "resources" / "local_siliconflow.env"
OUT = ROOT / "outputs" / "vision_compare"

# 加载 .env
env = {}
for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

API_KEY = env["SILICONFLOW_API_KEY"]
BASE_URL = env.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

# ─── 测试图片 ──────────────────────────────────────────────
IMAGE_PATH = Path(r"C:\Users\xlq20\Documents\Tencent Files\2416667041\nt_qq\nt_data\Pic\2026-06\Ori\d99dadcd558e0a925a9895b29728fb01.png")

# ─── 候选视觉模型 ──────────────────────────────────────────
VISION_MODELS = [
    {"id": "Pro/moonshotai/Kimi-K2.6", "label": "Kimi-K2.6 (Moonshot)"},
    {"id": "Qwen/Qwen3-VL-32B-Instruct", "label": "Qwen3-VL-32B (Alibaba)"},
    {"id": "Qwen/Qwen3-VL-32B-Thinking", "label": "Qwen3-VL-32B-Thinking (Alibaba)"},
    {"id": "PaddlePaddle/PaddleOCR-VL-1.5", "label": "PaddleOCR-VL (OCR专用)"},
]

# 不同维度的 prompt
PROMPTS = [
    {
        "id": "describe",
        "title": "基础描述",
        "text": "请详细描述这张图片里的内容，包括：主体是什么、有什么文字、颜色、布局、氛围等信息。越详细越好。",
    },
    {
        "id": "ocr",
        "title": "文字识别 (OCR)",
        "text": "请提取这张图片中所有的文字内容，保持原文格式和排版。如有表格，用 Markdown 表格格式输出。",
    },
    {
        "id": "analysis",
        "title": "深度分析",
        "text": "请分析这张图片：1) 这是什么类型的图片（截图/海报/文档/照片/UI界面/图表等）？2) 图片想要传达什么信息？3) 你觉得这张图片有什么值得注意的细节或问题？",
    },
]


# ─── 图片转 Base64 ─────────────────────────────────────────
def image_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ─── API 调用 ──────────────────────────────────────────────
def call_vision_model(model_id: str, prompt: str, image_b64: str, max_tokens: int = 2048) -> dict:
    """调用 SiliconFlow 视觉模型"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": False,
    }
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=180,
        )
        elapsed = round(time.time() - t0, 2)
        if resp.status_code == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return {
                "ok": True,
                "text": content,
                "latency": elapsed,
                "usage": usage,
                "model": model_id,
            }
        else:
            return {
                "ok": False,
                "text": f"API错误 [{resp.status_code}]: {resp.text[:500]}",
                "latency": elapsed,
                "usage": {},
                "model": model_id,
            }
    except requests.Timeout:
        return {"ok": False, "text": "请求超时 (180s)", "latency": 180, "usage": {}, "model": model_id}
    except Exception as e:
        return {"ok": False, "text": f"异常: {str(e)}", "latency": 0, "usage": {}, "model": model_id}


# ─── 生成对比 HTML ─────────────────────────────────────────
def render_html(results: list, image_b64: str) -> str:
    """生成带图片的对比报告 HTML"""
    model_blocks = []
    for model_result in results:
        prompt_blocks = []
        for pr in model_result["prompts"]:
            ok_badge = "✅" if pr["ok"] else "❌"
            prompt_blocks.append(f"""
            <div class="prompt-block">
              <h4>{ok_badge} {pr['title']}</h4>
              <span class="meta">延迟 {pr['latency']}s | {pr.get('usage', {}).get('total_tokens', '?')} tokens</span>
              <pre>{chr(10).join(line[:200] for line in pr['text'][:3000].split(chr(10)))}</pre>
            </div>""")

        model_blocks.append(f"""
        <div class="model-card">
          <h3>🤖 {model_result['label']}</h3>
          <p class="model-id">{model_result['id']}</p>
          {''.join(prompt_blocks)}
        </div>""")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>视觉模型对比测试</title>
  <style>
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#f6f7f9;color:#17202a}}
    header{{background:#1a3a4a;color:white;padding:24px 38px}} header h1{{margin:0 0 6px}} header p{{margin:0;color:#bfcdd6}}
    main{{max-width:1400px;margin:20px auto 48px;padding:0 20px}}
    .img-box{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:16px;margin:14px 0;text-align:center}}
    .img-box img{{max-width:100%;max-height:500px;border-radius:4px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px}}
    .model-card{{background:white;border:1px solid #d8dee6;border-radius:8px;padding:16px}}
    .model-card h3{{margin:0 0 4px}} .model-id{{color:#667789;font-size:13px;margin:0 0 12px}}
    .prompt-block{{border:1px solid #e5e8ed;border-radius:6px;padding:12px;margin:10px 0;background:#fbfcfd}}
    .prompt-block h4{{margin:0 0 4px}} .meta{{color:#667789;font-size:12px}}
    pre{{white-space:pre-wrap;font-size:13px;line-height:1.5;max-height:400px;overflow:auto;background:#f5f6f8;padding:10px;border-radius:4px}}
  </style>
</head>
<body>
<header><h1>🔍 多模型视觉识别对比</h1><p>同一张图片 × {len(VISION_MODELS)} 个视觉模型 × {len(PROMPTS)} 个维度</p></header>
<main>
  <div class="img-box">
    <h3>📷 测试图片</h3>
    <img src="data:image/png;base64,{image_b64}" alt="测试图片">
    <p class="meta">1024x559 PNG</p>
  </div>
  <div class="grid">{''.join(model_blocks)}</div>
  <div class="model-card" style="margin-top:16px">
    <h3>📊 对比总结</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr><th style="border:1px solid #d8dee6;padding:8px">模型</th><th style="border:1px solid #d8dee6;padding:8px">描述</th><th style="border:1px solid #d8dee6;padding:8px">OCR</th><th style="border:1px solid #d8dee6;padding:8px">分析</th><th style="border:1px solid #d8dee6;padding:8px">均速</th></tr>
      {''.join(f"<tr><td style='border:1px solid #d8dee6;padding:8px'><b>{r['label']}</b></td>"
               f"<td style='border:1px solid #d8dee6;padding:8px'>{'✅' if r['prompts'][0]['ok'] else '❌'} {r['prompts'][0]['latency']}s</td>"
               f"<td style='border:1px solid #d8dee6;padding:8px'>{'✅' if r['prompts'][1]['ok'] else '❌'} {r['prompts'][1]['latency']}s</td>"
               f"<td style='border:1px solid #d8dee6;padding:8px'>{'✅' if r['prompts'][2]['ok'] else '❌'} {r['prompts'][2]['latency']}s</td>"
               f"<td style='border:1px solid #d8dee6;padding:8px'>{round(sum(p['latency'] for p in r['prompts'])/3,1)}s</td></tr>"
               for r in results)}
    </table>
  </div>
</main>
</body>
</html>"""


# ─── 主流程 ────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🔍 多模型视觉识别对比测试")
    print(f"   图片: {IMAGE_PATH}")
    print(f"   模型: {len(VISION_MODELS)} 个")
    print(f"   维度: {len(PROMPTS)} 个")
    print(f"   总调用: {len(VISION_MODELS) * len(PROMPTS)} 次")
    print("=" * 60)

    # 1. 图片转 base64
    print("\n📷 正在加载图片...")
    image_b64 = image_to_base64(IMAGE_PATH)
    print(f"   Base64 长度: {len(image_b64)} 字符")

    # 2. 逐个模型测试
    all_results = []
    total = len(VISION_MODELS) * len(PROMPTS)
    idx = 0

    for model in VISION_MODELS:
        print(f"\n{'─' * 60}")
        print(f"🤖 {model['label']}")
        print(f"   ID: {model['id']}")
        model_prompts = []

        for prompt in PROMPTS:
            idx += 1
            print(f"\n   [{idx}/{total}] {prompt['title']} ...", end=" ", flush=True)

            result = call_vision_model(model["id"], prompt["text"], image_b64)
            status = "✅" if result["ok"] else "❌"
            tokens = result.get("usage", {}).get("total_tokens", "?")
            print(f"{status} 延迟={result['latency']}s tokens={tokens}")

            if result["ok"]:
                preview = result["text"][:200].replace("\n", " ")
                print(f"   📝 {preview}...")

            model_prompts.append({
                "title": prompt["title"],
                "ok": result["ok"],
                "text": result["text"],
                "latency": result["latency"],
                "usage": result["usage"],
            })

        all_results.append({
            "label": model["label"],
            "id": model["id"],
            "prompts": model_prompts,
        })

    # 3. 保存原始 JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT / f"vision_results_{timestamp}.json"
    json_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n💾 原始结果: {json_path}")

    # 4. 生成 HTML 报告
    html = render_html(all_results, image_b64)
    html_path = OUT / f"vision_compare_{timestamp}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"📄 HTML 报告: {html_path}")

    # 5. 文本总结
    print(f"\n{'=' * 60}")
    print("📊 对比总结")
    print(f"{'=' * 60}")
    for r in all_results:
        ok_count = sum(1 for p in r["prompts"] if p["ok"])
        avg_latency = round(sum(p["latency"] for p in r["prompts"]) / len(r["prompts"]), 1)
        print(f"\n{r['label']}: {ok_count}/{len(PROMPTS)} 成功 | 均速 {avg_latency}s")
        for p in r["prompts"]:
            status = "✅" if p["ok"] else "❌"
            print(f"   {status} {p['title']}: {p['latency']}s | {p.get('usage', {}).get('total_tokens', '?')} tokens")

    print(f"\n📁 所有文件在: {OUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
