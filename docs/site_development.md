---
lang: zh-Hant
---

# 文件站開發

網站使用 MkDocs 1.6.1，把現有 Markdown 建置成靜態頁面。
公開網站不會呼叫 localhost API，也不使用私人觀測快照。

`requirements-docs.txt` 適用本機開發；CI 使用 `requirements-docs.lock` 鎖定全部依賴與
SHA-256，並只安裝 wheels。此鎖檔對應 Python 3.13 / Linux x86_64。

## 本機建置

從專案根目錄建立獨立環境：

```bash
python3 -m venv .venv-docs
source .venv-docs/bin/activate
python -m pip install -r requirements-docs.txt
python -m mkdocs build --strict
python scripts/validate_site.py site
python -m mkdocs serve --dev-addr 127.0.0.1:8000
```

開啟 <http://127.0.0.1:8000/MinxiongHydroCast/>。正式網址使用 `/MinxiongHydroCast/` 前綴，首頁模板的
本機連結須使用 Jinja `url` filter，讓根路徑與子路徑預覽皆正確。

## 修改位置

| 檔案 | 用途 |
| --- | --- |
| `mkdocs.yml` | 導覽、搜尋、來源排除與連結驗證 |
| `docs/index.md` | GitHub 可讀的首頁內容與首頁模板設定 |
| `docs/theme/home.html` | 網站首頁模板 |
| `docs/theme/site_hooks.py` | 將翻譯 locale 轉為頁面的有效 HTML 語言標記 |
| `docs/assets/site.css` | 首頁與文件頁的共用視覺樣式 |
| `docs/documentation.md` | 完整文件入口 |
| `.github/workflows/docs.yml` | PR 建置檢查與 main 發布 |

技術文件保留英文；繁體中文入口提供閱讀路徑。
一般 Markdown 頁面連到另一文件時使用相對 `.md` 路徑，由 MkDocs 處理。
不要在 HTML 模板寫死網站根路徑。

## 驗證與發布

PR 必須通過嚴格建置及產生後的本機連結、圖片、錨點檢查。
檢查只讀取建置產物，不請求外部網站。
新頁面應另檢查手機寬度、鍵盤操作、搜尋與日期／資料來源說明。

GitHub Pages 的來源設定為 **GitHub Actions**。合併到 `main` 後，文件工作流程會
發布建置產物；PR 不會部署。手動發布也僅允許 `main`。
生成的 `site/`、主題來源 `docs/theme/` 與內部規劃 `docs/superpowers/` 不發布為文件內容。

部署證據是歷史紀錄。更新網站內容不等於驗證私人服務現況；維運數字必須附觀測日期，
並依[部署狀態](deployment_status.md)的記錄政策處理。
