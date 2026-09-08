#!/usr/bin/env python3
"""
合规检查（公众号平台逻辑）

对当天产出做完整合规扫描：
- 文本 9 项禁用清单
- 图片基本检查（存在性、文件大小合理性）

任何违规 → 退出码非 0，main.py 会停止流水线
"""

import os
import sys
import argparse
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE_DIR / "articles"


# 9 项文本禁用清单（依据《广告法》、微信公众平台规范、抖音/头条等平台通用词库整理）
TEXT_FORBIDDEN = {
    # 1. 政治敏感（涉政/涉军/敏感历史/领土）
    "政治敏感": [
        r"文革", r"六四", r"法轮", r"天安门事件",
        r"台独", r"藏独", r"疆独", r"港独",
    ],
    # 2. 医疗疗效（无资质绝对禁用）
    "医疗疗效": [
        r"治愈", r"根治", r"疗效", r"特效", r"神效", r"奇效", r"速效", r"全效",
        r"无副作用", r"药到病除", r"包治", r"包好", r"包痊愈",
        r"防癌", r"抗癌", r"消炎", r"杀菌", r"抗病毒", r"增强免疫力",
        r"瘦身", r"减肥", r"美白", r"祛斑", r"祛痘", r"丰胸", r"壮阳", r"增高",
        r"100%\s*有效", r"百分百\s*有效", r"\d+\s*天见效",
    ],
    # 3. 广告法违禁词（绝对化/极限/权威/品牌地位）
    "广告法违禁词": [
        # "最" 相关（全部拦截：最 + 任意中文字，覆盖 最大/最高/最低/最佳/最强/最好 等）
        r"最[\u4e00-\u9fa5]",
        # "一" 相关绝对化（只拦"全国第一/销量第一"等绝对化宣传，不误伤"第一件事"这种正常口语）
        r"(?:中国|全网|销量|排名|全国|全球|世界|行业|国际|市场|第一品牌)第一",
        r"NO\.1", r"TOP\.?1", r"独一无二", r"仅此一次", r"仅此一款", r"最后一波", r"一流",
        # "级/极" 相关
        r"国家级", r"全球级", r"宇宙级", r"世界级", r"顶级", r"顶尖", r"尖端",
        r"极品", r"极佳", r"绝佳", r"终极", r"极致",
        # "首/家/国" 相关
        r"首个", r"首选", r"独家", r"独家配方", r"全国首发", r"首款",
        r"全国销量冠军", r"国家免检", r"填补国内空白", r"特供", r"专供",
        # "品牌地位" 相关
        r"王牌", r"金牌", r"名牌", r"领袖品牌", r"世界领先", r"遥遥领先", r"领先上市",
        r"领导者", r"缔造者", r"至尊", r"巅峰", r"领袖", r"之王", r"王者", r"冠军",
        r"老字号", r"驰名商标", r"权威认证", r"官方认证",
        # "虚假/绝对" 相关
        r"史无前例", r"前无古人", r"永久", r"万能", r"祖传", r"无敌", r"纯天然",
        r"绝对", r"100%", r"百分百", r"彻底",
    ],
    # 4. 金融/收益违规（承诺收益/稳赚，涉及理财方法论可，但禁具体代码与承诺）
    "金融收益违规": [
        r"稳赚", r"高收益", r"零风险", r"保本", r"年化收益", r"日赚", r"月入",
        r"躺赚", r"必涨", r"必赚", r"不亏", r"无风险", r"保证收益", r"内幕消息", r"荐股",
        r"\b[036]\d{5}\b",  # A 股 6 位代码
        r"\b\d{6}\b(?=.*(?:基金|ETF|股票|净值))",  # 基金/ETF 代码
    ],
    # 5. 具体金额（调性硬约束：全文禁出现具体钱数）
    "具体金额": [
        r"月薪\s*[0-9]+(?:\.[0-9]+)?\s*元", r"存下\s*[0-9]+\s*万",
        r"房租\s*[0-9]+\s*元", r"[0-9]+(?:\.[0-9]+)?\s*万元",
        r"[0-9]+(?:\.[0-9]+)?\s*块钱", r"[0-9]+(?:\.[0-9]+)?\s*块",
        r"日入", r"年入",
    ],
    # 6. 焦虑/负能量词
    "焦虑词": [
        r"内卷", r"躺平", r"35岁危机", r"中年危机",
        r"同龄人抛弃你", r"被同龄人甩开", r"输在起跑线",
        r"贩卖焦虑", r"阶层固化", r"寒门难出贵子",
    ],
    # 7. 未成年人保护
    "未成年人保护": [
        r"\d+岁儿童.*推荐", r"未成年.*购买", r"未成年人.*理财",
    ],
    # 8. 虚假承诺/绝对化
    "虚假承诺": [
        r"我保证", r"绝对能", r"100%\s*能做到", r"百分百\s*能做到", r"肯定能",
        r"包治百病", r"无效退款", r"保过", r"包过",
    ],
    # 9. 诱导分享/关注/点赞/抽奖
    "诱导分享": [
        r"分享到朋友圈", r"分享得", r"集赞", r"转发解锁", r"转发有礼", r"转发了",
        r"关注公众号", r"关注解锁", r"加微信", r"加VX", r"私聊",
        r"评论抽奖", r"转发抽奖", r"点赞抽奖", r"不转不是", r"必转", r"转疯了",
        r"点击领奖", r"恭喜获奖", r"全民免单",
    ],
}


