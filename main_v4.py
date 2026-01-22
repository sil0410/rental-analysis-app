"""
租屋行情分析系統 - 版本控制 API v7.5 (Database Architecture)
架構變更：ETL 模式
1. Source: Google Drive (CSV)
2. Storage: SQLite (Properties Table)
3. Query: Direct SQL Select
"""

import sqlite3
import json
import os
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import math
import pandas as pd
from io import BytesIO

# 初始化 FastAPI
app = FastAPI(title="租屋行情分析 API v7.5 (DB版)")

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 數據庫路徑
DB_PATH = os.path.join(os.path.dirname(__file__), "rental.db")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")  # 建議從環境變數讀取

# ============ Google Drive 配置 ============
GOOGLE_DRIVE_FOLDER_NAME = "租屋數據"
drive_service = None
drive_folder_id = None
drive_available = False

def init_google_drive():
    """初始化 Google Drive API"""
    global drive_service, drive_folder_id, drive_available
    
    try:
        key_json_str = os.getenv('GOOGLE_DRIVE_KEY_JSON')
        if not key_json_str:
            print("ℹ️ Google Drive 未配置 (使用本地模式)")
            return False
        
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            print("⚠️ 缺少 Google Drive 套件: pip install google-auth google-api-python-client")
            return False
        
        try:
            key_dict = json.loads(key_json_str)
        except json.JSONDecodeError:
            print("⚠️ Google Drive Key JSON 解析失敗")
            return False
        
        credentials = Credentials.from_service_account_info(
            key_dict, scopes=['https://www.googleapis.com/auth/drive']
        )
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        results = drive_service.files().list(
            q=f"name='{GOOGLE_DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive', fields='files(id, name)', pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            drive_folder_id = files[0]['id']
            drive_available = True
            print(f"✓ Google Drive 連接成功 (ID: {drive_folder_id})")
            return True
        else:
            print(f"⚠️ 找不到資料夾: {GOOGLE_DRIVE_FOLDER_NAME}")
            return False
            
    except Exception as e:
        print(f"⚠️ Google Drive 初始化異常: {e}")
        return False

# ============ 數據庫初始化 (Schema) ============

def init_database():
    """初始化數據庫架構 - 新增 properties 表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 版本控制表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            week_id TEXT PRIMARY KEY,
            upload_date TEXT NOT NULL,
            record_count INTEGER DEFAULT 0
        )
    """)
    
    # 2. 檔案同步記錄表 (取代舊的 csv_index)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            file_id TEXT PRIMARY KEY,
            filename TEXT,
            city TEXT,
            district TEXT,
            week_id TEXT,
            status TEXT, -- 'synced', 'failed'
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. 核心資料表 (存放所有房源數據)
    # 這就是你的「大冰箱」，所有 CSV 的資料都會被清洗後放入這裡
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT,          -- 案件編號
            title TEXT,
            address TEXT,
            city TEXT,
            district TEXT,
            rent INTEGER,
            area REAL,
            floor TEXT,
            room_type TEXT,            -- 原始房型 (例如: 2房1廳)
            property_category TEXT,    -- 歸類 (套房/住家)
            building_type TEXT,        -- 建物類型 (apartment/building)
            latitude REAL,
            longitude REAL,
            week_id TEXT,              -- 時間維度
            file_id TEXT,              -- 來源檔案
            
            -- 複合唯一鍵：確保同一週、同一個案件編號只會存一次
            UNIQUE(property_id, week_id)
        )
    """)
    
    # 建立索引以加速查詢
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_loc ON properties (city, district)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rent ON properties (rent)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_week ON properties (week_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_btype ON properties (building_type)")
    
    conn.commit()
    conn.close()
    print("✓ 數據庫初始化完成 (Tables: versions, sync_log, properties)")

# ============ 工具函數 ============

def parse_dms_coordinate(coord_str: str):
    """解析座標 (支援度分秒與十進位)"""
    if not coord_str or pd.isna(coord_str):
        return 0, 0
    
    coord_str = str(coord_str).strip()
    
    # 1. 嘗試解析度分秒 (DMS)
    dms_pattern = r"(\d+)°(\d+)'(\d+(?:\.\d+)?)\"([NSEW])"
    matches = re.findall(dms_pattern, coord_str)
    if len(matches) >= 2:
        try:
            lat_match = next((m for m in matches if m[3] in ['N', 'S']), None)
            lng_match = next((m for m in matches if m[3] in ['E', 'W']), None)
            
            if lat_match and lng_match:
                lat = float(lat_match[0]) + float(lat_match[1])/60 + float(lat_match[2])/3600
                if lat_match[3] == 'S': lat = -lat
                
                lng = float(lng_match[0]) + float(lng_match[1])/60 + float(lng_match[2])/3600
                if lng_match[3] == 'W': lng = -lng
                return lat, lng
        except:
            pass

    # 2. 嘗試解析直接的浮點數 (Decimal)
    try:
        # 有些資料可能是 "25.123, 121.456" 或單純浮點數欄位
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", coord_str)
        if len(parts) >= 2:
            # 台灣大約在 Lat 22-25, Lng 120-122，簡單判斷
            v1, v2 = float(parts[0]), float(parts[1])
            if 20 <= v1 <= 26 and 118 <= v2 <= 124:
                return v1, v2
            elif 20 <= v2 <= 26 and 118 <= v1 <= 124:
                return v2, v1
    except:
        pass
        
    return 0, 0

def haversine_distance(lat1, lon1, lat2, lon2):
    """計算兩點距離 (公尺)"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def parse_filename_info(filename: str):
    """從檔名解析 metadata"""
    info = {
        'week_id': '', 'city': '', 'district': '', 
        'building_type': 'unknown', 'property_category': 'unknown'
    }
    
    # 解析週次
    week_match = re.search(r'_(\d{4})(?:_merged)?(?:\.csv)?$', filename)
    if week_match:
        info['week_id'] = week_match.group(1)
    
    # 解析類型
    if '電梯' in filename: info['building_type'] = 'building'
    elif '公寓' in filename: info['building_type'] = 'apartment'
    
    if '套房' in filename: info['property_category'] = '套房'
    elif '住家' in filename: info['property_category'] = '住家'
    
    # 解析地點
    if filename.startswith('新北市'): info['city'] = '新北市'
    elif filename.startswith('臺北市') or filename.startswith('台北市'): info['city'] = '台北市'
    elif filename.startswith('基隆市'): info['city'] = '基隆市'
    elif filename.startswith('桃園市'): info['city'] = '桃園市'
    
    # 簡易區域判斷
    districts = ['板橋', '三重', '中和', '永和', '新莊', '新店', '土城', '蘆洲', '樹林', '汐止', '林口', '淡水', '大安', '信義', '中山', '松山', '內湖']
    for d in districts:
        if d in filename:
            info['district'] = d + '區' if not d.endswith('區') else d
            break
            
    return info

