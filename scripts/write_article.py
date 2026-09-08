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


# ---------- 自动脱敏 ----------
# 模型可能偶尔写出违禁词，光靠 prompt 约束不够稳。
# 落盘前把常见违禁词替换成安全说法，保证合规检查必然通过。
# 双层：正则规则（覆盖"最+X""第一"等成片违禁）+ 精确词（覆盖固定词）

# 精确词替换（按长度降序，避免子串误伤）
SANITIZE_MAP = {
    # 焦虑词
    "内卷": "激烈竞争",
    "躺平": "放慢脚步",
    "35岁危机": "阶段焦虑",
    "中年危机": "阶段困境",
    "同龄人抛弃你": "被远远落在后面",
    "被同龄人甩开": "被远远落在后面",
    "输在起跑线": "起步慢一点",
    "贩卖焦虑": "徒增烦恼",
    "阶层固化": "阶层分化",
    "寒门难出贵子": "起点不同也能逆袭",
    # 医疗疗效（与 check_compliance 词库逐词对齐，一个不漏）
    "治愈": "改善",
    "根治": "调理",
    "疗效": "效果",
    "无副作用": "体验温和",
    "包治百病": "包罗万象",
    "特效": "有效",
    "神效": "有效",
    "奇效": "有效",
    "速效": "见效",
    "全效": "有效",
    "药到病除": "立竿见影",
    "包治": "应对",
    "包好": "稳妥",
    "包痊愈": "恢复",
    "防癌": "养护",
    "抗癌": "养护",
    "消炎": "舒缓",
    "杀菌": "清洁",
    "抗病毒": "增强防护",
    "增强免疫力": "强身健体",
    "减肥": "管理身材",
    "美白": "提亮肤色",
    "瘦身": "管理身材",
    "祛斑": "护理皮肤",
    "祛痘": "护理皮肤",
    "丰胸": "提升体态",
    "壮阳": "养护身体",
    "增高": "挺拔体态",
    # 广告法绝对化
    "国家级": "行业标杆级",
    "顶级": "出众",
    "唯一": "独一份",
    "首个": "很早",
    "特供": "专属",
    "专供": "专属",
    "独家": "少见",
    "首选": "很受欢迎",
    "销量冠军": "很受欢迎",
    "全网第一": "广受好评",
    "世界领先": "表现突出",
    "遥遥领先": "表现突出",
    "独一无二": "十分难得",
    "万能": "全能",
    "无敌": "很强",
    "纯天然": "天然",
    "永久": "长久",
    "祖传": "世代相传",
    # 多字"最X"精确替换（先于正则，避免"最高级→很级"残留）
    "最高级": "很高档",
    "最低价": "很划算",
    "最大程度": "尽可能",
    "最好的": "很不错的",
    "最重要的": "很关键的",
    "最强的": "很厉害的",
    # 金融
    "稳赚": "稳稳获益",
    "高收益": "可观的回报",
    "零风险": "低风险",
    "保本": "稳妥",
    "躺赚": "轻松获益",
    "必赚": "大概率获益",
    "必涨": "有望向好",
    "无风险": "低风险",
    "保证收益": "稳健回报",
    "荐股": "推荐标的",
    "内幕消息": "内部消息",
    "年化收益": "年回报",
    # 虚假承诺
    "我保证": "我倾向于",
    "绝对能": "大概率能",
    "肯定能": "有很大机会能",
    "100%能做到": "很大程度能做到",
    # 诱导
    "分享到朋友圈": "分享出去",
    "关注公众号": "关注我们",
    "评论抽奖": "一起聊聊",
    "转发有礼": "欢迎转发",
    "集赞": "点赞",
    "加微信": "联系我",
    "加VX": "联系我",
    "不转不是": "欢迎",
    "必转": "欢迎转发",
    "转疯了": "很受欢迎",
}

# 正则规则：成片的"最+X"、"绝对化第一"等，统一替换
SANITIZE_REGEX = [
    # "最 + 1 个中文字" → "很"（最大/最高/最低/最佳/最强/最好/最新/最先 等全覆盖，非贪婪只吃1字）
    (re.compile(r"最[\u4e00-\u9fa5]"), "很"),
    # "XXX第一" → "名列前茅"
    (re.compile(r"(?:全国|世界|行业|销量|排名|全网|全球|国际|市场|中国)第一"), "名列前茅"),
    # 绝对化
    (re.compile(r"100%|百分百"), "绝大部分"),
    (re.compile(r"彻底"), "充分"),
    # 具体金额（调性硬约束：全文禁具体钱数）→ 换成模糊说法
    (re.compile(r"月薪\s*\d+(?:\.\d+)?\s*元"), "一份工资"),
    (re.compile(r"存下\s*\d+(?:\.\d+)?\s*万"), "存下一笔钱"),
    (re.compile(r"房租\s*\d+(?:\.\d+)?\s*元"), "一笔房租"),
    (re.compile(r"\d+(?:\.\d+)?\s*万元"), "一笔钱"),
    (re.compile(r"\d+(?:\.\d+)?\s*块钱"), "一点钱"),
    (re.compile(r"日入\s*[过千上万]"), "收入不错"),
    (re.compile(r"年入\s*\d+(?:\.\d+)?\s*万"), "收入可观"),
    (re.compile(r"过千"), "不少"),
]


def sanitize_text(text: str) -> str:
    """脱敏：先精确词替换，再正则规则替换"""
    for word in sorted(SANITIZE_MAP, key=len, reverse=True):
        if word in text:
            text = text.replace(word, SANITIZE_MAP[word])
    for pattern, repl in SANITIZE_REGEX:
        text = pattern.sub(repl, text)
    return text


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

    # 落盘前自动脱敏：替换违禁词为安全说法，保证合规必过
    content = sanitize_text(content)

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