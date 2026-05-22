# TradingView Alert Setup

Cloud Run webhook URL:

    https://your-cloud-run-service-url/

TradingView webhook 官方限制重點：

- Webhook URL 必須走 80 或 443；Cloud Run HTTPS URL 可用。
- Alert message 是有效 JSON 時，TradingView 會用 `application/json` 送出。
- 接收端超過 3 秒才回應，TradingView 會取消請求。
- TradingView webhook 需要帳號啟用 2FA。
- 來源 IP 可用 allowlist：
  - `52.89.214.238`
  - `34.212.75.30`
  - `54.218.53.128`
  - `52.32.178.7`

目前建議先保持 Cloud Run：

    ENFORCE_WEBHOOK_IP_ALLOWLIST=false

等 TradingView 真實 alert 測通後，再改成 true。

## 1. 先啟動本機 puller

    cd /Users/dc/Workspace/bingx-trading-bot
    .venv/bin/python -u -m src.pubsub_puller

`-u` 可以讓收到訊號時即時印出來。

## 2. TradingView Alert 欄位

建立或編輯 alert 時：

- Notifications 勾選 Webhook URL
- Webhook URL 填：

      https://your-cloud-run-service-url/

- Message 填 JSON

## 3. 手動固定點位測試

這個版本適合先確認 TradingView -> Cloud Run -> Pub/Sub -> local puller 有通。

把 `secret` 換成 `.env` 的 `WEBHOOK_SECRET`：

    {
      "secret": "你的WEBHOOK_SECRET",
      "signal_id": "{{ticker}}-{{interval}}-{{time}}-manual-long",
      "ticker": "{{ticker}}",
      "side": "long",
      "entry": 78000,
      "tp": 79200,
      "sl": 77400,
      "win_rate": 0.55,
      "rr": 2.0,
      "reason": "TradingView manual test"
    }

`ticker` 會自動轉成 BingX / ccxt symbol，例如：

- `BTCUSDT.P` -> `BTC/USDT:USDT`
- `ETHUSDT.P` -> `ETH/USDT:USDT`
- `SOLUSDT` -> `SOL/USDT:USDT`

如果你要手動指定交易所 symbol，也可以改用：

    "symbol": "BTC/USDT:USDT"

成功時，本機 puller 會印出類似：

    processed message_id=... result={'ok': True, 'received': True, 'signal_id': '...', ...}

## 4. Pine Script 動態 alert 範例

如果 entry / TP / SL / win rate 要由策略計算，建議在 Pine Script 裡用 `alert()` 組 JSON。

下面只是接線範例，不是完整交易策略：

    //@version=5
    indicator("BingX Bot Alert Example", overlay=true)

    secret = input.string("replace-with-webhook-secret", "Webhook secret")
    winRate = input.float(0.55, "Estimated win rate", minval=0.01, maxval=1.0)
    rr = input.float(2.0, "Win/loss ratio", minval=0.01)
    tpPct = input.float(0.015, "TP %", minval=0.0001)
    slPct = input.float(0.0075, "SL %", minval=0.0001)

    fast = ta.ema(close, 9)
    slow = ta.ema(close, 21)

    longSignal = ta.crossover(fast, slow)
    shortSignal = ta.crossunder(fast, slow)

    makePayload(side, entry, tp, sl) =>
        '{"secret":"' + secret + '"' +
        ',"signal_id":"' + syminfo.ticker + '-' + timeframe.period + '-' + str.tostring(time) + '-' + side + '"' +
        ',"ticker":"' + syminfo.ticker + '"' +
        ',"side":"' + side + '"' +
        ',"entry":' + str.tostring(entry) +
        ',"tp":' + str.tostring(tp) +
        ',"sl":' + str.tostring(sl) +
        ',"win_rate":' + str.tostring(winRate) +
        ',"rr":' + str.tostring(rr) +
        ',"reason":"Pine EMA alert"}'

    if longSignal
        entry = close
        tp = entry * (1 + tpPct)
        sl = entry * (1 - slPct)
        alert(makePayload("long", entry, tp, sl), alert.freq_once_per_bar_close)

    if shortSignal
        entry = close
        tp = entry * (1 - tpPct)
        sl = entry * (1 + slPct)
        alert(makePayload("short", entry, tp, sl), alert.freq_once_per_bar_close)

TradingView 建立 alert 時，Condition 選這個 indicator，觸發方式選 `Any alert() function call`。

## 5. 測通後才開 IP allowlist

等 TradingView alert 真的送到本機 puller 後，再更新 Cloud Run：

    gcloud run services update bingx-tv-webhook \
      --region asia-east1 \
      --update-env-vars ENFORCE_WEBHOOK_IP_ALLOWLIST=true

如果開啟後被擋，再看 Cloud Run logs 的 `source_ip`。