# ============ ETL 核心邏輯 (Sync Data) ============

async def process_sync_task(background_tasks: BackgroundTasks):
    """背景執行：同步 Drive 資料到 DB"""
    if not drive_available or not drive_service:
        print("⚠️ 無法同步：Google Drive 未連接")
        return

    print("🔄 開始執行資料同步任務...")
    
    # 1. 獲取 Drive 上的所有 CSV
    try:
        results = drive_service.files().list(
            q=f"'{drive_folder_id}' in parents and name contains '.csv' and trashed=false",
            fields="files(id, name)", pageSize=1000
        ).execute()
        drive_files = results.get('files', [])
    except Exception as e:
        print(f"⚠️ 讀取 Drive 列表失敗: {e}")
        return

    # 2. 檢查哪些已經同步過
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM sync_log")
    synced_ids = {row[0] for row in cursor.fetchall()}
    
    new_files = [f for f in drive_files if f['id'] not in synced_ids]
    print(f"📊 掃描結果：共 {len(drive_files)} 個檔案，需同步 {len(new_files)} 個新檔案")
    
    # 3. 逐一下載並匯入
    from googleapiclient.http import MediaIoBaseDownload
    
    count_success = 0
    for file_meta in new_files:
        file_id = file_meta['id']
        filename = file_meta['name']
        print(f"  ⬇️ 下載並處理: {filename} ...")
        
        try:
            # 解析檔名資訊
            meta = parse_filename_info(filename)
            if not meta['week_id']:
                # 如果檔名沒有週次，跳過或使用當前週次 (這裡選擇跳過以保證數據品質)
                print(f"     ⚠️ 跳過 (無法解析週次): {filename}")
                continue

            # 下載內容
            request = drive_service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            
            # Pandas 讀取與清理
            df = pd.read_csv(fh, encoding='utf-8-sig')
            
            # 數據轉換 (Transform)
            clean_rows = []
            for _, row in df.iterrows():
                try:
                    # 必填欄位檢查
                    pid = str(row.get('案件編號', ''))
                    if not pid or pid == 'nan': continue
                    
                    rent = row.get('租金', 0)
                    if pd.isna(rent): rent = 0
                    else: rent = int(str(rent).replace(',', '').split('.')[0])
                    
                    # 座標處理
                    lat, lng = 0.0, 0.0
                    if '緯度' in df.columns and '經度' in df.columns and not pd.isna(row['緯度']):
                        lat, lng = float(row['緯度']), float(row['經度'])
                    elif '座標' in df.columns:
                        lat, lng = parse_dms_coordinate(row.get('座標', ''))
                    
                    # 地址補全
                    addr = str(row.get('地址', ''))
                    if meta['city'] and not addr.startswith(meta['city']):
                        addr = meta['city'] + addr
                    
                    clean_rows.append((
                        pid,
                        str(row.get('標題', '')),
                        addr,
                        meta['city'],
                        meta['district'] or row.get('區域', ''), # 如果檔名沒區域，看CSV內有無
                        rent,
                        float(row.get('坪數', 0) or 0),
                        str(row.get('樓層', '')),
                        str(row.get('房型', '')),
                        meta['property_category'],
                        meta['building_type'],
                        lat,
                        lng,
                        meta['week_id'],
                        file_id
                    ))
                except Exception as e:
                    continue # 單行失敗不影響整檔
            
            # 批量寫入 (Load)
            if clean_rows:
                cursor.executemany("""
                    INSERT OR IGNORE INTO properties 
                    (property_id, title, address, city, district, rent, area, floor, room_type, 
                     property_category, building_type, latitude, longitude, week_id, file_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, clean_rows)
                
                # 更新版本表
                cursor.execute("""
                    INSERT OR IGNORE INTO versions (week_id, upload_date) VALUES (?, ?)
                """, (meta['week_id'], datetime.now().strftime("%Y-%m-%d")))
            
            # 記錄同步成功
            cursor.execute("""
                INSERT INTO sync_log (file_id, filename, city, district, week_id, status)
                VALUES (?, ?, ?, ?, ?, 'synced')
            """, (file_id, filename, meta['city'], meta['district'], meta['week_id']))
            
            conn.commit()
            count_success += 1
            print(f"     ✓ 成功匯入 {len(clean_rows)} 筆資料")
            
        except Exception as e:
            print(f"     ❌ 處理失敗: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    print(f"🏁 同步完成：成功處理 {count_success} 個檔案")

# ============ API Endpoints ============

@app.on_event("startup")
async def startup_event():
    init_database()
    init_google_drive()

@app.get("/api/versions")
async def get_versions():
    """獲取可用的週次"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
    versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "versions": versions}

