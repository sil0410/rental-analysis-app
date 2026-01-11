
# 租屋行情分析系統 - Windows 本地部署指南

本指南將引導您如何在 Windows 10 或 Windows 11 電腦上成功部署並運行「租屋行情分析系統」。

---

## 1. 環境準備

在開始之前，請確保您的電腦已安裝以下軟體：

### 1.1. 安裝 Python

本系統需要 Python 3.11 (穩定版)。如果您尚未安裝，請按照以下步驟操作：

1.  **下載 Python**：
    前往 [Python 官方網站](https://www.python.org/downloads/windows/)，下載最新的 Python 3.x 版本安裝程式。

2.  **執行安裝程式**：
    -   打開下載的 `.exe` 檔案。
    -   **重要**：在安裝介面的第一頁，務必勾選 **`Add Python to PATH`** 選項。這一步非常關鍵，可以讓您在命令提示字元中輕鬆執行 Python。
    -   點擊 `Install Now` 進行標準安裝。

3.  **驗證安裝**：
    -   按下 `Win + R`，輸入 `cmd` 並按 Enter，打開命令提示字元。
    -   輸入以下指令並按 Enter：
        ```bash
        python --version
        ```
    -   如果看到類似 `Python 3.11.4` 的版本號，表示安裝成功。

### 1.2. 安裝程式碼編輯器 (推薦)

一個好的程式碼編輯器能讓您更輕鬆地查看和修改設定。推薦使用 [Visual Studio Code](https://code.visualstudio.com/)，它免費且功能強大。

## 2. 系統部署

接下來，我們將下載系統檔案並安裝所需的依賴套件。

### 2.1. 下載系統檔案

1.  **創建資料夾**：
    在您喜歡的位置（例如 `D:\` 磁碟機）創建一個名為 `rental_analysis` 的資料夾。

2.  **下載並解壓縮**：
    我將為您打包所有系統檔案。下載後，將所有檔案解壓縮到剛剛創建的 `D:\rental_analysis` 資料夾中。

### 2.2. 安裝依賴套件

1.  **打開命令提示字元**：
    -   在 `rental_analysis` 資料夾的空白處，按住 `Shift` 鍵並點擊滑鼠右鍵。
    -   在選單中選擇 `在此處開啟 PowerShell 視窗` 或 `在此處開啟命令提示字元`。

2.  **安裝依賴**：
    在打開的視窗中，輸入以下指令並按 Enter：
    ```bash
    pip install -r requirements.txt
    ```
    這個指令會自動安裝所有必要的 Python 套件。

## 3. 數據配置

系統需要您的 CSV 數據才能運作。

1.  **創建 `upload` 資料夾**：
    在 `rental_analysis` 資料夾中，創建一個名為 `upload` 的子資料夾。

2.  **放置 CSV 檔案**：
    將您所有的 CSV 數據檔案複製到 `D:\rental_analysis\upload` 資料夾中。

## 4. 啟動系統

一切準備就緒後，就可以啟動系統了。

1.  **啟動後端服務**：
    在剛剛的命令提示字元視窗中，輸入以下指令：
    ```bash
    python -m uvicorn main_v4:app --reload
    ```
    -   `main_v4` 是後端主程式的檔名。
    -   `app` 是程式中的 FastAPI 實例。
    -   `--reload` 會在您修改程式碼後自動重啟服務，非常方便。

2.  **訪問系統**：
    -   後端啟動後，您會看到類似 `Uvicorn running on http://127.0.0.1:8000` 的訊息。
    -   打開您的網頁瀏覽器（推薦 Chrome 或 Edge），在網址列輸入：
        ```
        http://127.0.0.1:8000/index_v6.html
        ```
    -   您現在應該能看到熟悉的租屋行情分析地圖介面了。

## 5. 故障排除

-   **`python` 或 `pip` 指令找不到**：
    這表示 Python 沒有被正確加入到系統的 `PATH` 環境變數中。請重新安裝 Python，並確保勾選 `Add Python to PATH`。

-   **無法訪問 `127.0.0.1:8000`**：
    請檢查防火牆設定，確保允許 `uvicorn` 或 `python` 程式的網絡訪問。

---
