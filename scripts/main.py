#!/usr/bin/env python3
"""
公众号日更 · 云端主入口

每日北京时间 8:30 由 GitHub Actions 自动触发：
  步骤 0：内容查重
  步骤 1：选题 + 生成文章（DeepSeek）
  步骤 2：生成 3 张配图 + 1 张封面（通义万相）
  步骤 3：合规检查
  步骤 4：发送邮件推送

依赖：requests / openai / dashscope（见 requirements.txt）
"""

import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
ARTICLES_DIR = BASE_DIR / "articles"


def today_beijing() -> str:
    """返回北京时间日期字符串 YYYY-MM-DD"""
    beijing = timezone(timedelta(hours=8))
    return datetime.now(beijing).strftime("%Y-%m-%d")


def step_log(step_name: str):
    print(f"\n{'=' * 60}\n  {step_name}\n{'=' * 60}")


def run_script(script_name: str, *args) -> tuple[int, str, str]:
    """运行同目录下的脚本，返回 (returncode, stdout, stderr)"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *args],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    date = today_beijing()
    print(f"🚀 公众号日更 · 云端流水线 · {date}")
    print(f"   工作目录: {BASE_DIR}")
    print(f"   产物目录: {ARTICLES_DIR}")

    # 步骤 0：内容查重 + 选题
    step_log("步骤 0：内容查重 + 选题")
    rc, out, err = run_script("pick_topic.py", "--date", date)
    print(out)
    if rc != 0:
        print(f"❌ 步骤 0 失败：\n{err}")
        sys.exit(1)
    topic = out.strip().splitlines()[-1].strip()
    print(f"✅ 选定选题: {topic}")

    # 步骤 1：生成文章
    step_log("步骤 1：生成文章（DeepSeek）")
    rc, out, err = run_script("write_article.py", "--date", date, "--topic", topic)
    print(out)
    if rc != 0:
        print(f"❌ 步骤 1 失败：\n{err}")
        sys.exit(1)

    # 步骤 2：生成图片
    step_log("步骤 2：生成图片（通义万相：3 张配图 + 1 张封面）")
    rc, out, err = run_script("gen_images.py", "--date", date)
    print(out)
    if rc != 0:
        print(f"❌ 步骤 2 失败：\n{err}")
        sys.exit(1)

    # 步骤 3：合规检查
    step_log("步骤 3：合规检查（公众号平台逻辑）")
    rc, out, err = run_script("check_compliance.py", "--date", date)
    print(out)
    if rc != 0:
        print(f"❌ 步骤 3 失败：\n{err}")
        sys.exit(1)

    # 步骤 4：发送邮件
    step_log("步骤 4：发送邮件推送")
    rc, out, err = run_script("send_email.py", "--date", date)
    print(out)
    if rc != 0:
        print(f"⚠️ 邮件推送失败（不影响产物本身）\n{err}")

    print(f"\n✅ 完成 · {date}")
    print(f"   产物在: {ARTICLES_DIR}")


if __name__ == "__main__":
    main()