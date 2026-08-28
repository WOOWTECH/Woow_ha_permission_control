<p align="center">
  <img src="https://brands.home-assistant.io/_/homeassistant/icon.png" alt="Woow HA Permission Control" width="120"/>
</p>

<h1 align="center">Woow HA Permission Control</h1>

<p align="center">
  <strong>Home Assistant 面板、區域、標籤的個別使用者存取控制</strong><br/>
  單一整合、兩個面板，改權限不需重啟
</p>

<p align="center">
  <a href="#概述">概述</a> &bull;
  <a href="#兩個面板">面板</a> &bull;
  <a href="#安裝">安裝</a> &bull;
  <a href="#權限模型">權限模型</a> &bull;
  <a href="#服務">服務</a> &bull;
  <a href="#安全性">安全性</a> &bull;
  <a href="#畫面截圖">截圖</a>
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

---

## 概述

Home Assistant 的可見性模型對所有人一視同仁：每個使用者都看得到每個面板、每個區域、每個儀表板。這個整合補上「因人而異」的那一層——由管理員逐一決定每位使用者能看到哪些側邊欄面板、區域與標籤，其餘的 Home Assistant 根本不會發出去。

| 問題 | 這個整合怎麼解 |
|---|---|
| 所有使用者看到相同的側邊欄 | 逐使用者控制面板可見性，管理工具對一般使用者直接消失 |
| HA 沒有區域層級的存取控制 | 逐使用者授予或拒絕個別區域 |
| HA 沒有標籤層級的存取控制 | 逐使用者授予或拒絕個別標籤 |
| Lovelace 儀表板人人可見 | 被關閉的儀表板不會出現在瀏覽器收到的面板清單裡 |
| 權限散落在多個整合 | 一張管理矩陣：所有使用者 × 所有資源 |
| 改權限要重啟 | 事件驅動，側邊欄立即更新 |

> **從 v1.x 的三整合架構升級？** `ha_area_control` 與 `ha_label_control` 已不存在。請先讀 [CHANGELOG.md](CHANGELOG.md)——其中有一個很容易漏掉的 HACS custom repository 步驟。

## 兩個面板

### Permission Manager — `/ha_permission_manager`（僅管理員）

管理矩陣。所有使用者對所有資源排成一張表格，含 Panels / Areas / Labels 分頁、搜尋與批次操作。

### Control Panel — `/ha-control-panel`（所有使用者）

本整合唯一的裝置控制介面。區域與標籤是同一個面板的兩個分頁：領域摘要卡、領域分頁、搜尋，以及 15 種領域專屬磚（燈光、空調、窗簾、媒體播放器、門鎖……）可直接控制實體。每位使用者只會看到自己擁有 View 權限的內容。舊的獨立 Area Control 與 Label Control 面板為何被刪除，見 [ADR-0002](docs/adr/0002-control-panel-is-the-only-device-control-surface.md)。

## 安裝

### 前置需求

