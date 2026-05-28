# BingX Trading Bot — Progress

## 更新紀錄

| 日期 | 里程碑 | 狀態 | 備註 |
|------|--------|------|------|
| 2026-05-28 | 專案初始化 | ✅ 完成 | Fork + 目錄結構建立 |
| 2026-05-28 | Config module | ✅ 完成 | typed config, dotenv, unit tests |
| 2026-05-28 | Cloud Run webhook receiver | ✅ 完成 | FastAPI, secret validation, Pub/Sub publish |
| 2026-05-28 | GCP setup script | ✅ 完成 | Pub/Sub + Cloud Run one-shot deploy |
| 2026-05-28 | BingX executor | ✅ 完成 | HMAC auth, place/close order, dry-run mode |
| 2026-05-28 | Risk manager | ✅ 完成 | circuit breaker, position limit, size cap, daily reset |
| 2026-05-28 | Pub/Sub subscriber | ✅ 完成 | streaming pull, ACK on success, NACK on error |
| 2026-05-28 | Position monitor | ✅ 完成 | background thread, PROGRESS.md auto-update |

## 待辦清單

- [x] Task 1: Fork repo + project setup
- [x] Task 2: Config module
- [x] Task 3: Cloud Run webhook receiver
- [x] Task 4: GCP infrastructure setup
- [x] Task 5: BingX executor
- [x] Task 6: Risk manager
- [x] Task 7: Pub/Sub subscriber
- [x] Task 8: Position monitor
- [ ] Task 9: Main entry point
- [ ] Task 10: Windows Service setup
- [ ] Task 11: End-to-end demo test

## 架構（簡版）

```
TradingView → Cloud Run → Pub/Sub → Windows Bot → BingX API
```

## Bot 狀態（由 position_monitor 自動更新）

_Bot 尚未啟動_
