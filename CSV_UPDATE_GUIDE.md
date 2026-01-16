# CSV 數據更新指南 - 詳細步驟

## 📋 目錄
1. [準備工作](#準備工作)
2. [更新步驟](#更新步驟)
3. [驗證更新](#驗證更新)
4. [故障排除](#故障排除)
5. [常見問題](#常見問題)

---

## 準備工作

### 第 1 步：安裝必要工具

您需要安裝 **Git** 來管理代碼和文件。

#### Windows 用戶
1. 訪問 https://git-scm.com/download/win
2. 下載並安裝（選擇默認選項即可）
3. 安裝完成後重啟電腦

#### Mac 用戶
1. 打開終端（Terminal）
2. 運行命令：`xcode-select --install`
3. 按照提示完成安裝

#### Linux 用戶
```bash
sudo apt-get install git
```

### 第 2 步：克隆倉庫到本地

這一步是將 GitHub 上的代碼下載到您的電腦上。

#### Windows 用戶
1. 打開 **文件瀏覽器**
2. 選擇一個合適的位置（例如：`C:\Users\YourName\Documents`）
3. 右鍵點擊空白處，選擇 **「Git Bash Here」**
4. 運行以下命令：
   ```bash
   git clone https://github.com/sil0410/rental-analysis-app.git
   ```
5. 等待下載完成

#### Mac/Linux 用戶
1. 打開終端
2. 進入合適的目錄：
   ```bash
   cd ~/Documents
   ```
3. 克隆倉庫：
   ```bash
   git clone https://github.com/sil0410/rental-analysis-app.git
   ```

**完成後，您會看到一個名為 `rental-application-app` 的文件夾。**

---

## 更新步驟

### 第 1 步：準備新的 CSV 文件

1. **獲取新的 CSV 文件**
   - 從 591.com 或其他來源下載新的房源數據
   - 確保 CSV 文件格式與原有文件相同

2. **檢查文件格式**
   - 打開 CSV 文件確認包含以下列：
     - 案件編號
     - 標題
     - 地址
     - 房型
     - 坪數
     - 樓層
     - 租金
     - 押金
     - 捷運站
     - 聯絡人
     - 截圖檔名
     - 頁碼
     - 座標（DMS 格式：25°0'26"N 121°30'5"E）
     - 執行日期

### 第 2 步：替換本地 CSV 文件

1. **打開文件夾**
   - 進入 `rental-analysis-app` 文件夾
   - 進入 `upload` 子文件夾

2. **備份舊文件（可選但推薦）**
   - 在 `upload` 文件夾中創建一個 `backup` 子文件夾
   - 將舊的 CSV 文件複製到 `backup` 文件夾

3. **替換 CSV 文件**
   - 刪除舊的 CSV 文件（保留 `test_properties.csv`）
   - 將新的 CSV 文件複製到 `upload` 文件夾

**文件夾結構應該看起來像這樣：**
```
rental-analysis-app/
├── upload/
│   ├── test_properties.csv
│   ├── 591_中和區_公寓_整層住家_page1.csv
│   ├── 591_中和區_公寓_整層住家_page2.csv
│   └── ... (其他 CSV 文件)
├── main_v4.py
├── index_v6.html
└── ... (其他文件)
```

### 第 3 步：提交更改到 Git

#### Windows 用戶

1. **打開 Git Bash**
   - 在 `rental-analysis-app` 文件夾中右鍵點擊
   - 選擇 **「Git Bash Here」**

2. **查看更改**
   ```bash
   git status
   ```
   您應該看到類似的輸出：
   ```
   modified:   upload/591_中和區_公寓_整層住家_page1.csv
   modified:   upload/591_中和區_公寓_整層住家_page2.csv
   ...
   ```

3. **添加所有更改**
   ```bash
   git add upload/*.csv
   ```

4. **提交更改**
   ```bash
   git commit -m "Update: New rental data from 591.com"
   ```
   
   **提示：** `"Update: New rental data from 591.com"` 是提交信息，您可以根據需要修改。

5. **推送到 GitHub**
   ```bash
   git push origin main
   ```
   
   **提示：** 如果提示輸入用戶名和密碼，使用：
   - 用戶名：`sil0410`
   - 密碼：使用您的 **GitHub Personal Access Token**（在 GitHub 設置中生成）

#### Mac/Linux 用戶

1. **打開終端**

2. **進入項目目錄**
   ```bash
   cd ~/Documents/rental-analysis-app
   ```

3. **查看更改**
   ```bash
   git status
   ```

4. **添加所有更改**
   ```bash
   git add upload/*.csv
   ```

5. **提交更改**
   ```bash
   git commit -m "Update: New rental data from 591.com"
   ```

6. **推送到 GitHub**
   ```bash
   git push origin main
   ```

**成功標誌：**
```
Counting objects: 5, done.
Delta compression using up to 4 threads.
Compressing objects: 100% (5/5), done.
Writing objects: 100% (5/5), 1.23 MiB | 1.23 MiB/s, done.
Total 5 (delta 2), reused 0 (delta 0)
To https://github.com/sil0410/rental-analysis-app.git
   abc1234..def5678  main -> main
```

### 第 4 步：在 Railway 上重新部署

1. **訪問 Railway 儀表板**
   - 打開 https://railway.app
   - 登錄您的帳號

2. **找到應用**
   - 在儀表板上找到 `rental-analysis-app` 項目

3. **重新部署**
   - 點擊「Deployments」標籤
   - 找到最新的部署
   - 點擊「Redeploy」按鈕

4. **等待部署完成**
   - 等待 5-10 分鐘
   - 查看「Deploy Logs」確認部署成功
   - 看到「✓ Deployment successful」表示成功

### 第 5 步：驗證更新

1. **訪問應用**
   ```
   https://rental-analysis-app-production.up.railway.app/index_v6.html
   ```

2. **檢查房源數量**
   - 查看統計儀表板中的「房源數」
   - 確認新增的房源已顯示

3. **測試搜尋功能**
   - 在地址欄輸入搜尋條件
   - 點擊「搜尋分析」
   - 確認結果正確

---

## 驗證更新

### 檢查清單

- [ ] 新的 CSV 文件已放入 `upload/` 文件夾
- [ ] 運行 `git status` 確認文件已修改
- [ ] 運行 `git add upload/*.csv` 添加文件
- [ ] 運行 `git commit -m "..."` 提交更改
- [ ] 運行 `git push origin main` 推送到 GitHub
- [ ] 在 Railway 上點擊「Redeploy」
- [ ] 等待部署完成（5-10 分鐘）
- [ ] 訪問應用確認房源已更新

---

## 故障排除

### 問題 1：Git 命令提示「找不到命令」

**原因：** Git 沒有安裝或沒有正確配置

**解決方案：**
1. 重新安裝 Git
2. 重啟電腦
3. 重新打開 Git Bash

### 問題 2：推送時提示「Permission denied」

**原因：** GitHub 認證失敗

**解決方案：**
1. 確認使用了正確的 Personal Access Token
2. 確認 Token 沒有過期
3. 重新生成 Token（如需要）

### 問題 3：推送後 Railway 上仍然沒有新數據

**原因：** 部署還沒有完成或構建失敗

**解決方案：**
1. 等待 5-10 分鐘
2. 查看 Railway 的「Build Logs」
3. 如果有錯誤，查看錯誤信息並修復

### 問題 4：CSV 文件太大無法上傳

**原因：** GitHub 有文件大小限制

**解決方案：**
1. 分割 CSV 文件為多個較小的文件
2. 或者使用 Git LFS（Large File Storage）
3. 聯繫技術支持

---

## 常見問題

### Q1：我需要每次都克隆倉庫嗎？

**答：** 不需要。第一次克隆後，您可以在同一個文件夾中進行多次更新。只需：
1. 進入 `rental-analysis-app` 文件夾
2. 替換 CSV 文件
3. 運行 `git add`、`git commit`、`git push` 命令

### Q2：我可以同時更新多個 CSV 文件嗎？

**答：** 可以。只需將所有新 CSV 文件放入 `upload/` 文件夾，然後運行：
```bash
git add upload/*.csv
git commit -m "Update: Multiple CSV files"
git push origin main
```

### Q3：如果我不小心刪除了重要文件怎麼辦？

**答：** 不用擔心，您可以恢復：
```bash
git checkout HEAD -- upload/filename.csv
```

### Q4：我可以回到之前的版本嗎？

**答：** 可以。查看提交歷史：
```bash
git log
```

然後恢復到特定版本：
```bash
git revert <commit-hash>
```

### Q5：我需要了解 Git 的所有知識嗎？

**答：** 不需要。您只需要記住以下命令：
- `git status` - 查看更改
- `git add upload/*.csv` - 添加文件
- `git commit -m "..."` - 提交更改
- `git push origin main` - 推送到 GitHub

---

## 📞 需要幫助？

如果遇到問題，請：

1. **查看錯誤信息**
   - 仔細閱讀命令行中的錯誤信息
   - 大多數錯誤信息都包含解決方案

2. **查看 Railway 日誌**
   - Railway 儀表板 → Deployments → Deploy Logs
   - 查看是否有構建或部署錯誤

3. **檢查 GitHub**
   - 訪問 https://github.com/sil0410/rental-analysis-app
   - 確認 CSV 文件已被上傳

4. **聯繫技術支持**
   - 提供錯誤信息和日誌
   - 描述您採取的步驟

---

## 🎯 快速參考

### 完整的更新流程（複製粘貼版本）

#### Windows（Git Bash）
```bash
# 1. 進入項目目錄
cd path/to/rental-analysis-app

# 2. 查看更改
git status

# 3. 添加 CSV 文件
git add upload/*.csv

# 4. 提交更改
git commit -m "Update: New rental data"

# 5. 推送到 GitHub
git push origin main
```

#### Mac/Linux（終端）
```bash
# 1. 進入項目目錄
cd ~/Documents/rental-analysis-app

# 2. 查看更改
git status

# 3. 添加 CSV 文件
git add upload/*.csv

# 4. 提交更改
git commit -m "Update: New rental data"

# 5. 推送到 GitHub
git push origin main
```

然後在 Railway 上點擊「Redeploy」，等待 5-10 分鐘。

---

**祝您更新順利！** 🎉
