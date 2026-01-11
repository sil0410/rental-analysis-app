# 租屋行情分析系統 - 部署指南

歡迎使用「租屋行情分析系統」！本文件將引導您完成系統的部署過程。

---

## 📋 部署文件清單

本部署包包含以下檔案：

| 檔案名稱 | 說明 |
|---------|------|
| `windows_deployment_guide.md` | Windows 10/11 本地部署詳細指南 |
| `synology_deployment_guide.md` | Synology DS420+ NAS 部署詳細指南 |
| `network_access_guide.md` | 本地網絡和外部訪問配置指南 |
| `main_v4.py` | 後端 API 主程式 |
| `index_v6.html` | 前端網頁介面 |
| `requirements.txt` | Python 依賴套件清單 |
| `Dockerfile` | Docker 容器配置（用於 NAS 部署） |
| `docker-compose.yml` | Docker Compose 配置（用於 NAS 部署） |

---

## 🚀 快速開始

### 選項 1：Windows 10/11 本地部署

如果您想在 Windows 電腦上直接運行系統，請按照以下步驟：

1.  閱讀 `windows_deployment_guide.md`
2.  安裝 Python 3.8 或更高版本
3.  安裝依賴套件：`pip install -r requirements.txt`
4.  啟動後端：`uvicorn main_v4:app --reload`
5.  在瀏覽器中訪問：`http://127.0.0.1:8000/index_v6.html`

### 選項 2：Synology DS420+ NAS 部署

如果您想在 NAS 上運行系統，請按照以下步驟：

1.  閱讀 `synology_deployment_guide.md`
2.  安裝 Docker
3.  上傳所有檔案到 NAS
4.  使用 Docker Compose 啟動系統
5.  在瀏覽器中訪問：`http://YOUR_NAS_IP:8000/index_v6.html`

---

## 🌐 網絡訪問

### 本地網絡訪問

在您的家庭或辦公室網絡中，您可以直接訪問系統。詳見 `network_access_guide.md`。

### 外部訪問

要從外部訪問您的系統，請按照 `network_access_guide.md` 中的「外部訪問規劃」部分進行設定。

---

## 📊 系統功能

部署完成後，您將能夠：

-   **搜尋租屋市場**：指定地址和搜尋範圍，查看該區域的房源分佈。
-   **分析房源趨勢**：查看新上榜、已下架房源的數量和變化趨勢。
-   **查看熱力圖**：直觀地看到房源密度和租金分佈。
-   **統計分析**：獲得平均租金、平均坪數等市場統計數據。

---

## 🆘 故障排除

如果您在部署過程中遇到問題，請參考相應部署指南中的「故障排除」部分。

---

## 📞 技術支援

如果您有任何問題或建議，歡迎聯繫系統開發者。

---

**祝您使用愉快！** 🏠📈
