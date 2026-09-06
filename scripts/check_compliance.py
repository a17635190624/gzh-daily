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


# 9 项文本禁用清单
TEXT_FORBIDDEN = {
    "政治敏感": [
        r"文革", r"六四", r"法轮", r"天安门事件",
        # 可按需扩展
    ],
    "医疗疗效": [
        r"治愈", r"根治", r"100%\s*有效", r"无副作用", r"\d+\s*天见效",
        r"彻底治疗", r"药到病除",
    ],
    "广告法违禁词": [
        r"最[好的佳强优大]", r"第一[名款个]", r"国家级", r"顶级", r"唯一", r"首个",
        r"特供", r"专供", r"独家", r"首选", r"销量冠军", r"全网第一", r"世界领先",
    ],
    "具体金融代码": [
        r"\b[036]\d{5}\b",  # A 股代码
        r"\b\d{6}\b(?=.*基金|.*ETF)",  # 基金代码（需要前后文）
    ],
    "具体金额": [
        r"月薪\s*[0-9]+\s*元", r"存下\s*[0-9]+\s*万", r"房租\s*[0-9]+\s*元",
        r"[0-9]+\s*万元", r"[0-9]+\s*块钱",
    ],
    "焦虑词": [
        r"内卷", r"躺平", r"35岁危机", r"中年危机",
        r"同龄人抛弃你", r"被同龄人甩开", r"输在起跑线",
    ],
    "未成年人保护": [
        r"\d+岁儿童.*推荐", r"未成年.*购买",
    ],
    "虚假承诺": [
        r"我保证", r"绝对能", r"100%\s*能做到", r"肯定能",
    ],
    "诱导分享": [
        r"分享到朋友圈", r"关注公众号", r"评论抽奖", r"转发有礼", r"集赞",
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