def check_text(md_path: Path) -> list[str]:
    """扫文本违禁词，返回违规项列表"""
    content = md_path.read_text(encoding="utf-8")
    violations = []

    for category, patterns in TEXT_FORBIDDEN.items():
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(f"[{category}] 命中 '{pattern}': {matches[:3]}")

    return violations


def check_images(date: str) -> list[str]:
    """检查 4 张图是否存在 + 大小合理（避免空文件 / 错误页）"""
    violations = []
    expected = [
        (f"{date}_配图1.png", 50 * 1024, 5 * 1024 * 1024),    # 50KB ~ 5MB
        (f"{date}_配图2.png", 50 * 1024, 5 * 1024 * 1024),
        (f"{date}_配图3.png", 50 * 1024, 5 * 1024 * 1024),
        (f"{date}_封面.png", 50 * 1024, 5 * 1024 * 1024),
    ]

    for name, min_size, max_size in expected:
        p = ARTICLES_DIR / name
        if not p.exists():
            violations.append(f"[图片缺失] {name}")
            continue
        size = p.stat().st_size
        if size < min_size:
            violations.append(f"[图片过小] {name} 仅 {size} 字节（可能生成失败）")
        elif size > max_size:
            violations.append(f"[图片过大] {name} {size} 字节")

    return violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    md_files = sorted(ARTICLES_DIR.glob(f"{args.date}_*.md"))
    if not md_files:
        print(f"❌ 找不到 {args.date} 的 md 文件")
        sys.exit(1)
    md_path = md_files[0]

    print(f"📄 文本合规检查：{md_path.name}")
    text_violations = check_text(md_path)
    if text_violations:
        for v in text_violations:
            print(f"  ❌ {v}")
    else:
        print(f"  ✅ 9 项禁用清单全通过")

    print(f"\n🖼️  图片合规检查")
    img_violations = check_images(args.date)
    if img_violations:
        for v in img_violations:
            print(f"  ❌ {v}")
    else:
        print(f"  ✅ 4 张图全通过（存在性 + 大小）")

    total = len(text_violations) + len(img_violations)
    print(f"\n{'=' * 60}")
    if total == 0:
        print(f"✅ 合规检查通过：0 项违规")
    else:
        print(f"❌ 合规检查未通过：{total} 项违规")
        print(f"   （GitHub Actions 会因返回非 0 退出码而停止流水线）")
        sys.exit(1)


if __name__ == "__main__":
    main()