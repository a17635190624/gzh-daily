# 公众号日更 · 云端版

每天北京时间 8:30 自动跑一篇"认知 / 成长 / 复利"方向公众号长文，自动邮件推送。**完全云端，不依赖电脑是否开机。**

---

## 这是什么

```
GitHub Actions（云端，免费）
每天 8:30 cron 触发
        ↓
  Step 1：DeepSeek API 选题（避开历史主题）
        ↓
  Step 2：DeepSeek API 写文章
        ↓
  Step 3：通义万相 生成 3 张配图 + 1 张封面
        ↓
  Step 4：合规检查（公众号平台规则）
        ↓
  Step 5：SMTP 发送邮件到你的 163 邮箱
        ↓
  Step 6：当日产物提交到 GitHub（历史可回看）
```

---

## 快速开始（5 分钟）

### 1. 注册 3 个免费账号（拿 API Key）

| 服务 | 用途 | 注册地址 |
|---|---|---|
| **GitHub** | 托管代码 + 跑定时任务 | https://github.com |
| **DeepSeek** | 文本生成 | https://platform.deepseek.com → API Keys |
| **阿里云 DashScope** | 图片生成（通义万相） | https://dashscope.aliyun.com → API-KEY 管理 |

每个服务都送免费额度：
- **DeepSeek**：新用户 10 元，写一篇文章约几分钱
- **通义万相**：新用户 500 张免费图，之后约 0.04 元/张
- **GitHub Actions**：2000 分钟/月额度，每天跑 1 次只用 1-2 分钟

### 2. 建 GitHub 私有仓库并推送

```bash
# 在 GitHub 网站新建一个私有仓库，比如 gzh-daily
# 然后在本地：

cd 公众号云端
git init
git add .
git commit -m "init: 公众号日更云端版"
git branch -M main
git remote add origin https://github.com/你的用户名/gzh-daily.git
git push -u origin main
```

### 3. 配置 GitHub Secrets（凭据）

进入 GitHub 仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

依次添加 6 个 Secrets（每个一行）：

| Secret 名 | 填什么 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | `sk-xxxxxxxxxx` | DeepSeek 控制台拿 |
| `DASHSCOPE_API_KEY` | `sk-xxxxxxxxxx` | 阿里云 DashScope 控制台拿 |
| `SMTP_HOST` | `smtp.163.com` | 163 邮箱固定值 |
| `SMTP_PORT` | `465` | SSL 端口固定值 |
| `SMTP_USER` | `yourname@163.com` | 你的 163 邮箱 |
| `SMTP_PASS` | `xxxxxxxxxxxxxxxx` | **不是登录密码**，是 163 设置→POP3/SMTP/IMAP→开启后生成的 16 位授权密码 |
| `TO_ADDR` | `yourname@163.com` | 收件邮箱（默认 = SMTP_USER） |

> 💡 SMTP_PASS 是最容易搞错的：必须是 163 设置里"客户端授权密码"，不是你的登录密码。

### 4. 手动触发一次验证

仓库 → **Actions** 标签 → 左侧"公众号日更 · 每天 8:30" → **Run workflow**

跑完查看邮箱，应该收到一封带封面 + 3 张配图的邮件。

如果失败 → 看下面的"故障排查"。

---

## 工作原理

### 目录结构
```
公众号云端/
├── .github/workflows/daily.yml      # GitHub Actions 定时任务
├── scripts/
│   ├── main.py                       # 主入口（按顺序调用下面 5 个脚本）
│   ├── pick_topic.py                 # 查重 + 选题（调 DeepSeek）
│   ├── write_article.py              # 生成文章（调 DeepSeek）
│   ├── gen_images.py                 # 生成图片（调通义万相）
│   ├── check_compliance.py           # 合规检查（公众号平台逻辑）
│   └── send_email.py                 # 发邮件（SMTP）
├── articles/                         # 产物目录（自动提交到 git）
│   ├── 2026-09-06_每天1小时.md
│   ├── 2026-09-06_封面.png
│   ├── 2026-09-06_配图1.png
│   ├── 2026-09-06_配图2.png
│   └── 2026-09-06_配图3.png
├── requirements.txt
├── .env.example                      # 环境变量模板（云端不用这个，通过 Secrets 注入）
├── .gitignore
└── README.md
```

