---
lang: zh-Hant
---

# 開發與貢獻

適合從合成範例、資料來源契約測試、區域設定或文件改善開始。
完整開發設定與 PR 規範見 [CONTRIBUTING](https://github.com/KageRyo/MinxiongHydroCast/blob/main/CONTRIBUTING.md)。

## 選擇工作

- 程式開發：[Adapter 開發](adapter_development.md)與[資料契約](data_contracts.md)。
- 區域移植：[Region profiles](region_profiles.md)。
- 文件與網站：[文件站開發](site_development.md)。
- 研究重現：[資料資產](data_assets.md)與[基準模型結果](baseline_results.md)。
- 查看待辦：[任務清單](tasks.md)與[公開 Issues](https://github.com/KageRyo/MinxiongHydroCast/issues)。

## GitHub flow

從最新 `main` 建立功能分支，完成小範圍修改與驗證後開 PR，通過檢查及審查再合併。
提交訊息遵循 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)，
例如 `docs: clarify observation freshness` 或 `feat(docs): add project homepage`。

請使用合成 fixtures 測試；官方原始資料、API key、部署路徑、私人事件審查紀錄與
模型權重不應加入 PR。程式授權與第三方資料的再散布權利是不同問題，請參閱
[資料來源登錄](data_source_register.md)。
