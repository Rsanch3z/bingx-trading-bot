# BingX Trading Bot — Progress & AI Handoff

> **給下一個 AI 開發者：** 這個檔案是你的起點。從「當前狀態」開始讀，然後看「下一步行動」。所有 spec 和 plan 在 `docs/` 裡。

---

## 當前狀態 (2026-05-28)

**程式碼：全部完成，17/17 tests 通過。尚未部署。**

```
[✅ 程式碼完成] → [⏳ 等待部署/測試] → [ ] Demo 驗證 → [ ] 切換 Live
```

所有 src/ 模組已實作並通過單元測試。下一步是人工完成 GCP 部署和 BingX 帳號設定（需要真實的 API key 和 GCP 帳號，AI 無法代勞）。

---

## 整體架構

```
TradingView Alert
      │ HTTPS POST (JSON + secret token)
      ▼
GCP Cloud Run  [cloud/webhook_receiver/main.py]
  - 驗證 webhook secret (hmac.compare_digest)
  - 發布到 Pub/Sub topic: tradingview-alerts
      │ Pub/Sub (訊息保留 7 天，自動 retry)
      ▼
GCP Pub/Sub  subscription: local-bot-sub
      │ streaming pull
      ▼
Windows 11 本機 Bot  [src/]
  pubsub_subscriber → risk_manager → bingx_executor
                           ↕
                   position_monitor (背景執行緒)
      │ BingX REST API (HMAC-SHA256)
      ▼
BingX Perpetual Futures (Demo VST / Live)
```

**設計原則：** BingX API key 永遠不離開本機。Cloud Run 只負責轉發，不知道 BingX 的存在。

---

## 檔案地圖

| 檔案 | 職責 |
|------|------|
| `src/config.py` | 從 `.env` 載入所有設定，`load_config() -> Config` |
| `src/bingx_executor.py` | BingX API wrapper：`TradeSignal` 資料類別、下單、平倉、查帳戶 |
| `src/risk_manager.py` | 風控：每日虧損熔斷、持倉上限、size cap。**RLock 執行緒安全** |
| `src/pubsub_subscriber.py` | 拉取 Pub/Sub 訊息 → 解析 → 呼叫 callback → ACK/NACK |
| `src/position_monitor.py` | 背景執行緒：每 N 秒 poll BingX，更新本檔案 Bot 狀態 |
| `src/main.py` | 入口點：串接所有模組，SIGINT/SIGTERM 優雅關閉 |
| `cloud/webhook_receiver/main.py` | Cloud Run FastAPI app：`POST /alert`, `GET /health` |
| `cloud/webhook_receiver/Dockerfile` | 非 root 用戶，python:3.11-slim |
| `scripts/setup_gcp.sh` | 一鍵建立 Pub/Sub + Cloud Run + service account |
| `scripts/install_service.ps1` | NSSM Windows Service 安裝（需 Administrator） |
| `config/.env.example` | 所有環境變數模板，**複製成 `.env` 後填入** |

---

## 設計文件位置

| 文件 | 路徑 |
|------|------|
| 完整 Spec | `docs/superpowers/specs/2026-05-28-bingx-trading-bot-design.md` |
| 實作計畫 (11 tasks) | `docs/superpowers/plans/2026-05-28-bingx-trading-bot.md` |

---

## TradingView Alert Payload 格式

TradingView webhook 要發送的 JSON（在 TradingView alert 設定裡貼這個）：

```json
{
  "secret": "{{你設的 WEBHOOK_SECRET}}",
  "symbol": "BTC-USDT",
  "action": "BUY",
  "side": "LONG",
  "order_type": "MARKET",
  "size_pct": 5.0,
  "tp_pct": 2.0,
  "sl_pct": 1.0,
  "close_position": false,
  "strategy": "{{strategy.title}}",
  "timestamp": "{{timenow}}"
}
```

| 欄位 | 說明 |
|------|------|
| `action` | `BUY` / `SELL` / `CLOSE`（大寫） |
| `side` | `LONG` / `SHORT`（大寫） |
| `size_pct` | 帳戶餘額百分比，例：`5.0` = 下 5% |
| `close_position` | `true` 時忽略其他欄位，直接平倉 |

---

## 風控設定說明

| 環境變數 | 預設值 | 說明 |
|----------|--------|------|
| `DRY_RUN` | `true` | **切 live 前改成 false** |
| `BINGX_MODE` | `demo` | `demo` 或 `live` |
| `BINGX_SANDBOX` | `true` | true = 使用 VST demo key |
| `MAX_DAILY_LOSS_PCT` | `5.0` | 超過此值觸發熔斷，當日停止下單 |
| `MAX_OPEN_POSITIONS` | `5` | 同時最多幾個持倉 |
| `MAX_SINGLE_TRADE_PCT` | `10.0` | 單筆最大倉位（超過自動截斷） |
| `MONITOR_INTERVAL_SEC` | `30` | 持倉監控輪詢間隔（秒） |

---

## 已知待處理問題（上 live 前）

這些問題已記錄，不影響 demo 測試，但上 live 前應處理：

1. **熔斷器無自動觸發**：`risk_manager.update_daily_loss()` 沒有在實際成交後被呼叫。熔斷器目前只能手動觸發（或透過未來加入的 P&L tracking）。
2. **訂單冪等性**：NACK 後重試可能重複下單。未來應加 client order ID 去重。
3. **API rate limit**：`bingx_executor._request()` 沒有 retry-with-backoff。短時間多訊號可能觸發 BingX 限流。
4. **啟動時無憑證驗證**：bot 啟動成功但 API key 錯誤要等第一次 poll（30s）才報錯。

