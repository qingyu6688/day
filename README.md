# 每日科技资讯推送

> 开发者：maorongkang@gmail.com

一个基于 GitHub Actions 的自动化工具，每天早上 8 点（北京时间）自动抓取科技资讯，并通过 Server酱 推送到微信。

## 功能

- 自动抓取多个科技媒体的最新资讯（过去 24 小时）
- 从 Hacker News 获取海外科技热榜
- 整理成 Markdown 格式，通过 Server酱 推送到微信
- 支持定时运行和手动触发

## 数据来源

| 来源 | 类型 | 说明 |
|------|------|------|
| 36氪 | RSS | 国内科技、商业快讯 |
| IT之家 | RSS | 国内 IT 行业资讯 |
| 少数派 | RSS | 数码产品、效率工具 |
| Solidot | RSS | 科技、科学前沿 |
| Hacker News | API | 海外科技社区热榜 |

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

### 3. 启用 GitHub Actions

把代码推送到 GitHub 仓库后，Actions 会自动按计划运行。

也可以手动触发：进入仓库的 **Actions** 页面 → 选择 **每日科技资讯推送** 工作流 → 点击 **Run workflow**。

## 项目结构

```
.
├── .github/
│   └── workflows/
│       └── daily_tech_news.yml   # GitHub Actions 工作流配置
├── fetch_news.py                 # 核心抓取与推送脚本
├── requirements.txt              # Python 依赖
└── README.md                     # 就是你正在看的这个
```

## 本地调试

如果想在本地测试脚本：

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（换成你自己的 SendKey）
export SERVERCHAN_SENDKEY="你的SendKey"

# 运行
python fetch_news.py
```

Windows PowerShell 下设置环境变量：

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

编辑 `fetch_news.py` 中的 `RSS_SOURCES` 列表，加上或去掉你想要的源。

### 调整 Hacker News 数量

修改 `fetch_news.py` 中的 `HN_TOP_N` 变量。

## 注意事项

- Server酱免费版每天最多推送 5 条消息，一般够用
- 如果 RSS 源地址变了，脚本不会崩溃，只是那个源的内容会跳过
- GitHub Actions 的定时任务可能有几分钟的延迟，属于正常现象
