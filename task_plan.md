# Task Plan: HA Theme × Custom Panel 前端 UI 驗證

## Goal
安裝 Woow_ha_theme 主題套件到 HA 測試環境，使用 Playwright 自動化測試驗證 3 個自訂面板（權限管理器、分區控制、標籤控制、控制面板）在 3 個代表性主題 × 2 模式（light/dark）下的前端 UI 是否正確跟隨主題 CSS 變數變化。共 24 組截圖 + CSS 值比對。

## Current Phase
Phase 1

## Test Matrix
| # | 主題 | 模式 | 面板 |
|---|------|------|------|
| 1-4 | Woow | Light | PM / CP / AC / LC |
| 5-8 | Woow | Dark | PM / CP / AC / LC |
| 9-12 | Frosted Glass | Light | PM / CP / AC / LC |
| 13-16 | Frosted Glass | Dark | PM / CP / AC / LC |
| 17-20 | Google Theme | Light | PM / CP / AC / LC |
| 21-24 | Google Theme | Dark | PM / CP / AC / LC |

面板代號：PM=權限管理器, CP=控制面板, AC=分區控制, LC=標籤控制

## CSS 驗證項目
| 驗證項目 | CSS 變數 | 檢查方式 |
|----------|----------|----------|
| Sidebar 背景色 | `--sidebar-background-color` | computed style vs YAML |
| Sidebar 選中色 | `--sidebar-selected-text-color` | computed style vs YAML |
| 卡片背景 | `--ha-card-background` | computed style vs YAML |
| 主色調 | `--primary-color` | computed style vs YAML |
| 文字顏色 | `--primary-text-color` | computed style vs YAML |
| 文字對比度 | text vs background | 可讀性判斷 |

## Phases

### Phase 1: 主題套件安裝部署
- [ ] 將 Woow_ha_theme/themes/ 複製到 HA config/themes/
- [ ] 確認 configuration.yaml 有 `!include_dir_merge_named themes` 設定
- [ ] 重啟 HA 驗證主題載入
- [ ] 透過 API 確認 3 個目標主題可用
- **Status:** in_progress

### Phase 2: Playwright 測試腳本建立
- [ ] 安裝 Playwright 並設定 headless browser
- [ ] 建立自動登入 HA 的腳本
- [ ] 建立主題切換 + 深淺色模式切換功能
- [ ] 建立面板導航 + 截圖功能
- [ ] 建立 CSS computed style 抽取功能
- **Status:** pending

### Phase 3: 執行 24 組測試
- [ ] 逐一切換主題/模式/面板，截圖並抽取 CSS 值
- [ ] 將 CSS 值與主題 YAML 定義比對
- [ ] 記錄每組測試 PASS/FAIL
- **Status:** pending

### Phase 4: 結果分析與報告
- [ ] 彙整 24 組截圖到 screenshots/ 目錄
- [ ] 產生測試報告（PASS/FAIL 統計、CSS 差異表）
- [ ] 標註任何主題不跟隨的問題
- **Status:** pending

## Key Questions
1. Playwright 能否在 headless 模式下正確渲染 HA 的 shadow DOM？
2. 主題切換後是否需要等待 re-render 才能抓取正確 CSS 值？
3. Frosted Glass 的半透明效果在 computed style 中如何表示？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 選 Woow/Frosted Glass/Google Theme | 視覺差異最大，涵蓋簡約/毛玻璃/Material 三種風格 |
| 用 Playwright JS 抽取 CSS 值 | 比純截圖更客觀，可量化比對 |
| 24 組 = 3主題 × 2模式 × 4面板 | 完整覆蓋所有組合 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- HA 運行於 localhost:15124
- 登入帳號: admin / admin
- 主題 YAML 位於 /tmp/Woow_ha_theme/themes/