---

## 下一步行動（人工執行）

這些步驟需要真實帳號，AI 無法代勞：

### 第一階段：環境設定

- [ ] **Step A** — 取得 BingX VST demo API key
  - BingX 官網 → API Management → 新增 API（選 VST 模式）
  - 記錄 `API Key` 和 `Secret Key`

- [ ] **Step B** — 建立 GCP project
  - https://console.cloud.google.com → 新增 project
  - 確認計費帳號已啟用（Cloud Run 需要）

- [ ] **Step C** — 複製並填寫 `.env`
  ```powershell
  Copy-Item config\.env.example .env
  # 用文字編輯器填入：BINGX_API_KEY, BINGX_API_SECRET, PUBSUB_PROJECT_ID, WEBHOOK_SECRET
  ```
  `WEBHOOK_SECRET` 自訂一個 32 字元隨機字串，後面 Cloud Run 也要用同一個。

### 第二階段：GCP 部署

- [ ] **Step D** — 安裝並登入 gcloud CLI
  ```powershell
  # 安裝：https://cloud.google.com/sdk/docs/install
  gcloud auth login
  ```

- [ ] **Step E** — 一鍵部署
  ```bash
  bash scripts/setup_gcp.sh <YOUR_PROJECT_ID> asia-east1 <YOUR_WEBHOOK_SECRET>
  ```
  輸出的最後一行是 Cloud Run URL，例：`https://bingx-webhook-xxxx.run.app/alert`
  把這個 URL 填入 TradingView alert 的 webhook URL。

### 第三階段：本機 bot 測試

- [ ] **Step F** — 前台執行 bot 確認連線
  ```powershell
  cd "D:\投資專案\bingx-trading-bot"
  .venv\Scripts\Activate.ps1
  python -m src.main
  ```
  應看到：`Starting BingX trading bot (mode=demo, dry_run=True)`
  以及：`Listening on projects/.../subscriptions/local-bot-sub ...`

- [ ] **Step G** — 手動觸發一筆測試訊號
  ```powershell
  $url = "https://bingx-webhook-xxxx.run.app/alert"   # 換成你的 URL
  $body = @{
      secret = "YOUR_WEBHOOK_SECRET"
      symbol = "BTC-USDT"; action = "BUY"; side = "LONG"
      order_type = "MARKET"; size_pct = 1.0
      tp_pct = 2.0; sl_pct = 1.0; close_position = $false
      strategy = "manual_test"; timestamp = (Get-Date -Format o)
  } | ConvertTo-Json
  Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $body
  ```
  Bot 終端機應出現：`Signal received: BUY BTC-USDT` → `DRY RUN: BUY BTC-USDT ...` → `Message ACKed`

- [ ] **Step H** — 驗證 PROGRESS.md 自動更新
  執行 bot 超過 30 秒後，本檔案的「Bot 狀態」區塊應自動被更新。

### 第四階段：常駐化

- [ ] **Step I** — 安裝 Windows Service（需 Administrator）
  ```powershell
  # 先下載 NSSM：https://nssm.cc/download → 解壓放入 PATH
  # 以系統管理員執行 PowerShell：
  .\scripts\install_service.ps1
  ```

### 第五階段：切換 Live（demo 通過後）

切換前確認清單：
- [ ] 至少 10 筆 demo 單執行正確
- [ ] 熔斷器手動觸發測試通過
- [ ] PROGRESS.md Bot 狀態區塊正常更新
- [ ] Windows Service 重啟後自動恢復

確認後只改 `.env` 三行，不需改程式碼：
```env
BINGX_MODE=live
BINGX_SANDBOX=false
DRY_RUN=false
```

---

## 更新紀錄

| 日期 | 里程碑 | 狀態 | 備註 |
|------|--------|------|------|
| 2026-05-28 | 專案初始化 | ✅ 完成 | Fork dc-tw/bingx-trading-bot + 目錄結構 |
| 2026-05-28 | Config module | ✅ 完成 | typed Config dataclass, dotenv, TDD |
| 2026-05-28 | Cloud Run webhook receiver | ✅ 完成 | FastAPI, hmac.compare_digest, Pub/Sub publish |
| 2026-05-28 | GCP setup script | ✅ 完成 | Pub/Sub + Cloud Run 一鍵部署 |
| 2026-05-28 | BingX executor | ✅ 完成 | HMAC-SHA256, place/close order, dry-run |
| 2026-05-28 | Risk manager | ✅ 完成 | circuit breaker, position limit, RLock 執行緒安全 |
| 2026-05-28 | Pub/Sub subscriber | ✅ 完成 | streaming pull, ACK/NACK, input validation |
| 2026-05-28 | Position monitor | ✅ 完成 | 背景執行緒, PROGRESS.md auto-update |
| 2026-05-28 | Main entry point | ✅ 完成 | 串接全部，SIGINT/CancelledError 優雅關閉 |
| 2026-05-28 | Windows Service | ✅ 完成 | NSSM install/uninstall, log rotation |
| 2026-05-28 | Code review fixes | ✅ 完成 | dry_run guards, input validation, timing-safe secret |
| 2026-05-28 | Demo test + GCP 部署 | 📋 待執行 | 需要真實 API key + GCP 帳號 |

---

## Bot 狀態（由 position_monitor 自動更新）

_Bot 尚未啟動_
