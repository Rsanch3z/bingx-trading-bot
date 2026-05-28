#!/bin/bash
# One-shot GCP setup: Pub/Sub + Cloud Run + service account
# Usage: bash scripts/setup_gcp.sh <GCP_PROJECT_ID> <REGION> <WEBHOOK_SECRET>
set -euo pipefail

PROJECT_ID="${1:?Usage: setup_gcp.sh <PROJECT_ID> <REGION> <WEBHOOK_SECRET>}"
REGION="${2:?}"
WEBHOOK_SECRET="${3:?}"
TOPIC="tradingview-alerts"
SUBSCRIPTION="local-bot-sub"
SA_NAME="bingx-bot-pubsub"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SERVICE_NAME="bingx-webhook"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=== [1/6] Setting project ==="
gcloud config set project "${PROJECT_ID}"

echo "=== [2/6] Enabling APIs ==="
gcloud services enable \
  pubsub.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com

echo "=== [3/6] Creating Pub/Sub topic and subscription ==="
gcloud pubsub topics create "${TOPIC}" 2>/dev/null || echo "Topic already exists"
gcloud pubsub subscriptions create "${SUBSCRIPTION}" \
  --topic="${TOPIC}" \
  --message-retention-duration=7d \
  --ack-deadline=60 \
  2>/dev/null || echo "Subscription already exists"

echo "=== [4/6] Creating service account for local bot ==="
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="BingX Bot Pub/Sub Subscriber" \
  2>/dev/null || echo "Service account already exists"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.subscriber"

echo "=== [5/6] Downloading service account key ==="
mkdir -p config
gcloud iam service-accounts keys create config/service_account.json \
  --iam-account="${SA_EMAIL}"
echo "Key saved to config/service_account.json — DO NOT commit this file!"

echo "=== [6/6] Building and deploying Cloud Run ==="
gcloud builds submit cloud/webhook_receiver \
  --tag="${IMAGE}"
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="WEBHOOK_SECRET=${WEBHOOK_SECRET},PUBSUB_PROJECT_ID=${PROJECT_ID}" \
  --min-instances=0 \
  --max-instances=10

CLOUD_RUN_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --platform=managed --region="${REGION}" --format="value(status.url)")

echo ""
echo "=== DONE ==="
echo "Cloud Run URL: ${CLOUD_RUN_URL}/alert"
echo "Use this URL as your TradingView webhook."
echo "Service account key: config/service_account.json"
echo ""
echo "Next: copy config/.env.example to .env and fill in the values."
