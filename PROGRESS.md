# BingX Trading Bot — Progress

## 更新紀錄

| 日期 | 里程碑 | 狀態 | 備註 |
|------|--------|------|------|
| 2026-05-28 | 專案初始化 | ✅ 完成 | Fork + 目錄結構建立 |
| 2026-05-28 | Config module | ✅ 完成 | typed config, dotenv, unit tests |

## 待辦清單

- [x] Task 1: Fork repo + project setup
- [x] Task 2: Config module
- [ ] Task 3: Cloud Run webhook receiver
- [ ] Task 4: GCP infrastructure setup
- [ ] Task 5: BingX executor
- [ ] Task 6: Risk manager
- [ ] Task 7: Pub/Sub subscriber
- [ ] Task 8: Position monitor
- [ ] Task 9: Main entry point
- [ ] Task 10: Windows Service setup
- [ ] Task 11: End-to-end demo test

## 架構（簡版）

```
TradingView → Cloud Run → Pub/Sub → Windows Bot → BingX API
```

## Bot 狀態（由 position_monitor 自動更新）

_Bot 尚未啟動_
