# API 與狀態判讀

API 是 localhost 觀測服務的一部分，與公開靜態文件站分開。先依
[快速開始](getting_started.md)啟動示範；以下請求不需要憑證。

## 端點

| GET 路徑 | 回應內容 |
| --- | --- |
| `/healthz` | 程序存活，`{"status":"ok"}` |
| `/readyz` | 完整資料狀態；未就緒時 HTTP 503 |
| `/metrics` | Prometheus 文字格式的狀態、時效與重試指標 |
| `/api/v1/status` | 最近快照、最近嘗試、各來源品質與時效 |
| `/api/v1/official-alerts/rainfall` | 官方降雨警戒與來源資訊 |
| `/api/v1/observations/rain-gauges` | 雨量站觀測 |
| `/api/v1/observations/flood-sensors` | 淹水深度觀測 |
| `/api/v1/features/region` | 區域彙整與覆蓋情況 |
| `/api/v1/locations` | 與快照一致的位置參考 |
| `/api/v1/shadow-readiness` | Shadow 指標、條件與阻擋原因 |
| `/api/v1/experimental-forecasts` | 明確表示實驗預報尚不可用 |

## 可重現的請求

```bash
curl -i http://127.0.0.1:8080/healthz
curl -i http://127.0.0.1:8080/readyz
curl --silent http://127.0.0.1:8080/api/v1/observations/rain-gauges
curl --silent http://127.0.0.1:8080/api/v1/shadow-readiness
curl --silent http://127.0.0.1:8080/api/v1/experimental-forecasts
```

預報端點目前的完整回應：

```json
{
  "schema_version": 1,
  "available": false,
  "product_type": "experimental_forecast",
  "notice": "Experimental model output. Not an official warning and not for automated public action.",
  "reason": "No forecast has passed the model and shadow-deployment gates.",
  "records": []
}
```

HTTP 200 在這裡代表成功取得「預報不可用」的狀態，並非預報已經發布。

資料端點包含 `schema_version`、`snapshot_id`、`generated_at`、`mode`、`dataset`、
`product_type`、`notice`、`health`、`source`、`row_count` 與 `records`。
`row_count` 必須等於記錄數量；觀測欄位與單位定義見[資料契約](data_contracts.md)。
`records` 內的值是字串，計算前必須依契約解析數值和單位。

## HTTP 與資料品質是不同層次

| 現象 | 判讀與處理 |
| --- | --- |
| `/healthz` 回傳 200 | 程序存活；仍須檢查 `/readyz` |
| `/readyz` 回傳 503 | 讀取 JSON 的 `state`、`failure_reason` 與 `datasets` 判斷原因 |
| `mode=demo` | 合成資料；不能用於目前天氣或正式預報 |
| 資料健康狀態 `stale` | 觀測時間超過新鮮度上限；新的抓取時間不能使舊觀測變新 |
| `degraded` 或 `upstream_unhealthy` | 來源降級或上游異常；檢查來源與原因，不以舊資料滿足 readiness |
| `coverage_missing` | 區域覆蓋不足；資料筆數多不等於民雄有可用觀測 |
| `collector_error` | 最近蒐集失敗；即使保留舊快照也不能解讀為最新成功 |
| `storage_error` | 指標、快照或校驗失敗；依[事件處理](incident_response.md)調查 |
| 官方警戒 `outcome=empty` 且 `records=[]` | 已驗證的空官方警戒產品；不是缺失資料，也不保證沒有淹水 |
| HTTP 503，`error="dataset unavailable"` | 該資料產品無法讀取；不能當成健康的空警戒 |
| HTTP 404，`error="not found"` | 路徑不存在；確認使用 `/api/v1/` 的已列出端點 |

Readiness 的頂層狀態可能是 `unhealthy`，而個別資料產品的原因是 `stale`。
應同時檢查頂層與 `datasets`，不要只看 HTTP 狀態或單一顏色。

## 來源與時間

`source` 記錄發布者、資料集 ID、抓取時間、來源型態、結果及校驗資訊。
`health.observed_at` 是觀測時間，`health.age_minutes` 是資料年齡，
`health.max_age_minutes` 是該來源的新鮮度門檻。`generated_at` 是產品產生時間，
不能代替觀測時間。[WRA 時效事件](wra_freshness_evidence.md)提供實際案例。

## 預報與通知

資料 `ready=true` 不會自動通過 shadow 或模型門檻。
`shadow_gate_passed`、`notification_allowed`、模型評估與人工決策各有獨立條件。
詳見[操作指南](operational_use.md#production-gates)與[決策權責](decision_authority.md)。

服務預設綁定 `127.0.0.1`。對外提供 API 前須完成既有的身份驗證、TLS、維運與
資料使用條件；公開文件站不會改變這些條件。
