# 自動導入 CSV 功能指南

## 概述

租賃分析 MVP 系統現已支持**自動導入** CSV 檔案功能。系統啟動時會自動掃描 `upload` 資料夾並將所有 CSV 檔案導入到數據庫。

## 功能特性

✅ **自動掃描**：系統啟動時自動掃描 `upload` 資料夾中的所有 CSV 檔案
✅ **智能導入**：自動檢測新房源和已刪除房源
✅ **增量更新**：支持增量更新，不會重複導入相同房源
✅ **詳細日誌**：導入過程中顯示詳細的進度信息

## 使用方式

### 1. 準備 CSV 檔案

將您的 CSV 檔案放入 `upload` 資料夾中。CSV 檔案應包含以下列：

| 列名 | 說明 | 必需 |
|------|------|------|
| 標題 | 房源標題 | ✅ |
| 地址 | 房源地址 | ✅ |
| 租金 | 月租金（數字） | ✅ |
| 坪數 | 房源面積（數字） | ✅ |
| 房型 | 房間類型（如：1房1廳） | ✅ |
| 樓層 | 樓層信息 | ✅ |
| 緯度 | 房源緯度 | ✅ |
| 經度 | 房源經度 | ✅ |
| 裝修狀態 | 裝修狀態（已裝修/未裝修） | ✅ |

### 2. 啟動系統

在 Windows 上運行：

```bash
py -3.11 -m uvicorn main_v4:app --reload
```

在 Linux/Mac 上運行：

```bash
python3.11 -m uvicorn main_v4:app --reload
```

### 3. 查看導入結果

系統啟動時會在控制台顯示導入進度：

```
📁 找到 51 個 CSV 檔案，開始導入...
  ⏳ 正在導入: 公寓套房_20260110.csv
  ✅ 公寓套房_20260110.csv: 新增 416, 刪除 0
  ⏳ 正在導入: 公寓整層_20260110.csv
  ✅ 公寓整層_20260110.csv: 新增 1359, 刪除 0
  ...
✅ CSV 自動導入完成！
```

### 4. 訪問系統

打開瀏覽器訪問：

```
http://localhost:8000
```

您應該能看到地圖上顯示所有導入的房源。

## 文件夾結構

```
rental_mvp_deployment/
├── main_v4.py              # 後端 FastAPI 應用
├── index_v6.html           # 前端 HTML 文件
├── rental.db               # SQLite 數據庫（自動創建）
├── requirements.txt        # Python 依賴
├── upload/                 # CSV 檔案目錄
│   ├── 公寓套房_20260110.csv
│   ├── 公寓整層_20260110.csv
│   └── ...
└── ...
```

## 導入過程詳解

### 1. 啟動事件 (Startup Event)

```python
@app.on_event("startup")
async def startup_event():
    """應用啟動時初始化數據庫並自動導入 CSV"""
    init_database()
    auto_import_csv_files()
```

### 2. 自動導入函數 (Auto Import Function)

```python
def auto_import_csv_files():
    """自動導入 upload 資料夾中的所有 CSV 檔案"""
    # 1. 掃描 upload 資料夾
    # 2. 讀取每個 CSV 檔案
    # 3. 檢查房源是否已存在
    # 4. 新增新房源或更新現有房源
    # 5. 標記已刪除的房源
```

### 3. 房源匹配邏輯

系統使用 **地址 + 租金** 作為房源唯一標識：

```python
cursor.execute("""
    SELECT id FROM properties 
    WHERE address = ? AND rent_monthly = ?
""", (address, rent))
```

如果找到匹配的房源，系統會更新其狀態；否則創建新房源。

### 4. 已刪除房源處理

系統會自動檢測已刪除的房源（在新數據中不存在但在舊數據中存在的房源）並標記為 `deleted`。

## 數據庫表結構

### properties 表

| 列名 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| title | TEXT | 房源標題 |
| address | TEXT | 房源地址 |
| rent_monthly | INTEGER | 月租金 |
| area | REAL | 房源面積 |
| room_type | TEXT | 房間類型 |
| floor | TEXT | 樓層信息 |
| latitude | REAL | 緯度 |
| longitude | REAL | 經度 |
| building_type | TEXT | 建築類型 |
| renovation_status | TEXT | 裝修狀態 |
| first_published_date | TEXT | 首次發佈日期 |
| upload_week | TEXT | 上傳週次 |
| status | TEXT | 房源狀態 (active/deleted) |
| deleted_date | TEXT | 刪除日期 |

### versions 表

| 列名 | 類型 | 說明 |
|------|------|------|
| week_id | TEXT | 週次 ID |
| upload_date | TEXT | 上傳日期 |

## 故障排除

### 問題 1：CSV 檔案未被導入

**原因**：
- `upload` 資料夾不存在
- CSV 檔案名稱不以 `.csv` 結尾
- CSV 檔案編碼不是 UTF-8

**解決方案**：
1. 確保 `upload` 資料夾存在
2. 檢查 CSV 檔案名稱
3. 使用 UTF-8 編碼保存 CSV 檔案

### 問題 2：導入過程中出現錯誤

**原因**：
- CSV 檔案列名不匹配
- 數據類型不正確（如租金不是數字）

**解決方案**：
1. 檢查 CSV 檔案列名是否正確
2. 確保數據類型正確
3. 查看控制台錯誤信息

### 問題 3：房源未在地圖上顯示

**原因**：
- 緯度/經度為 0 或無效
- 房源狀態不是 `active`

**解決方案**：
1. 檢查 CSV 檔案中的緯度/經度
2. 查詢數據庫確認房源狀態

## 性能考慮

- 導入 2,383 個房源通常需要 5-10 秒
- 首次導入會創建索引，後續導入會更快
- 建議定期備份 `rental.db` 檔案

## API 端點

導入完成後，您可以通過以下 API 端點訪問數據：

- `GET /api/versions` - 獲取所有版本信息
- `GET /api/statistics` - 獲取統計信息
- `POST /api/import_data` - 手動導入數據（可選）

## 常見問題

**Q: 能否手動導入 CSV 檔案？**
A: 是的，系統仍然支持通過 `/api/import_data` 端點手動導入。

**Q: 導入時是否會覆蓋現有數據？**
A: 不會。系統使用智能匹配邏輯，只會更新已存在的房源或添加新房源。

**Q: 能否導入多個版本的 CSV 檔案？**
A: 是的。系統支持增量導入，每次導入都會記錄新的版本信息。

## 支持

如有問題，請查看：
- 控制台日誌信息
- `rental.db` 數據庫內容
- 本指南的故障排除部分
