# Findings & Decisions

## Requirements
- 安裝 Woow_ha_theme 到 HA 測試環境 (localhost:15124)
- 使用 Playwright CLI 自動化測試
- 驗證 3 個自訂面板 UI 是否正確跟隨主題 CSS 變數
- 測試 3 主題 × 2 模式 (light/dark) = 6 場景
- 每場景截圖 4 面板 = 共 24 組
- 用 computed CSS 值 vs YAML 定義值做客觀比對

## Research Findings

### Theme 套件結構
- Repo: https://github.com/WOOWTECH/Woow_ha_theme
- 12 個 YAML 檔案，52 個子主題
- HACS 相容，filename: `themes/*.yaml`
- content_in_root: false → themes/ 目錄下

### 目標主題 YAML 分析
- **woow.yaml**: `Woow` 主題，有 `modes:` light/dark，主色 `#3d8ef0`
- **Frosted Glass.yaml**: 需確認是否有 modes 支援
- **google_theme.yaml**: 需確認結構

### HA 測試環境現狀
- 容器: ha_test, port 15124
- configuration.yaml 已有 `frontend: themes: !include_dir_merge_named themes`
- 三個自訂整合全部 state=loaded
- 四個面板: ha_permission_manager, ha-control-panel, area-control, label-control
- Demo 整合已啟用，259 個實體
- 6 個分區、5 個標籤已建立

### 面板 URL 路徑
- 權限管理器: /ha_permission_manager
- 控制面板: /ha-control-panel
- 分區控制: /area-control
- 標籤控制: /label-control

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 使用 Playwright CLI skill | 用戶指定使用此工具 |
| headless chromium | 伺服器環境無 X server |
| Shadow DOM 穿透取 CSS | HA 使用 LitElement shadow DOM |
| 截圖存 /tmp/ha-theme-test/ | 不汙染專案目錄 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
|       |            |

## Resources
- Theme repo: /tmp/Woow_ha_theme/
- HA: http://localhost:15124
- Auth: admin / admin

## Visual/Browser Findings
<!-- CRITICAL: Update after every 2 view/browser operations -->
-

---
*Update this file after every 2 view/browser/search operations*
