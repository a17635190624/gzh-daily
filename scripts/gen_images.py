#!/usr/bin/env python3
"""
生成图片（通义万相 API）

读当天的 md，提取 3 个配图说明 + 标题，生成 4 张图：
- 配图1（1024×1536 竖图）
- 配图2（1024×1536 竖图）
- 配图3（1536×1024 横图）
- 封面（2048×870 公众号头条 2.35:1，带中文大标题）
"""

import os
import sys
import argparse
import re
import time
from pathlib import Path
import urllib.request
import urllib.error
import json as jsonlib
from io import BytesIO

import requests
import dashscope
from dashscope import ImageSynthesis
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE_DIR / "articles"


def parse_md_for_image_prompts(date: str) -> dict:
    """读当天 md，提取文章标题 + 3 个配图说明 + 副标题钩子"""
    md_files = sorted(ARTICLES_DIR.glob(f"{date}_*.md"))
    if not md_files:
        print(f"❌ 找不到 {date} 的 md 文件")
        sys.exit(1)
    md_path = md_files[0]
    content = md_path.read_text(encoding="utf-8")

    # 标题（第一行 # xxx）
    title_match = re.match(r"#\s+(.+)", content.split("\n")[0])
    title = title_match.group(1).strip() if title_match else ""

    # 提取每个配图位上方那行说明
    img_prompts = []
    for i in (1, 2, 3):
        marker = f"<!-- 配图{i}位 -->"
        if marker not in content:
            img_prompts.append("")
            continue
        # 找 marker 上方的方括号说明 [配图X：...]
        pos = content.find(marker)
        above = content[max(0, pos - 200):pos]
        m = re.search(r"\[配图\d[：:]\s*([^\]]+)\]", above)
        img_prompts.append(m.group(1).strip() if m else "")

    # 找第一个加粗短句作为副标题
    bold_lines = re.findall(r"\*\*([^*]+)\*\*", content)
    sub_title = bold_lines[0] if bold_lines else ""

    return {
        "title": title,
        "sub_title": sub_title,
        "img_prompts": img_prompts,
        "md_path": md_path,
    }


def _submit_task(prompt: str, size: str, n: int = 1, retries: int = 3):
    """用 async_call 提交任务，返回 task_id。提交失败重试（不扣费，因为没拿到任务）"""
    for attempt in range(1, retries + 1):
        try:
            rsp = ImageSynthesis.async_call(
                model="wanx-v1",
                prompt=prompt,
                n=n,
                size=size,
            )
            if rsp.status_code == 200 and getattr(rsp.output, "task_id", None):
                return rsp.output.task_id
            # 非 200 但有 code：直接返回错误信息
            if rsp.status_code != 200:
                msg = getattr(rsp, "message", "") or getattr(rsp, "code", "")
                print(f"    ⚠️ 提交返回非 200：{rsp.code} - {msg}")
                if attempt < retries:
                    time.sleep(8 * attempt)
                    continue
                return None
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ProtocolError,
                TimeoutError) as e:
            print(f"    ⚠️ 第 {attempt}/{retries} 次提交网络错（{type(e).__name__}），重试...")
            if attempt < retries:
                time.sleep(8 * attempt)
                continue
            return None
    return None


def _poll_task(task_id: str, max_waits: int = 12, poll_interval: int = 15):
    """用 fetch 轮询任务状态，返回 (results, status)。网络错则退避重试（同一 task，不重复扣费）"""
    last_status = "PENDING"
    for i in range(1, max_waits + 1):
        try:
            rsp = ImageSynthesis.fetch(task_id)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ProtocolError,
                TimeoutError) as e:
            print(f"    ⚠️ 第 {i}/{max_waits} 次查询网络错（{type(e).__name__}），{poll_interval}s 后重查")
            time.sleep(poll_interval)
            continue

        if rsp.status_code != 200:
            print(f"    ⚠️ 查询返回非 200：{rsp.code} - {rsp.message}")
            time.sleep(poll_interval)
            continue

        status = getattr(rsp.output, "task_status", "RUNNING")
        last_status = status
        if status == "SUCCEEDED":
            results = getattr(rsp.output, "results", None)
            return results, status
        elif status == "FAILED":
            print(f"    ❌ 任务失败：{getattr(rsp, 'code', '')} - {getattr(rsp, 'message', '')}")
            return None, status
        # PENDING / RUNNING：继续等
        if i % 3 == 0:
            print(f"    任务 {status}，已等 {i * poll_interval}s ...")
        time.sleep(poll_interval)

    print(f"    ❌ 轮询超时（{max_waits * poll_interval}s），最后状态 {last_status}")
    return None, last_status


