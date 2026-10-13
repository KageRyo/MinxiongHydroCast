---
title: 民雄水文氣象觀測與研究
template: home.html
---

# MinxiongHydroCast

從官方觀測，走向可驗證的降雨研究。

整理民雄／嘉義的官方雨量、淹水深度與雷達資料，保存來源、時間與品質，
建立可重現的降雨臨近預報研究流程。

專案目前是內部觀測與資料／模型開發原型。公開文件站沒有即時資料連線；
實驗預報與風險通知尚未通過全部發布條件。

- [快速開始](getting_started.md)：不用 API key 的合成資料示範。
- [操作維運](operational_use.md)：資料時效、API、備份與 shadow 條件。
- [資料與研究](data_assets.md)：事件切分、雷達轉換與模型比較。
- [開發貢獻](contributing.md)：契約測試、區域設定與文件站開發。
- [完整文件總覽](documentation.md)。

## 證據與限制

[部署紀錄](deployment_status.md)保存 2026-07-29 的歷史驗證與 2026-09-12 的
WRA 資料時效事件；這些紀錄不能代表今天的服務健康。
[五事件模型評估](baseline_results.md#reproducible-five-event-cwa-baseline)顯示
Tiny U-Net 改善 RMSE，但部分 CSI 與預報時距退步，預報發布仍受阻擋。

官方警戒由主管機關發布。雷達回波、雨量與淹水深度是不同物理量；
本專案不取代官方警報或緊急決策。詳見[專案範圍](project_scope.md)。
