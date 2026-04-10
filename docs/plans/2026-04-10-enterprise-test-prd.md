# PRD：HA Permission & Control 企業級全面測試計畫

## 1. 目標

對 `ha_permission_manager`、`ha_area_control`、`ha_label_control` 三套件進行商用企業部署等級的全面邊界測試，覆蓋所有先前未測試的範圍。

## 2. 測試環境

| 項目 | 規格 |
|------|------|
| HA 實例 | Podman 容器，localhost:15124 |
| 管理員 | admin / admin |
| 測試使用者 | test_user（非管理員） |
| 套件版本 | permission_manager 1.0.2, area_control 1.0.3, label_control 2.0.0 |

## 3. 測試範圍（10 輪）

### Round 1：權限邊界測試
- 1.1 管理員 vs 一般用戶：所有 8 個 WS handler 的回傳差異
- 1.2 未授權用戶（permission_level=0）存取 area/label 資源
- 1.3 授權用戶（permission_level=1）存取 area/label 資源
- 1.4 不存在的用戶 ID 查詢
- 1.5 set_permission 非管理員呼叫（應被拒絕）
- 1.6 get_admin_data 非管理員呼叫（應被拒絕）
- 1.7 自我權限修改（管理員修改自己的權限）

### Round 2：WebSocket API 錯誤處理與惡意輸入
- 2.1 缺少必要參數（area_id, label_id, user_id, resource_id, level）
- 2.2 空字串參數
- 2.3 超長字串（256+ 字元）
- 2.4 特殊字元注入（SQL: `'; DROP TABLE--`, XSS: `<script>alert(1)</script>`）
- 2.5 非法型別（level 傳字串、area_id 傳數字）
- 2.6 超出範圍（level=-1, level=2, level=999）
- 2.7 不存在的 area_id / label_id
- 2.8 不存在的 WebSocket type（如 `area_control/delete_area`）
- 2.9 Unicode 特殊字元（emoji、零寬字元、RTL 字元）

### Round 3：並發與競態條件
- 3.1 同時 100 個 get_permitted_areas 請求
- 3.2 同時讀寫權限（一邊 set，一邊 get）
- 3.3 快速連續 set_permission（同一 user+resource，不同 level）
- 3.4 多個 WebSocket 連線同時操作
- 3.5 set_permission 後立即 get 檢查一致性

### Round 4：資料持久化與重啟恢復
- 4.1 設定權限 → 重啟 HA → 驗證權限保留
- 4.2 儲存檔案損壞場景（空檔、無效 JSON）
- 4.3 大量權限記錄（100+ 用戶 × 50+ 資源）持久化
- 4.4 孤立權限清理（刪除 area/label 後權限記錄的處理）

### Round 5：前端靜態資源與 Panel 載入
- 5.1 所有 JS/CSS 檔案可存取性驗證
- 5.2 快取控制 header 檢查
- 5.3 lit.js bundle 完整性（可成功 import）
- 5.4 Panel 路由正確性（area-control, label-control, ha_permission_manager）
- 5.5 Content-Type 正確性

### Round 6：事件系統測試
- 6.1 set_permission 觸發 permission_manager_updated 事件
- 6.2 事件 payload 完整性（user_id, resource_id, level）
- 6.3 多訂閱者同時收到事件
- 6.4 area/label registry 變更觸發資源重新發現
- 6.5 面板增刪觸發資源更新

### Round 7：安全性測試
- 7.1 未認證 WebSocket 連線（無 token）
- 7.2 過期 token 的行為
- 7.3 非管理員越權嘗試所有 admin-only 端點
- 7.4 路徑遍歷攻擊（靜態檔案路徑）
- 7.5 XSS payload 在 resource_id 中的處理
- 7.6 IDOR（用其他用戶的 user_id 查詢權限）

### Round 8：效能與壓力測試
- 8.1 大量 area（50+）的效能
- 8.2 大量 entity（1000+）的效能
- 8.3 WebSocket 響應時間基準（P50, P95, P99）
- 8.4 前端 JS 檔案大小與載入效能
- 8.5 記憶體使用穩定性（多次操作後無洩漏）

### Round 9：部署相容性
- 9.1 三套件同時安裝（已測試 ✓）
- 9.2 僅安裝 area_control（無 permission_manager 的 standalone 模式）
- 9.3 僅安裝 label_control（standalone 模式）
- 9.4 config entry 重新載入（unload + reload）
- 9.5 integration 完全移除後再安裝

### Round 10：回歸端對端測試
- 10.1 完整流程：建立用戶 → 設定權限 → 驗證存取 → 修改權限 → 驗證變更
- 10.2 admin 面板：查看所有用戶、所有資源、設定矩陣
- 10.3 area control：摘要正確、實體分組正確、搜尋正確
- 10.4 label control：標籤列表、實體控制、domain 篩選
- 10.5 sidebar filter：受限面板隱藏、授權面板顯示
- 10.6 lovelace filter：受限儀表板隱藏

## 4. 通過標準

| 等級 | 標準 |
|------|------|
| PASS | 行為符合預期，回傳正確 |
| WARN | 功能正常但有改善空間（效能、訊息） |
| FAIL | 行為不符預期，存在缺陷 |
| CRITICAL | 安全漏洞或資料損壞 |

## 5. 企業部署要求

- 所有安全測試（Round 7）必須 PASS
- 所有權限邊界測試（Round 1）必須 PASS
- 效能基準（Round 8）響應時間 < 500ms
- 資料持久化（Round 4）零資料遺失
- 所有 CRITICAL/FAIL 問題必須修復後重測
