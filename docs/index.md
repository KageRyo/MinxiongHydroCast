---
title: 民雄水文氣象觀測與研究
template: home.html
lang: zh-Hant
---

# MinxiongHydroCast

MinxiongHydroCast 整理民雄與嘉義的官方雨量、淹水深度和雷達資料，記錄來源、時間及品質，
供降雨臨近預報研究使用。文件也說明如何重現研究流程。

專案目前是內部觀測與資料／模型開發原型。公開文件站沒有即時資料連線；
實驗預報與風險通知尚未通過全部發布條件。

- [快速開始](getting_started.md)：不用 API key 的合成資料示範。
- [操作維運](operational_use.md)：資料時效、API、備份與 shadow 條件。
- [資料與研究](data_assets.md)：事件切分、雷達轉換與模型比較。
- [開發貢獻](contributing.md)：契約測試、區域設定與文件站開發。
- [完整文件總覽](documentation.md)。

## 證據與限制

2026-10-15 的[部署驗證](deployment_status.md#verification-update-2026-10-15)顯示，檢查當下 API 正常，資料也已就緒。
但在 192 小時的觀察期內，收集成功率和資料就緒率都低於門檻，最長有 20 小時未達就緒條件。
[五事件模型評估](baseline_results.md#reproducible-five-event-cwa-baseline)顯示，Tiny U-Net 降低了整體 RMSE，
但部分事件的 CSI 和部分預報時距的評估結果變差，仍未達預報發布門檻。

官方警戒由主管機關發布。雷達回波、雨量與淹水深度是不同物理量；
本專案不取代官方警報或緊急決策。詳見[專案範圍](project_scope.md)。
