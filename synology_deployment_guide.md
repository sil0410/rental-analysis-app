
# 租屋行情分析系統 - Synology DS420+ 部署指南

本指南將引導您如何在 Synology DS420+ NAS 上使用 Docker 成功部署並運行「租屋行情分析系統」。使用 Docker 可以將系統與您的 NAS 環境隔離，更加安全和穩定。

---

## 1. 環境準備

在開始之前，請確保您的 DS420+ 已完成以下設定：

### 1.1. 安裝 Docker

1.  **登入 DSM**：
    打開瀏覽器，輸入您的 NAS IP 位址，登入 DSM 系統。

2.  **打開套件中心**：
    在 DSM 桌面找到並打開「套件中心」。

3.  **搜尋並安裝 Docker**：
    在套件中心的搜尋框中輸入 `Docker`，找到後點擊「安裝套件」。

### 1.2. 創建共用資料夾

我們需要一個專門的資料夾來存放系統檔案和數據。

1.  **打開 File Station**：
    在 DSM 桌面找到並打開「File Station」。

2.  **創建資料夾**：
    -   在左側面板選擇一個儲存空間（例如 `volume1`）。
    -   點擊「新增」>「新增共用資料夾」。
    -   **名稱**：輸入 `rental_analysis`。
    -   其他設定保持默認，點擊「下一步」直到完成。

3.  **創建子資料夾**：
    -   在剛剛創建的 `rental_analysis` 資料夾中，創建一個名為 `upload` 的子資料夾。
    -   將您所有的 CSV 數據檔案上傳到這個 `upload` 資料夾中。

## 2. 系統部署

我們將使用 Docker Compose 來簡化部署過程。

### 2.1. 上傳系統檔案

1.  **下載系統檔案**：
    我將為您打包所有系統檔案，包括 `Dockerfile` 和 `docker-compose.yml`。

2.  **上傳到 NAS**：
    將下載並解壓縮後的所有檔案（除了 `upload` 資料夾和裡面的 CSV）上傳到 `rental_analysis` 共用資料夾中。

### 2.2. 使用 Docker Compose 啟動系統

Synology 的 Docker 介面不直接支持 Docker Compose，但我們可以使用 SSH 來輕鬆完成。

1.  **啟用 SSH 服務**：
    -   前往 DSM 的「控制台」>「終端機 & SNMP」。
    -   勾選「啟用 SSH 服務」，端口保持默認的 `22`。

2.  **使用 SSH 連接到 NAS**：
    -   在您的 Windows 電腦上，打開命令提示字元或 PowerShell。
    -   輸入以下指令（將 `YOUR_NAS_IP` 和 `YOUR_USERNAME` 替換為您的實際信息）：
        ```bash
        ssh YOUR_USERNAME@YOUR_NAS_IP
        ```
    -   輸入您的 DSM 密碼。

3.  **切換到部署目錄**：
    -   輸入以下指令（路徑可能因您的儲存空間而異）：
        ```bash
        cd /volume1/rental_analysis
        ```

4.  **啟動 Docker 容器**：
    -   輸入以下指令：
        ```bash
        sudo docker-compose up -d
        ```
    -   `sudo` 是為了獲取管理員權限。
    -   `docker-compose up` 會根據 `docker-compose.yml` 的設定來建立並啟動容器。
    -   `-d` 表示在背景運行。

## 3. 訪問系統

-   打開您的網頁瀏覽器，在網址列輸入（將 `YOUR_NAS_IP` 替換為您的 NAS IP 位址）：
    ```
    http://YOUR_NAS_IP:8000/index_v6.html
    ```
-   您現在應該能看到系統介面了。

---

## 6. 故障排除

-   ****：
    -   這個錯誤表示  指令找不到  檔案。
    -   **請確認**：您是否已經使用  切換到正確的目錄。
    -   **請確認**： 檔案是否已經成功上傳到  資料夾中，並且檔名完全正確（沒有拼錯）。

-   **SSH 連線被拒絕**：
    -   請確認您已在 DSM 的「控制台」>「終端機 & SNMP」中啟用 SSH 服務。
    -   請確認您使用的 IP 位址和使用者名稱正確無誤。

---