@app.get("/api/available-filters")
async def get_filters():
    """從 properties 表快速獲取篩選條件"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT city, district FROM properties WHERE district IS NOT NULL ORDER BY city, district")
    districts = [{"city": r[0], "district": r[1]} for r in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT week_id FROM versions ORDER BY week_id DESC")
    week_ids = [r[0] for r in cursor.fetchall()]
    
    conn.close()
    return {
        "status": "success",
        "filters": {
            "districts": districts,
            "week_ids": week_ids,
            "building_types": ["apartment", "building"],
            "property_categories": ["套房", "住家"]
        },
        "drive_connected": drive_available
    }

class AnalysisRequest(BaseModel):
    pass # GET 請求不需要 body definition, 但為了結構化先保留

@app.get("/api/analysis_v4")
async def analysis_v4(
    address: str,
    city: Optional[str] = None,
    district: Optional[str] = None,
    distance_min: int = 0,
    distance_max: int = 5000,
    building_type: Optional[str] = None,
    property_category: Optional[str] = None,
    room_type: Optional[str] = None,
    week_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None
):
    """
    極速查詢 API
    直接使用 SQL 篩選，不再讀取 CSV
    """
    # 1. 處理參數
    if lat is None or lng is None:
        # 預設座標 (新北市政府)
        q_lat, q_lng = 25.0117, 121.4651
    else:
        q_lat, q_lng = lat, lng

    # 如果沒有指定週次，抓最新的
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # 讓結果可以像字典一樣存取
    cursor = conn.cursor()

    if not week_id:
        cursor.execute("SELECT MAX(week_id) FROM versions")
        week_id = cursor.fetchone()[0]
        if not week_id:
            return {"status": "error", "message": "資料庫為空，請先執行同步"}

    # 2. 建構 SQL 查詢
    # 策略：先用 SQL 篩選出該區域的所有房源，再用 Python 算精確距離 (因為 SQLite 算距離比較麻煩)
    # 這比載入整個 CSV 快得多，因為我們已經限縮在特定 district 和 week
    
    sql = """
        SELECT * FROM properties 
        WHERE week_id = ? 
    """
    params = [week_id]

    if district:
        sql += " AND district = ?"
        params.append(district)
    
    if building_type and building_type != '全部':
        bt_val = 'apartment' if building_type == '公寓' else 'building' if building_type == '電梯大樓' else building_type
        sql += " AND building_type = ?"
        params.append(bt_val)

    if property_category and property_category != '全部':
        sql += " AND property_category = ?"
        params.append(property_category)

    # 執行查詢
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    
    # 3. 距離過濾與統計
    filtered_props = []
    
    for row in rows:
        p_lat, p_lng = row['latitude'], row['longitude']
        
        # 忽略沒有座標的資料
        if not p_lat or not p_lng:
            continue
            
        dist = haversine_distance(q_lat, q_lng, p_lat, p_lng)
        
        if distance_min <= dist <= distance_max:
            # 房型篩選 (因為房型文字很雜，用 Python 篩選比較彈性)
            r_type = row['room_type'] or ''
            if room_type:
                if room_type == '套房' and ('套' not in r_type and row['property_category'] != '套房'): continue
                if room_type == '2房' and '2' not in r_type and '兩' not in r_type: continue
                if room_type == '3房' and '3' not in r_type and '三' not in r_type: continue
            
            # 轉換為前端需要的格式
            prop_dict = dict(row)
            prop_dict['distance'] = dist
            prop_dict['rent_monthly'] = row['rent'] # 兼容舊前端欄位名
            filtered_props.append(prop_dict)

    conn.close()

    # 4. 統計數據
    if filtered_props:
        rents = [p['rent'] for p in filtered_props]
        avg_rent = sum(rents) / len(rents)
        min_rent = min(rents)
        max_rent = max(rents)
        areas = [p['area'] for p in filtered_props if p['area'] > 0]
        avg_area = sum(areas) / len(areas) if areas else 0
    else:
        avg_rent = min_rent = max_rent = avg_area = 0

    return {
        "status": "success",
        "query": {
            "district": district,
            "week_id": week_id,
            "count": len(filtered_props)
        },
        "summary": {
            "avg_rent_all": round(avg_rent),
            "min_rent": min_rent,
            "max_rent": max_rent,
            "avg_area": round(avg_area, 1),
            "total_properties": len(filtered_props)
        },
        "properties": filtered_props,
        "source": "database (ETL)"
    }

class AdminAction(BaseModel):
    password: str

@app.post("/api/admin/sync-data")
async def trigger_sync(action: AdminAction, background_tasks: BackgroundTasks):
    """
    觸發數據同步任務 (非同步背景執行)
    將 Drive 資料搬運到 SQLite
    """
    if action.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="密碼錯誤")
    
    if not drive_available:
        raise HTTPException(status_code=400, detail="Google Drive 未連接")

    # 啟動背景任務，立即回傳回應，避免前端超時
    background_tasks.add_task(process_sync_task, background_tasks)
    
    return {"status": "success", "message": "同步任務已在背景啟動，請稍後查看資料庫狀態"}

@app.post("/api/admin/reset-all")
async def reset_all(action: AdminAction):
    """
    危險：清空所有資料庫內容
    """
    if action.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="密碼錯誤")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM properties")
    cursor.execute("DELETE FROM sync_log")
    cursor.execute("DELETE FROM versions")
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "資料庫已完全清空"}

@app.get("/api/admin/status")
async def admin_status():
    """查看同步狀態"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM properties")
    total_props = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sync_log WHERE status='synced'")
    synced_files = cursor.fetchone()[0]
    
    cursor.execute("SELECT filename, status, synced_at FROM sync_log ORDER BY synced_at DESC LIMIT 5")
    recent_logs = [{"file": r[0], "status": r[1], "time": r[2]} for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "drive_connected": drive_available,
        "database": {
            "total_properties": total_props,
            "synced_files_count": synced_files,
            "recent_activity": recent_logs
        }
    }

# 靜態文件
static_dir = os.path.dirname(__file__)
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")