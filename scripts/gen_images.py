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

import dashscope
from dashscope import ImageSynthesis


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


def gen_one_image(api_key: str, prompt: str, size: str, out_path: Path, n: int = 1):
    """调通义万相生成一张图"""
    dashscope.api_key = api_key

    print(f"  🎨 生成 {out_path.name} ({size})...")
    rsp = ImageSynthesis.call(
        model="wanx-v1",
        prompt=prompt,
        n=n,
        size=size,
        steps=30,
    )

    if rsp.status_code != 200:
        print(f"❌ 生成失败：{rsp.code} - {rsp.message}")
        sys.exit(1)

    url = rsp.output.results[0].url
    urllib.request.urlretrieve(url, str(out_path))
    print(f"  ✅ 已保存：{out_path.name}（{out_path.stat().st_size // 1024} KB）")


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
    print(f"\n🖼️  生成 3 张配图...")
    size_map = ["1024*1536", "1024*1536", "1536*1024"]
    for i, (hint, size) in enumerate(zip(info['img_prompts'], size_map), 1):
        topic = info['title'] or hint or "认知升级"
        prompt = gen_infographic_prompt(topic, hint)
        out_path = ARTICLES_DIR / f"{args.date}_配图{i}.png"
        gen_one_image(api_key, prompt, size, out_path)

    # 生成封面
    print(f"\n🎬  生成封面...")
    cover_prompt = gen_cover_prompt(info['title'], info['sub_title'], info['title'])
    cover_path = ARTICLES_DIR / f"{args.date}_封面.png"
    gen_one_image(api_key, cover_prompt, "2048*870", cover_path)

    print(f"\n✅ 所有图片已生成")


if __name__ == "__main__":
    main()