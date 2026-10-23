# Switched Cloud Tokens

自动获取 switched.cloud 金币（tokens）脚本。

## 机制

- 通过 Discord OAuth 登录 `panel.switched.cloud`
- 自动点击 "Earn with Vylo" 按钮
- 等待广告完成返回 tokens 页面
- 循环至每日上限（默认 25 个）

## 部署

### 1. Fork 或克隆仓库

```bash
git clone https://github.com/weikkadd/switched-tokens.git
```

### 2. 配置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret

| Secret | 必填 | 说明 |
|--------|------|------|
| `DISCORD_TOKEN` | 是 | Discord 账号 token（用于 OAuth 登录） |
| `SWITCHED_COOKIE` | 否 | switched.cloud Cookie（备用，Discord 登录不通时用） |
| `TG_BOT_TOKEN` | 否 | Telegram bot token（通知用） |
| `TG_CHAT_ID` | 否 | Telegram chat id（通知用） |
| `NODE_LINK` | 否 | 代理节点链接（需要代理时填） |

### 3. 获取 DISCORD_TOKEN

1. 浏览器登录 Discord 网页版
2. F12 → Network → 刷新页面
3. 找任意请求 → Headers → `Authorization` 的值就是 token

### 4. 运行

- **自动**：GitHub Actions 每 6 小时自动跑一次
- **手动**：Actions → "Switched Cloud Tokens" → Run workflow

### 5. 本地运行

```bash
pip install seleniumbase requests
seleniumbase install chromedriver

# 设置环境变量
export DISCORD_TOKEN="你的token"
export IS_PROXY=true  # 如需代理
export NODE_LINK="代理节点链接"

# 运行
xvfb-run --auto-servernum python renew.py
```

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MAX_TOKENS` | 25 | 每日金币上限 |
| `AD_WAIT` | 120 | 单次广告等待秒数 |
| `COOLDOWN` | 5 | 每次获取间隔秒数 |
| `IS_PROXY` | false | 是否使用代理 |
| `PROXY_SERVER` | socks5://127.0.0.1:1080 | 代理地址 |