- Home Assistant **2025.1.0** 以上
- 建議路徑需要 [HACS](https://hacs.xyz/)

### 透過 HACS

1. HACS → 右上角三點選單 → **Custom repositories**
2. 加入 `https://github.com/WOOWTECH/Woow_ha_permission_control`（類型選 **Integration**）
3. 下載 **Woow HA Permission Control**，然後重啟 Home Assistant
4. 設定 → 裝置與服務 → **新增整合** → *Permission Manager*

> 如果你之前加過 `WOOWTECH/hacs-ha_permission_manager`、`WOOWTECH/hacs-ha_area_control` 或 `WOOWTECH/hacs-ha_label_control` 這三個 custom repository，**請移除它們**。它們已封存，而只要還留在清單裡，HACS 就會繼續餵你舊版本。

### 手動安裝

```bash
git clone https://github.com/WOOWTECH/Woow_ha_permission_control.git
cp -r Woow_ha_permission_control/custom_components/ha_permission_manager \
  /config/custom_components/
# 接著重啟 Home Assistant，並從介面新增整合
```

## 權限模型

**權限等級**設定在「使用者 × 資源」這一組配對上。等級只有兩種，資源只有三類。

| 等級 | 值 | 行為 |
|---|---|---|
| **View** | `1` | 使用者看得到也進得去 |
| **Closed** | `0` | 完全不在面板清單裡——側邊欄沒有這一列，直接輸入網址會落到 Home Assistant 自己的 `notfound` |

| 前綴 | 資源類型 | 範例 |
|---|---|---|
| `panel_` | 側邊欄面板 | `panel_ha-control-panel` |
| `area_` | Home Assistant 區域 | `area_living_room` |
| `label_` | Home Assistant 標籤 | `label_lighting` |

權限存放於 `.storage/ha_permission_manager`，重啟與升級都不會遺失。程式碼中使用的術語定義在 [CONTEXT.md](CONTEXT.md)。

## 服務

14 個服務涵蓋完整的權限 CRUD，可從自動化、REST 與 WebSocket API 呼叫。完整的雙語參考——每個服務的參數、YAML、curl 與 Python 範例——在 **[docs/services-guide.md](docs/services-guide.md)**。

```yaml
# 給某位使用者一個區域的 View 權限
action: ha_permission_manager.set_permission
data:
  user_id: aa4d4d107f79429990c52080056c2715
  resource_id: area_living_room
  level: 1
```

### WebSocket 指令

| 指令 | 對象 | 用途 |
|---|---|---|
| `permission_manager/get_all_permissions` | 任何使用者 | 呼叫者自己的權限 |
| `permission_manager/get_panel_permissions` | 任何使用者 | 呼叫者的面板可見性 |
| `permission_manager/get_admin_data` | 管理員 | 完整矩陣 |
| `permission_manager/set_permission` | 管理員 | 寫入單筆權限 |
| `area_control/get_permitted_areas` | 任何使用者 | 呼叫者可檢視的區域 |
| `area_control/get_area_entities` | 任何使用者 | 已授權區域中的實體 |
| `label_control/get_permitted_labels` | 任何使用者 | 呼叫者可檢視的標籤 |
| `label_control/get_label_entities` | 任何使用者 | 已授權標籤中的實體 |

`area_control/*` 與 `label_control/*` 這兩組名稱在它們所屬的 domain 消失後仍然保留，這是刻意的——見 [ADR-0004](docs/adr/0004-websocket-command-names-are-frozen.md)。

## 安全性

寫入操作與完整矩陣僅限管理員；一般使用者的 WebSocket 連線只能讀取自己的權限，其餘一律讀不到。

- `set_permission` 與 `get_admin_data` 需要 `is_admin` 旗標
- 所有 WebSocket 參數以 `voluptuous` schema 驗證
- 資源 ID 只接受 `panel_`、`area_`、`label_` 三種前綴
- 等級只接受 `0` 與 `1`
- 全程沒有原生 SQL，資料存取一律經由 Home Assistant
- 權限儲存為 `.storage` JSON 檔，不會經由 HTTP 對外暴露
- **Panel Gate** 包住 Home Assistant 自己的 `get_panels`，使用者無 View 權限的面板根本不會送到瀏覽器

> 決定發生在 Home Assistant，不在瀏覽器。自 v2.0.13 起，本整合不再送出任何「把頁面上的東西藏起來」
> 的程式碼——因為頁面上根本沒有那個東西可藏。這仍然**不能取代** Home Assistant 本身的身分驗證，
> 原因見下方「停用本整合」那段。

> **停用本整合會解除所有限制。** 整合卸載時 Panel Gate 會把 `get_panels` 交還給 Home
> Assistant，所有使用者立刻看得到所有面板，不需要重啟。這是刻意的：管理員把自己鎖在
> 外面時就是這樣救回來的，也是為什麼這套權限模型是「安排使用者看到什麼」而不是資安邊界
> ——能停用整合的人就能推翻全部設定。詳見
> [ADR-0011](docs/adr/0011-the-panel-decision-moves-into-the-backend.md)。

## 畫面截圖

Control Panel 與 Permission Manager，三種主題的明暗兩版。

| | Control Panel | Permission Manager |
|---|---|---|
| Woow | <img src="screenshots/Woow_light_CP.png" width="320"/> | <img src="screenshots/Woow_light_PM.png" width="320"/> |
| Woow（深色） | <img src="screenshots/Woow_dark_CP.png" width="320"/> | <img src="screenshots/Woow_dark_PM.png" width="320"/> |
| Google | <img src="screenshots/Google_Theme_light_CP.png" width="320"/> | <img src="screenshots/Google_Theme_light_PM.png" width="320"/> |
| Frosted Glass | <img src="screenshots/Frosted_Glass_dark_CP.png" width="320"/> | <img src="screenshots/Frosted_Glass_dark_PM.png" width="320"/> |

## 專案結構

```
custom_components/ha_permission_manager/
├── __init__.py          setup、面板註冊、權限 CRUD
├── const.py             domain、前綴、面板與服務名稱
├── config_flow.py       單一實例 config flow
├── discovery.py         探索面板、區域與標籤
├── panel_gate.py        包住 Home Assistant get_panels 的 Panel Gate
├── panel_policy.py      使用者可以收到哪些面板——唯一的答案
├── services.py          14 個服務
├── websocket_api.py     8 個 WebSocket 指令
├── users.py             使用者查詢
└── frontend/            兩個面板、lit.js 與 sidebar-title.js，
                         掛載於 /ha_permission_manager_frontend
CONTEXT.md               術語表——貢獻前請先讀
docs/adr/                為什麼會長成現在這樣
docs/services-guide.md   完整服務參考（英 / 中）
tests/                   REST 功能測試與 Playwright UI 驗證
```

## 參與貢獻

請先讀 [CONTEXT.md](CONTEXT.md) 了解術語，以及 [docs/adr/](docs/adr/) 了解已經拍板的決定。若你的變更與某篇 ADR 相牴觸，請在 PR 中明說，不要繞過它。

問題回報：<https://github.com/WOOWTECH/Woow_ha_permission_control/issues>

## 授權

[MIT](LICENSE)