### 流水线顺序

1. **查重 + 选题**（`pick_topic.py`）
   - 扫描 `articles/` 最近 7 天的 md
   - 让 DeepSeek 选一个**避开历史主题**的新选题
2. **生成文章**（`write_article.py`）
   - 调 DeepSeek，按调性约束生成 1200-1800 字长文
   - 自动保留 3 个配图位置标记
3. **生成图片**（`gen_images.py`）
   - 读 md 里的 3 个配图说明
   - 调通义万相生成 3 张配图 + 1 张封面（含中文标题）
4. **合规检查**（`check_compliance.py`）
   - 文本扫 9 项禁用清单（政治、医疗、广告法、金融代码、金额、焦虑词等）
   - 图片检查存在性 + 大小
   - **任一违规 → 停止流水线，不发邮件**
5. **发送邮件**（`send_email.py`）
   - md 转 HTML，配图用 cid 内嵌
   - 1 张封面 + 3 张配图作为附件
   - SMTP 发到你的 163 邮箱

### 调性硬约束

云端版完全继承本机版的调性：
- **方向**：认知 / 成长 / 复利 / 反常识思维
- **禁**：具体金额、焦虑词、绝对化用词、具体金融代码
- **风格**：1200-1800 字、口语化、有钩子、有金句、不堆砌情绪词
- **封面**：必带中文标题，不带任何作业水印
- **图片**：no human figures / no watermarks / no AI badges

---

## 故障排查

| 现象 | 原因 | 解法 |
|---|---|---|
| Actions 跑失败：`ModuleNotFoundError: No module named 'openai'` | 依赖没装好 | 检查 `requirements.txt` 里有 `openai>=1.0.0` |
| Actions 跑失败：`❌ 缺少 DEEPSEEK_API_KEY 环境变量` | Secret 没配 | 进 Settings → Secrets 重新添加 |
| 文章生成了但没发邮件 | SMTP 失败 | 邮箱垃圾箱；检查 SMTP_PASS 是授权密码不是登录密码 |
| 文章空白 / 配图空白 | API 调用失败 | 检查 API Key 是否过期 / 余额用完 |
| 合规检查挂掉：`[广告法违禁词] 命中` | 文章触发了违禁词 | 修 `write_article.py` 的 system prompt 加更多约束；或删掉违规词的文章 |
| 邮件收到但图显示不出来 | 邮件客户端不支持 cid | 用 QQ邮箱 / 网易邮箱大师 APP 查看 |

---

## 费用估算

| 服务 | 免费额度 | 用满后费用 |
|---|---|---|
| GitHub Actions | 2000 分钟/月 | 不超额就免费 |
| DeepSeek | 10 元 | 约 0.001 元/1000 tokens（每篇几分钱） |
| 通义万相 | 500 张图 | 约 0.04 元/张（每天 3 张 ≈ 3.6 元/月） |
| 163 SMTP | 无限 | 免费 |
| **月总成本** | **≈ 0~5 元** | 取决于图片额度用完没 |

**就算一个月不出稿，账单也是 0 元**——按量付费，不跑不扣。

---

## 维护建议

### 改调性
编辑 `scripts/write_article.py` 的 `system_prompt`，调整选题方向 / 金句风格 / 硬约束。

### 改推送时间
编辑 `.github/workflows/daily.yml` 的 cron 表达式：
- 北京时间 8:30 → UTC 0:30（`cron: '30 0 * * *'`）
- 北京时间 7:30 → UTC 23:30（前一天） → `cron: '30 23 * * *'`

### 改收件人
在 Secrets 里改 `TO_ADDR` 即可，可以是任意邮箱。

### 加图片 prompt 模板
编辑 `scripts/gen_images.py` 的 `gen_infographic_prompt` / `gen_cover_prompt`，调风格。

### 跑某天但 8:30 错过了
进 Actions → Run workflow → 手动触发补跑（脚本会自动覆盖当天产物）。

---

## 下一步

跑通后，可以扩展：
- 视频版：脚本加 `scripts/gen_video.py`，调剪映/即梦 API
- 多平台分发：脚本加 `scripts/post_to_x.py`，同时发知乎/小红书
- 评论互动：脚本加 `scripts/read_comments.py`，自动回复读者

但**先跑 1 周看看效果**，再决定要不要加新功能。