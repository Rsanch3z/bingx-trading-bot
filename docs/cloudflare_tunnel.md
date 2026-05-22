# Cloudflare Tunnel + TradingView Webhook

目標：讓 TradingView alert 透過 HTTPS 打到本機 bot，但本機不用開公開 port。

## 重要限制

TradingView webhook 官方限制：

- Webhook URL 只能使用 80 或 443；Cloudflare Tunnel 的公開網址會走 443
- 接收端超過 3 秒才回應，TradingView 會取消請求
- TradingView webhook 目前不支援 IPv6
- TradingView 官方列出的 POST 來源 IP：52.89.214.238、34.212.75.30、54.218.53.128、52.32.178.7

## Bot 安全設定

.env 目前有：

    WEBHOOK_SECRET=replace-with-a-long-random-secret
    ENFORCE_WEBHOOK_IP_ALLOWLIST=false
    WEBHOOK_ALLOWED_IPS=52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7

建議：

1. 先保持 DRY_RUN=true。
2. 把 WEBHOOK_SECRET 改成一串長隨機字串。
3. Cloudflare Tunnel 測通後，再把 ENFORCE_WEBHOOK_IP_ALLOWLIST=true。
4. TradingView alert JSON 裡必須帶同一個 secret。

## 快速測試 tunnel

臨時測試可以用：

    cloudflared tunnel --url http://127.0.0.1:8787

缺點：每次重啟 cloudflared，公開 URL 可能會變，TradingView alert 要手動更新。

## 正式 named tunnel

正式建議用固定子網域，例如：

    tv-bot.your-domain.com

流程：

1. 安裝 cloudflared。
2. 登入 Cloudflare：

       cloudflared tunnel login

3. 建立 tunnel：

       cloudflared tunnel create bingx-trading-bot

4. 建立 DNS route：

       cloudflared tunnel route dns bingx-trading-bot tv-bot.your-domain.com

5. 建立 ~/.cloudflared/config.yml：

       tunnel: bingx-trading-bot
       credentials-file: /path/to/.cloudflared/<TUNNEL_ID>.json
       ingress:
         - hostname: tv-bot.your-domain.com
           service: http://127.0.0.1:8787
         - service: http_status:404

6. 啟動 bot：

       cd /path/to/bingx-trading-bot
       .venv/bin/python -m src.webhook

7. 另一個 terminal 啟動 tunnel：

       cloudflared tunnel run bingx-trading-bot

8. TradingView webhook URL 填：

       https://tv-bot.your-domain.com/

## TradingView alert JSON

    {
      "secret": "你的長隨機secret",
      "symbol": "BTC/USDT:USDT",
      "side": "long",
      "entry": 78000,
      "tp": 79200,
      "sl": 77400,
      "win_rate": 0.55,
      "rr": 2.0,
      "reason": "TV strategy long"
    }

## Cloudflare WAF 建議

若你的 Cloudflare plan 支援 WAF / Security Rules，可以再加一道規則：

- Hostname 等於 tv-bot.your-domain.com
- Source IP 只允許 TradingView 四個 IP
- Method 必須是 POST
- Path 可以限制為 /

即使 WAF 已擋，bot 仍會再檢查 secret 和 IP allowlist，形成兩層保護。
