#!/usr/bin/env python3
"""
生成文章（DeepSeek API）

按选定的选题 + 调性约束，生成 1200-1800 字公众号长文。
输出：`articles/YYYY-MM-DD_<标题>.md`
"""

import os
import sys
import argparse
import re
from pathlib import Path

import openai


BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE_DIR / "articles"


def generate_article(date: str, topic: str) -> Path:
    """生成文章并保存，返回 markdown 路径"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 缺少 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    system_prompt = """你是公众号文章润色编辑，专精"认知升级 / 个人成长 / 复利 / 反常识"方向。

# 调性硬约束（违反任一即重写）
- **绝不出现具体金额**（禁"月薪 X 元""存下 X 万""房租 X 元"）
- 不堆砌焦虑词（禁"内卷""35岁危机""同龄人抛弃你"）
- 不写记账 / 账单 / 收支明细
- 不出现具体股票代码、基金代码、ETF 代码
- 不用绝对化用词（禁"最""第一""100%""唯一""顶级"）
- 不写诱导分享/关注/点赞/抽奖
- 不贬低任何具体品牌
- 标题不与正文严重不符

# 文章结构
- **导语**：1-2 句话钩子（朋友的故事 / 反常识视角 / 共情场景）—— 不出现具体金额
- **正文**：3-4 段，每段一个小观点；穿插加粗金句（"X 是显性，Y 才是隐性"这类短句节奏）
- **结尾互动提问**：1 个聚焦、可回答的动作类问题
- 字数 1200-1800 字，口语化、有钩子、有金句、不堆砌情绪词、不给焦虑感

# 配图位置标记
文中必须保留 3 个配图位置标记（每个位置上方 1 句说明该图用途）：

- `<!-- 配图1位 -->` 配图1：核心数据/对比图（如四象限、复利曲线、高手 vs 普通对比）
- `<!-- 配图2位 -->` 配图2：复利曲线/时间轴/方法对比清单
- `<!-- 配图3位 -->` 配图3：3-4 步流程/方法图（可直接执行的动作链）

每个位置上方 1 句简短说明该图用途，例如：
```
[配图1：本文核心概念「四类资产」的四象限气泡图，呼应金句"工资只占 1/4"]
<!-- 配图1位 -->
```

# 输出格式
直接输出 Markdown 正文，不要前缀说明、不要 ```markdown 包裹。
开头第一行就是文章标题（# 一级标题），后面直接接正文。
"""

    user_prompt = f"""日期：{date}
选题：《{topic}》

请基于这个选题，按上述调性、结构、配图位置要求，输出一篇完整的公众号长文。
"""

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
    )

    print("🤖 调用 DeepSeek 生成文章...")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1.2,
        max_tokens=3500,
    )

    content = response.choices[0].message.content.strip()

    # 提取标题（第一行 # xxx）
    title_match = re.match(r"#\s+(.+)", content.split("\n")[0])
    title = title_match.group(1).strip() if title_match else topic
    # 限制文件名标题 8 字以内
    title = title[:8]

    out_path = ARTICLES_DIR / f"{date}_{title}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"✅ 文章已生成：{out_path}")
    print(f"   字数：{len(content)}")

    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()

    md_path = generate_article(args.date, args.topic)
    print(md_path)


if __name__ == "__main__":
    main()