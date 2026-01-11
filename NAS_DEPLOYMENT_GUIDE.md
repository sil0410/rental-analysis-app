# Synology DS420+ Docker 部署指南

## 📋 目錄
1. [環境準備](#環境準備)
2. [NAS 文件夾設置](#nas-文件夾設置)
3. [Docker 部署](#docker-部署)
4. [內部網絡訪問](#內部網絡訪問)
5. [外網訪問設置](#外網訪問設置)
6. [數據庫更新](#數據庫更新)
7. [故障排除](#故障排除)

---

## 環境準備

### 前置條件
- ✅ Synology DS420+ NAS
- ✅ 已安裝 Container Manager（舊版本稱為 Docker）
- ✅ 管理員權限
- ✅ 至少 2GB 可用空間

### 檢查 Container Manager 版本
1. 打開 NAS 控制面板
2. 進入「套件中心」
3. 搜索「Container Manager」
4. 確認已安裝（如未安裝，請先安裝）

---

## NAS 文件夾設置

### 第 1 步：創建必要文件夾

在 NAS 上創建以下文件夾結構：

```
/volume1/docker/
├── rental_app/           # 應用代碼
├── rental_data/          # 數據庫文件
└── rental_uploads/       # CSV 上傳文件夾
```

**操作步驟：**

1. 打開 NAS 上的「File Station」
2. 進入 `/volume1/docker/` 文件夾（如不存在，先創建 `docker` 文件夾）
3. 創建三個子文件夾：
   - `rental_app`
   - `rental_data`
   - `rental_uploads`

### 第 2 步：上傳應用文件

將以下文件上傳到 `/volume1/docker/rental_app/`：

```
rental_app/
├── main_v4.py              # 後端應用
├── index_v6.html           # 前端頁面
├── requirements.txt        # Python 依賴
├── docker-compose-nas.yml  # Docker 配置（可選）
└── upload/                 # 軟鏈接到 ../rental_uploads
```

**上傳方式：**
1. 使用 File Station 直接上傳
2. 或使用 FTP 客戶端（如 FileZilla）

### 第 3 步：上傳 CSV 文件

將您的 CSV 文件上傳到 `/volume1/docker/rental_uploads/`

```
rental_uploads/
├── 591_中和區_公寓_整層住家_page1.csv
├── 591_中和區_公寓_整層住家_page2.csv
└── ... (其他 CSV 文件)
```

---

## Docker 部署

### 方式 A：使用 Container Manager UI（推薦新手）

#### 第 1 步：打開 Container Manager

1. 打開 NAS 控制面板
2. 找到「Container Manager」
3. 點擊打開

#### 第 2 步：創建容器

1. 左側菜單 → 「映像」
2. 搜索 `python:3.11-slim`
3. 下載該映像

#### 第 3 步：創建容器

1. 左側菜單 → 「容器」
2. 點擊「新建」
3. 選擇 `python:3.11-slim` 映像
4. 設置以下參數：

**基本設置：**
- 容器名稱：`rental_analysis_app`
- 自動重啟：✅ 啟用

**高級設置：**
- 啟用特權容器：✗ 不需要

**卷掛載：**
| 文件夾路徑 | 掛載點 | 說明 |
|-----------|------|------|
| `/volume1/docker/rental_app` | `/app` | 應用代碼 |
| `/volume1/docker/rental_data` | `/app/data` | 數據庫 |
| `/volume1/docker/rental_uploads` | `/app/upload` | CSV 文件 |

**端口設置：**
| 容器端口 | NAS 端口 | 說明 |
|---------|---------|------|
| 8000 | 8000 | Web 應用 |

**環境變量：**
```
PYTHONUNBUFFERED=1
DB_PATH=/app/data/rental.db
```

**執行命令：**
```bash
sh -c "pip install -q -r requirements.txt && python -m uvicorn main_v4:app --host 0.0.0.0 --port 8000"
```

#### 第 4 步：啟動容器

1. 點擊「應用」保存設置
2. 在容器列表中找到 `rental_analysis_app`
3. 點擊「啟動」

#### 第 5 步：檢查日誌

1. 選擇容器 `rental_analysis_app`
2. 點擊「日誌」標籤
3. 查看是否有錯誤信息

**預期日誌：**
```
📁 找到 X 個 CSV 檔案，開始合併導入...
✅ 已合併 XXX 行數據
✅ 去重後 XXX 行數據
✅ CSV 導入完成！
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### 方式 B：使用 SSH 命令（進階用戶）

#### 第 1 步：連接到 NAS

```bash
ssh admin@your-nas-ip
```

#### 第 2 步：進入應用文件夾

```bash
cd /volume1/docker/rental_app
```

#### 第 3 步：啟動容器

```bash
docker run -d \
  --name rental_analysis_app \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /volume1/docker/rental_app:/app \
  -v /volume1/docker/rental_data:/app/data \
  -v /volume1/docker/rental_uploads:/app/upload \
  -e PYTHONUNBUFFERED=1 \
  -e DB_PATH=/app/data/rental.db \
  -w /app \
  python:3.11-slim \
  sh -c "pip install -q -r requirements.txt && python -m uvicorn main_v4:app --host 0.0.0.0 --port 8000"
```

#### 第 4 步：查看日誌

```bash
docker logs -f rental_analysis_app
```

---

## 內部網絡訪問

### 第 1 步：找到 NAS 的 IP 地址

1. 打開 NAS 控制面板
2. 進入「網絡」
3. 查看「IPv4 地址」，例如：`192.168.1.100`

### 第 2 步：在瀏覽器中訪問

在您的電腦或手機上，打開瀏覽器並訪問：

```
http://192.168.1.100:8000/index_v6.html
```

**預期結果：**
- ✅ 看到租賃分析系統的界面
- ✅ 地圖上顯示房源標記
- ✅ 統計儀表板顯示數據

### 第 3 步：測試功能

1. 在「地址」欄輸入：`中和區永和路`
2. 點擊「搜尋分析」
3. 確認地圖上有房源顯示
4. 檢查統計數據是否正確

---

## 外網訪問設置

### 第 1 步：啟用 DDNS

1. 打開 NAS 控制面板
2. 進入「外部訪問」
3. 選擇「DDNS」標籤
4. 點擊「新增」
5. 選擇服務提供商：`Synology`
6. 設置主機名，例如：`my-rental-app`
7. 記下完整域名，例如：`my-rental-app.synology.me`

### 第 2 步：配置反向代理（推薦）

1. 進入「應用程序入口」
2. 點擊「新增」
3. 設置以下參數：

| 設置項 | 值 |
|------|-----|
| 描述 | Rental Analysis App |
| 協議 | HTTPS |
| 主機名 | my-rental-app.synology.me |
| 端口 | 443 |
| 後端伺服器 | localhost |
| 後端端口 | 8000 |
| 啟用 HTTP/2 | ✅ |

### 第 3 步：外網訪問

現在可以從任何地方訪問：

```
https://my-rental-app.synology.me/index_v6.html
```

**注意：**
- 第一次訪問可能需要等待 1-2 分鐘
- 確保 NAS 已連接到網絡
- 確保 NAS 已開機

---

## 數據庫更新

### 方式 A：通過 Web 界面上傳 CSV（推薦）

1. 訪問系統：`http://192.168.1.100:8000/index_v6.html`
2. 將新的 CSV 文件放入 `/volume1/docker/rental_uploads/` 文件夾
3. 重啟容器（見下方）
4. 系統會自動導入新 CSV 文件

### 方式 B：直接上傳 CSV 文件

1. 打開 File Station
2. 進入 `/volume1/docker/rental_uploads/`
3. 上傳新的 CSV 文件
4. 重啟容器

### 重啟容器

**使用 Container Manager UI：**
1. 打開 Container Manager
2. 找到 `rental_analysis_app` 容器
3. 點擊「停止」
4. 等待 10 秒
5. 點擊「啟動」

**使用 SSH 命令：**
```bash
docker restart rental_analysis_app
```

### 驗證導入

1. 查看容器日誌
2. 確認看到「CSV 導入完成！」信息
3. 訪問系統，確認新房源已顯示

---

## 故障排除

### 問題 1：容器無法啟動

**症狀：** 容器顯示「已停止」狀態

**解決方案：**
1. 查看容器日誌
2. 檢查卷掛載路徑是否正確
3. 確保 `/volume1/docker/rental_app/` 中有 `main_v4.py` 和 `requirements.txt`
4. 重新創建容器

### 問題 2：無法訪問應用

**症狀：** 訪問 `http://192.168.1.100:8000` 時超時

**解決方案：**
1. 確認容器已啟動：`docker ps`
2. 確認端口映射正確：`docker port rental_analysis_app`
3. 檢查防火牆設置
4. 查看容器日誌：`docker logs rental_analysis_app`

### 問題 3：CSV 文件未導入

**症狀：** 系統啟動時沒有看到「CSV 導入完成」信息

**解決方案：**
1. 確認 CSV 文件在 `/volume1/docker/rental_uploads/` 中
2. 確認 CSV 文件名不含特殊字符
3. 確認 CSV 文件編碼為 UTF-8
4. 查看容器日誌查看具體錯誤

### 問題 4：外網無法訪問

**症狀：** 無法通過 DDNS 域名訪問

**解決方案：**
1. 確認 DDNS 已啟用
2. 確認 NAS 已連接到網絡
3. 等待 DDNS 同步（通常 5-10 分鐘）
4. 檢查防火牆規則
5. 檢查 ISP 是否限制了端口

### 問題 5：數據庫損壞

**症狀：** 系統無法啟動或顯示錯誤

**解決方案：**
1. 停止容器
2. 刪除數據庫文件：`rm /volume1/docker/rental_data/rental.db`
3. 重啟容器（系統會自動重新創建數據庫）
4. 重新上傳 CSV 文件

---

## 📞 支持和反饋

如遇到問題，請提供以下信息：
1. 容器日誌輸出
2. NAS 型號和系統版本
3. Container Manager 版本
4. 具體錯誤信息

---

## ✅ 測試清單

部署完成後，請按以下清單進行測試：

- [ ] 容器已啟動並運行
- [ ] 內部網絡可以訪問（http://192.168.1.100:8000）
- [ ] 地圖上顯示房源標記
- [ ] 統計儀表板顯示正確數據
- [ ] 搜尋功能正常
- [ ] 熱力圖功能正常
- [ ] CSV 文件已導入
- [ ] DDNS 域名已配置
- [ ] 外網可以訪問（https://your-domain.synology.me）
- [ ] 數據庫可以更新

---

**祝您部署順利！** 🎉
