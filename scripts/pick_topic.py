#!/usr/bin/env python3
"""
选题 + 查重

扫描 `articles/` 下最近 7 天的 .md，提取标题 + 核心金句做查重表，
然后让 DeepSeek 给出一个**避开历史主题**的新选题。

输出：stdout 打印查重报告 + 选题，**最后一行**是选题字符串（给 main.py 解析）。
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import openai


BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE_DIR / "articles"


def load_history(date: str, days: int = 7) -> list[dict]:
    """读最近 N 天的历史文章"""
    base = datetime.strptime(date, "%Y-%m-%d")
    history = []

    for i in range(1, days + 1):
        target_date = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        for md_path in ARTICLES_DIR.glob(f"{target_date}_*.md"):
            try:
                content = md_path.read_text(encoding="utf-8")
                title = md_path.stem.split("_", 1)[-1] if "_" in md_path.stem else md_path.stem
                # 提取第一段和第一个加粗短句（核心金句）
                lines = content.split("\n")
                first_para = next(
                    (l.strip() for l in lines if l.strip() and not l.startswith("#") and not l.startswith("<!--")),
                    "",
                )[:200]
                # 找第一个加粗的句子
                bold_lines = [
                    l.replace("**", "").strip()
                    for l in lines
                    if l.strip().startswith("**") and l.strip().endswith("**")
                ]
                core_slogan = bold_lines[0] if bold_lines else ""

                history.append({
                    "date": target_date,
                    "title": title,
                    "first_para": first_para,
                    "core_slogan": core_slogan,
                })
            except Exception as e:
                print(f"⚠️ 读取 {md_path} 失败：{e}")

    return history


def pick_topic_via_deepseek(date: str, history: list[dict]) -> str:
    """调用 DeepSeek API 选题（避开历史主题）"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 缺少 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    history_text = "\n".join(
        f"- {h['date']} 《{h['title']}》：核心金句「{h['core_slogan']}」"
        for h in history
    ) or "（无历史文章）"

    today = datetime.strptime(date, "%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]

    system_prompt = """你是公众号选题策划，专精"认知升级 / 个人成长 / 复利 / 反常识思维 / 长期主义"方向。

调性硬约束：
- 绝不出现具体金额（"月薪 X 元""存下 X 万"等）
- 不写记账 / 账单 / 收支明细
- 不堆砌焦虑词（"内卷""35岁危机""同龄人抛弃你"）
- 每段至少 1 句加粗金句
- 口语化 + 钩子 + 认知增量
- 1200-1800 字长文

选题优先级：
1. 复利/长期主义
2. 注意力/时间
3. 认知升级
4. 反常识思维
5. 习惯/方法论
6. 常青话题（兜底）

每次必须避开历史已写的主题，变换切入角度（时间维度 / 反方观点 / 不同人群 / 不同案例）。
"""

    user_prompt = f"""今天是 {date}（{weekday}）。

# 历史已写的主题（必须避开）
{history_text}

# 任务
请输出**一个**今天的新选题，遵循：
1. 主题方向与上述任何一条不重复
2. 切入角度要新（朋友故事 / 反常识视角 / 具体场景 等）
3. 适合 1200-1800 字公众号长文展开
4. 标题 8 字以内

输出格式：只输出标题字符串，不要任何前缀说明、标点、引号。
示例：每天1小时×5年
"""

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1.3,  # 高一点增加多样性
        max_tokens=200,
    )

    return response.choices[0].message.content.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    print(f"📅 查重日期：{args.date}")

    history = load_history(args.date, days=7)
    print(f"\n📚 历史文章：{len(history)} 篇")
    for h in history:
        print(f"  · {h['date']} 《{h['title']}》")
        if h['core_slogan']:
            print(f"    金句：{h['core_slogan']}")

    print(f"\n🤖 调用 DeepSeek 选题...")
    topic = pick_topic_via_deepseek(args.date, history)
    print(f"✅ 选题：{topic}")

    # 输出选题到 stdout（main.py 解析最后一行）
    print(topic)


if __name__ == "__main__":
    main()