def gen_one_image(api_key: str, prompt: str, size: str, out_path: Path,
                  target_w: int = 0, target_h: int = 0, n: int = 1):
    """调通义万相生成一张图（async_call 提交 + fetch 轮询，全链路重试），再裁到目标比例

    关键设计（避免重复扣费）：
    - async_call() 只提交任务、立即返回 task_id，不阻塞等待 → 提交失败可安全重试（没扣费）
    - fetch() 每次查状态都轻量、独立 → 网络抖动只影响这一次查询，重查同一 task 即可
    - 全程不重复提交任务，同一 task 只扣一次费
    """
    dashscope.api_key = api_key

    print(f"  🎨 生成 {out_path.name}（接口尺寸 {size}）...")
    task_id = _submit_task(prompt, size, n=n)
    if not task_id:
        print(f"  ❌ 提交任务失败，已重试多次，跳过此图")
        sys.exit(1)

    print(f"    任务已提交（{task_id}），轮询中...")
    results, status = _poll_task(task_id)
    if not results:
        print(f"  ❌ 任务未成功（状态 {status}），跳过此图")
        sys.exit(1)

    url = results[0].url
    print(f"    下载图片...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    img_data = urllib.request.urlopen(req, timeout=120).read()

    img = Image.open(BytesIO(img_data)).convert("RGB")

    # 若指定了目标比例，则居中裁剪 + 缩放到目标尺寸
    if target_w > 0 and target_h > 0:
        img = crop_to_aspect(img, target_w, target_h)
        img = img.resize((target_w, target_h), Image.LANCZOS)

    img.save(str(out_path), "PNG")
    print(f"  ✅ 已保存：{out_path.name}（{out_path.stat().st_size // 1024} KB）")


def crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """居中裁剪到目标宽高比（不缩放，只裁切）"""
    target_ratio = target_w / target_h
    w, h = img.size
    ratio = w / h

    if ratio > target_ratio:
        # 比目标更宽 → 裁左右
        new_w = int(h * target_ratio)
        x0 = (w - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, h))
    else:
        # 比目标更高 → 裁上下
        new_h = int(w / target_ratio)
        y0 = (h - new_h) // 2
        return img.crop((0, y0, w, y0 + new_h))


def gen_infographic_prompt(topic: str, hint: str) -> str:
    """配图 prompt（信息图风格，浅米色背景，无真人）"""
    base = f"""Create a clean modern infographic-style illustration about "{topic}".

Hint from article: {hint}.

Style requirements:
- infographic-style, flat design
- light cream/beige background
- no human figures, no portraits, no AI photo
- pure data visualization
- sans-serif Chinese typography (when applicable)
- WeChat public account editorial style
- soft pastel palette
- rounded rectangles
- no watermarks, no AI-generated badges, no model logos
- clean image, professional editorial quality

IMPORTANT: NO human figures, NO portraits, NO photos of people. Abstract data visualization only.
"""
    return base


def gen_cover_prompt(title: str, sub_title: str, topic: str) -> str:
    """封面 prompt（电影感渐变 + 大号中文标题）"""
    title_safe = title.replace('"', "'")[:12]
    sub_safe = sub_title.replace('"', "'").replace("**", "")[:20]

    return f"""A cinematic 8K ultra-HD magazine cover style horizontal hero image for a Chinese WeChat public account article.

Topic: {topic}
Title (must display): "{title_safe}"
Subtitle (must display below title): "{sub_safe}"

Visual direction:
- Dramatic gradient sky from deep midnight indigo at top to warm sunrise coral orange at horizon
- A single bold glowing white exponential growth curve rising from lower-left to upper-right (suggesting compounding/transformation)
- Negative space on the left and upper area for headline text overlay
- Subtle glowing bokeh particles scattered along the curve

Typography:
- Bold Chinese title "{title_safe}" centered, modern sans-serif Chinese font (黑体 / Source Han Sans / Noto Sans CJK style)
- Smaller subtitle "{sub_safe}" below in lighter weight
- White text with strong drop shadow for legibility
- Readable title, NO garbled glyphs, NO boxes, NO broken characters

Style:
- cinematic, 8K ultra HD, magazine cover quality
- dramatic gradient, sharp focus, hyper-detailed
- eye-catching, professional editorial quality
- no human figures, no portraits
- no watermarks, no AI-generated badges, no model logos
- clean image, ready to publish

Aspect ratio: 2.35:1 ultra-wide banner (2048x870)
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 缺少 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    info = parse_md_for_image_prompts(args.date)
    print(f"📰 文章标题：{info['title']}")
    print(f"💬 核心金句：{info['sub_title']}")
    print(f"📷 3 个配图位说明：")
    for i, p in enumerate(info['img_prompts'], 1):
        print(f"   配图{i}：{p}")

    # 生成 3 张配图
    # wanx-v1 仅支持: 1024*1024 / 720*1280 / 768*1152 / 1280*720
    # 用最接近比例的接口尺寸生成，再裁到目标比例
    print(f"\n🖼️  生成 3 张配图...")
    # (接口尺寸, 目标宽, 目标高)
    size_specs = [
        ("768*1152", 1024, 1536),   # 配图1 竖图 (2:3)
        ("768*1152", 1024, 1536),   # 配图2 竖图 (2:3)
        ("1280*720", 1536, 1024),   # 配图3 横图 (3:2)
    ]
    for i, (hint, (api_size, tw, th)) in enumerate(zip(info['img_prompts'], size_specs), 1):
        topic = info['title'] or hint or "认知升级"
        prompt = gen_infographic_prompt(topic, hint)
        out_path = ARTICLES_DIR / f"{args.date}_配图{i}.png"
        gen_one_image(api_key, prompt, api_size, out_path, target_w=tw, target_h=th)

    # 生成封面
    print(f"\n🎬  生成封面...")
    cover_prompt = gen_cover_prompt(info['title'], info['sub_title'], info['title'])
    cover_path = ARTICLES_DIR / f"{args.date}_封面.png"
    # 封面 2048×870 (2.35:1)，用最接近接口尺寸 1280*720 生成后裁到 2048*870
    gen_one_image(api_key, cover_prompt, "1280*720", cover_path, target_w=2048, target_h=870)

    print(f"\n✅ 所有图片已生成")


if __name__ == "__main__":
    main()