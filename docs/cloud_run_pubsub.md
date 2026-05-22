# Cloud Run Fixed Webhook + Local Pub/Sub Puller

這個方案不需要自己的網域。TradingView 打 Google Cloud Run 的固定 HTTPS URL，本機 bot 主動從 Pub/Sub 拉訊號。

## 架構

    TradingView Alert
      -> Cloud Run HTTPS URL
      -> Pub/Sub topic
      -> local bot puller
      -> Kelly sizing
      -> dry-run / BingX order

Cloud Run receiver 不需要 BingX API key，它只驗證 TradingView alert、檢查格式，然後把乾淨的訊號丟進 Pub/Sub。

目前建議分階段完成：

1. Cloud Run receiver 只負責接收、驗證、發布標準化訊號。
2. 本機 puller 只負責從 Pub/Sub 取得訊號並確認內容。
3. 確認端到端訊號穩定後，再接 BingX 下單。
4. 最後補 Kelly sizing、每日虧損、特殊情境與持倉風控。

## 1. Google Cloud 前置

設定你的 project id：

    export PROJECT_ID=你的-google-cloud-project-id
    export REGION=your-cloud-run-region
    export SERVICE_NAME=your-cloud-run-service-name
    gcloud config set project $PROJECT_ID

啟用服務：

    gcloud services enable run.googleapis.com pubsub.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

建立 Pub/Sub：

    gcloud pubsub topics create tradingview-alerts
    gcloud pubsub subscriptions create tradingview-alerts-local-bot --topic=tradingview-alerts

## 2. 準備 secret

產生一串長 secret，填進本機 .env，也部署到 Cloud Run：

    WEBHOOK_SECRET=你的長隨機字串

建議先保留：

    DRY_RUN=true
    ENFORCE_WEBHOOK_IP_ALLOWLIST=false

等 TradingView 真實 alert 測通後，再改：

    ENFORCE_WEBHOOK_IP_ALLOWLIST=true

## 3. 部署 Cloud Run receiver

從專案根目錄執行：

    cd /path/to/bingx-trading-bot

    gcloud run deploy $SERVICE_NAME \
      --source . \
      --region $REGION \
      --allow-unauthenticated \
      --set-env-vars GCP_PROJECT_ID=$PROJECT_ID,PUBSUB_TOPIC=tradingview-alerts,WEBHOOK_SECRET=$WEBHOOK_SECRET,ENFORCE_WEBHOOK_IP_ALLOWLIST=false \
      --port 8080

取得固定 URL：

    gcloud run services describe $SERVICE_NAME \
      --region $REGION \
      --format='value(status.url)'

TradingView webhook URL 填這個 run.app URL。

## 4. 本機 bot 設定

.env 填：

    GCP_PROJECT_ID=你的-google-cloud-project-id
    PUBSUB_TOPIC=tradingview-alerts
    PUBSUB_SUBSCRIPTION=tradingview-alerts-local-bot
    WEBHOOK_SECRET=同一串secret
    DRY_RUN=true

本機需要登入 Google Cloud：

    gcloud auth application-default login

啟動本機 puller：

    cd /path/to/bingx-trading-bot
    .venv/bin/python -m src.pubsub_puller

## 5. TradingView alert JSON

更完整的 TradingView 設定流程見 `docs/tradingview_alert.md`。

    {
      "secret": "你的長隨機secret",
      "signal_id": "{{ticker}}-{{interval}}-{{time}}-long",
      "symbol": "BTC/USDT:USDT",
      "side": "long",
      "entry": 78000,
      "tp": 79200,
      "sl": 77400,
      "win_rate": 0.55,
      "rr": 2.0,
      "reason": "TV strategy long"
    }

## 6. IP allowlist

TradingView 官方 webhook 來源 IP：

    52.89.214.238
    34.212.75.30
    54.218.53.128
    52.32.178.7

Cloud Run 測通後，可以更新服務：

    gcloud run services update $SERVICE_NAME \
      --region $REGION \
      --update-env-vars ENFORCE_WEBHOOK_IP_ALLOWLIST=true

如果啟用後 TradingView 被擋，先看 Cloud Run logs 裡的 source_ip，再決定是否是 header 解析或代理轉送問題。
