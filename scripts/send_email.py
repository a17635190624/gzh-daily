#!/usr/bin/env python3
"""
邮件推送（公众号日更 · 云端版）

读当天 `articles/YYYY-MM-DD_*.md`，把 4 张图（1 封面 + 3 配图）作为
邮件顶部满宽图 + 附件，发送到 .env 里的收件人。

依赖：仅用 Python 3 标准库（smtplib / email / pathlib / argparse / ssl）。
"""

import os
import sys
import argparse
import ssl
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE_DIR / "articles"


SMTP_HOST_DEFAULT = "smtp.163.com"
SMTP_PORT_DEFAULT = "465"


def load_env() -> dict:
    """从环境变量读 SMTP 凭据（GitHub Actions 直接通过 env 注入）"""
    required = ["SMTP_USER", "SMTP_PASS"]
    env = {k: os.environ.get(k) for k in required + ["SMTP_HOST", "SMTP_PORT", "TO_ADDR"]}
    missing = [k for k in required if not env[k]]
    if missing:
        print(f"❌ 缺少环境变量：{missing}")
        sys.exit(1)
    return env


def find_today_files(date: str) -> tuple[Path, str, list[Path], Path | None]:
    """找当天的 md + 4 张图"""
    md_files = sorted(ARTICLES_DIR.glob(f"{date}_*.md"))
    if not md_files:
        sys.exit(f"❌ 找不到当天的 Markdown: {ARTICLES_DIR}\\{date}_*.md")

    md_path = md_files[0]
    title = md_path.stem.split("_", 1)[-1] if "_" in md_path.stem else md_path.stem

    img_paths = []
    for i in (1, 2, 3):
        p = ARTICLES_DIR / f"{date}_配图{i}.png"
        if p.exists():
            img_paths.append(p)

    cover_path = ARTICLES_DIR / f"{date}_封面.png"
    if not cover_path.exists():
        cover_path = None

    return md_path, title, img_paths, cover_path


def build_html_body(md_text: str, img_paths: list[Path], cover_path: Path | None) -> str:
    """md → HTML，正文图片用 cid 内嵌"""
    html = md_text

    # 配图位置标记替换为 cid 内嵌图
    for i, _ in enumerate(img_paths, 1):
        html = html.replace(
            f"<!-- 配图{i}位 -->",
            f'<div style="text-align:center;margin:18px 0;">'
            f'<img src="cid:img{i}" style="max-width:100%;border-radius:10px;'
            f'box-shadow:0 2px 12px rgba(0,0,0,0.08);">'
            f'<div style="color:#999;font-size:12px;margin-top:6px;">配图{i}</div>'
            f'</div>',
        )

    # 简单 markdown → html（保留加粗 + 标题）
    html = re.sub(r"^#\s+(.+)$", r'<h1 style="font-size:22px;color:#222;margin:20px 0 12px;">\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("\n", "<br>\n")

    cover_html = ""
    if cover_path:
        cover_html = (
            f'<div style="text-align:center;margin:0 0 24px;">'
            f'<img src="cid:cover" style="max-width:100%;border-radius:10px;'
            f'box-shadow:0 4px 20px rgba(0,0,0,0.15);">'
            f'</div>'
        )

    return f"""\
<html><body style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;\
max-width:680px;margin:auto;padding:20px 24px;color:#222;line-height:1.75;font-size:15px;">
{cover_html}
<hr style="border:none;border-top:1px dashed #ddd;margin:14px 0;">
{html}
<hr style="border:none;border-top:1px dashed #ddd;margin:20px 0 10px;">
<p style="color:#999;font-size:12px;text-align:center;">
本邮件由 WorkBuddy 公众号日更云端任务推送 · {datetime.now().strftime("%Y-%m-%d %H:%M")} (北京时间)
</p>
</body></html>"""


def send(env: dict, date: str, title: str, md_path: Path, img_paths: list[Path], cover_path: Path | None):
    smtp_user = env["SMTP_USER"]
    smtp_pass = env["SMTP_PASS"]
    smtp_host = env.get("SMTP_HOST") or SMTP_HOST_DEFAULT
    smtp_port = int(env.get("SMTP_PORT") or SMTP_PORT_DEFAULT)
    to_addr = env.get("TO_ADDR") or smtp_user

    md_text = md_path.read_text(encoding="utf-8")
    html_body = build_html_body(md_text, img_paths, cover_path)

    msg = MIMEMultipart("related")
    msg["From"] = Header(f"公众号日更 · 云端 <{smtp_user}>", "utf-8")
    msg["To"] = Header(to_addr, "utf-8")
    msg["Subject"] = Header(f"公众号日更 · {date} 《{title}》", "utf-8")

    msg_html = MIMEText(html_body, "html", "utf-8")
    msg.attach(msg_html)

    # 封面（cid:cover + 附件）
    if cover_path:
        data = cover_path.read_bytes()
        mime = MIMEImage(data)
        mime.add_header("Content-ID", "<cover>")
        mime.add_header("Content-Disposition", "attachment", filename=cover_path.name)
        msg.attach(mime)

    # 配图（cid:imgN + 附件）
    for i, img_path in enumerate(img_paths, 1):
        data = img_path.read_bytes()
        mime = MIMEImage(data)
        mime.add_header("Content-ID", f"<img{i}>")
        mime.add_header("Content-Disposition", "attachment", filename=img_path.name)
        msg.attach(mime)

    total_attachments = len(img_paths) + (1 if cover_path else 0)
    print(f"📧 准备发送")
    print(f"   发件人：{smtp_user}")
    print(f"   收件人：{to_addr}")
    print(f"   主题：公众号日更 · {date} 《{title}》")
    print(f"   附件：{total_attachments} 张图（1 封面 + {len(img_paths)} 配图）")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as smtp:
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(smtp_user, [to_addr], msg.as_string())

    print(f"✅ 发送成功 → {to_addr}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    env = load_env()
    md_path, title, img_paths, cover_path = find_today_files(args.date)
    send(env, args.date, title, md_path, img_paths, cover_path)


# 需要 import re
import re  # noqa: E402


if __name__ == "__main__":
    main()