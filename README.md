# 每日科技资讯推送

> 开发者：maorongkang@gmail.com

一个基于 GitHub Actions 的自动化工具，每天早上 8 点（北京时间）自动抓取科技资讯，生成精美的新闻页面并部署到 GitHub Pages，同时通过 Server酱 推送摘要到微信。

## 功能

- 自动抓取多个科技媒体的最新资讯（过去 24 小时）
- 从 Hacker News 获取海外科技热榜
- 生成浅色调、卡片式布局的精美 HTML 新闻页面
- 部署到 GitHub Pages，支持在线查看和历史归档
- 通过 Server酱 推送摘要 + 页面链接到微信
- 支持定时运行和手动触发

## 数据来源

| 来源 | 类型 | 说明 |
|------|------|------|
| 36氪 | RSS | 国内科技、商业快讯 |
| IT之家 | RSS | 国内 IT 行业资讯 |
| 少数派 | RSS | 数码产品、效率工具 |
| Solidot | RSS | 科技、科学前沿 |
| Hacker News | API | 海外科技社区热榜 |

## 页面设计

新闻页面采用浅色调设计，特点：
- 白色/浅灰背景，长时间阅读不累
- 商务蓝灰色系，专业稳重
- 卡片式布局，按来源分区
- Hacker News 热度标签（按分数分级显示）
- 适配移动端，在微信内打开也好看

## 配置步骤

### 1. 获取 Server酱 SendKey

1. 打开 [Server酱官网](https://sct.ftqq.com/)
2. 用微信扫码登录
3. 登录后在「Key & API」页面复制你的 **SendKey**

### 2. 配置 GitHub Secrets

1. 进入你的 GitHub 仓库页面
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. 名称填 `SERVERCHAN_SENDKEY`，值填上一步复制的 SendKey
5. 保存

### 3. 启用 GitHub Pages

首次运行工作流后，会自动创建 `gh-pages` 分支。然后需要手动开启 Pages：

1. 进入仓库 **Settings** → **Pages**
2. Source 选择 **Deploy from a branch**
3. Branch 选择 **gh-pages**，目录选 **/ (root)**
4. 保存

之后你的新闻页面就可以在 `https://<你的用户名>.github.io/<仓库名>/` 访问了。

### 4. 手动触发一次测试

进入仓库的 **Actions** 页面 → 选择 **每日科技资讯推送** → 点击 **Run workflow**。

## 项目结构

```
.
├── .github/
│   └── workflows/
│       └── daily_tech_news.yml   # GitHub Actions 工作流配置
├── fetch_news.py                 # 核心抓取、页面生成与推送脚本
├── requirements.txt              # Python 依赖
└── README.md                     # 就是你正在看的这个
```

运行后会生成：

```
public/
├── index.html                    # 最新一期的新闻页面
└── archive/
    ├── 2026-03-02.html           # 历史归档
    ├── 2026-03-03.html
    └── ...
```

## 本地调试

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export SERVERCHAN_SENDKEY="你的SendKey"

# 运行
python fetch_news.py
# 生成的页面在 public/index.html，浏览器打开即可预览
```

Windows PowerShell：

```powershell
$env:SERVERCHAN_SENDKEY = "你的SendKey"
python fetch_news.py
```

## 自定义

### 调整抓取时间

编辑 `.github/workflows/daily_tech_news.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 0 * * *'  # UTC 00:00 = 北京时间 08:00
```

### 增减 RSS 源

编辑 `fetch_news.py` 中的 `RSS_SOURCES` 列表。

### 调整 Hacker News 数量

修改 `fetch_news.py` 中的 `HN_TOP_N` 变量。

## 注意事项

- Server酱免费版每天最多推送 5 条消息，一般够用
- 首次运行后需要手动开启 GitHub Pages（在 Settings → Pages 中配置）
- GitHub Actions 的定时任务可能有几分钟的延迟，属于正常现象
- 历史归档会保留在 gh-pages 分支，每天一个 HTML 文件
