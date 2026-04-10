# Home Assistant 權限管理器

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1.0%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.2-blue.svg)](https://github.com/WOOWTECH/Woow_ha_permission_control/releases)

[English](README.md)

一個 Home Assistant 自訂整合，為非管理員使用者提供細緻的權限管理。透過視覺化管理介面，控制每位使用者可存取的側邊欄面板、區域和標籤。

## 功能特色

- **面板權限** — 依使用者顯示或隱藏側邊欄面板（儀表板、附加元件、工具等）
- **區域權限** — 控制每位使用者可見的區域及其實體
- **標籤權限** — 控制每位使用者可見的標籤及其實體
- **權限矩陣** — 視覺化管理面板，提供試算表風格的矩陣，方便快速設定
- **控制面板** — 統一儀表板，顯示區域/標籤摘要及實體數量
- **即時生效** — 透過 JavaScript 即時套用側邊欄篩選與內容篩選
- **存取拒絕頁面** — 使用者導航至受限面板時顯示友善的重導向頁面
- **儲存庫持久化** — 權限儲存於 `.storage/`（不會產生多餘實體）
- **事件驅動清理** — 當使用者或資源被刪除時，自動移除相關權限
- **雙語介面** — 支援英文與繁體中文面板標題

## 截圖

### 權限矩陣
從單一試算表風格的介面管理所有使用者權限：

![權限矩陣](screenshots/permission-matrix-zh.png)

### 控制面板 — 區域
檢視區域摘要，包含依領域分組的實體數量：

![控制面板 - 區域](screenshots/control-panel-areas-zh.png)

### 控制面板 — 標籤
檢視標籤摘要及實體統計資訊：

![控制面板 - 標籤](screenshots/control-panel-labels-zh.png)

## 系統需求

- Home Assistant **2025.1.0** 或更新版本
- 至少一個非管理員使用者

## 安裝方式

### HACS（建議）

1. 在 Home Assistant 中開啟 HACS
2. 點選右上角的三點選單，選擇**自訂儲存庫**
3. 新增 `https://github.com/WOOWTECH/Woow_ha_permission_control` 作為**整合**類型
4. 搜尋 **Permission Manager** 並點選**下載**
5. 重新啟動 Home Assistant

### 手動安裝

1. 從此儲存庫下載 `custom_components/ha_permission_manager` 資料夾
2. 複製到您的 Home Assistant `config/custom_components/` 目錄
3. 重新啟動 Home Assistant

## 設定

1. 前往**設定** > **裝置與服務**
2. 點選**新增整合**並搜尋 **Permission Manager**
3. 依照設定精靈操作 — 系統會建立必要的儲存空間並註冊管理面板

無需 YAML 設定。

## 儀表板

安裝完成後，整合會自動建立兩個儀表板：

### 權限控制面板（僅限管理員）

此管理儀表板**僅對管理員使用者可見**。管理員可在此設定三個類別的權限：

- **面板** — 控制每位使用者在 Home Assistant 中可存取的側邊欄項目（儀表板、附加元件、工具等）
- **區域** — 控制每位使用者在控制面板儀表板中可見的區域
- **標籤** — 控制每位使用者在控制面板儀表板中可見的標籤

### 控制面板

此儀表板**對管理員和非管理員使用者皆可見**。顯示區域和標籤的摘要及實體數量，並依據每位使用者的權限進行篩選。非管理員使用者僅能看到被授權存取的區域和標籤。

## 使用方式

### 權限等級

| 等級 | 值 | 說明 |
|------|-----|------|
| **關閉** | 0 | 資源對使用者隱藏 |
| **檢視** | 1 | 資源對使用者可見 |

### 面板權限

面板權限控制使用者可見的側邊欄項目。當面板設為**關閉**時，該項目會從使用者的側邊欄移除，且直接透過網址存取會顯示存取拒絕頁面。

### 區域權限

區域權限控制在控制面板中可見的區域。屬於受限區域的實體會從使用者的視圖中篩除。

### 標籤權限

標籤權限控制在控制面板中可見的標籤。屬於受限標籤的實體會從使用者的視圖中篩除。

### 管理員使用者

管理員使用者始終擁有完整存取權限 — 不會對其套用權限限制。權限管理器面板本身僅對管理員使用者可見。

## 疑難排解

**安裝後面板未出現在側邊欄：**
重新啟動 Home Assistant 並清除瀏覽器快取。

**權限變更未生效：**
變更會即時套用。請嘗試重新整理瀏覽器。如果使用 CDN 或反向代理，可能需要清除快取的頁面。

**使用者仍能短暫看到受限內容：**
側邊欄篩選腳本在頁面載入後執行。系統會顯示短暫的載入覆蓋層以防止內容閃現。

## 授權條款

本專案採用 MIT 授權條款 — 詳見 [LICENSE](LICENSE) 檔案。
