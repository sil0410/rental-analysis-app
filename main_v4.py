"""
租屋行情分析系統 - 版本控制 API v7.0
支持四象限分類（建物類型 x 房型大類）按需載入 CSV
支持 Google Drive 分層資料夾管理
優化效能：只載入指定篩選條件的數據
"""

import sqlite3
import json
import os
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import math
import pandas as pd
from io import BytesIO

# 初始化 FastAPI
app = FastAPI(title="租屋行情分析 API v7.0")

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

# Upload 資料夾路徑
UPLOAD_DIR = None

# ============ Google Drive 配置 ============
GOOGLE_DRIVE_FOLDER_NAME = "租屋數據"
drive_service = None
drive_folder_id = None
drive_available = False

def init_google_drive():
    """初始化 Google Drive API（可選功能）"""
    global drive_service, drive_folder_id, drive_available
    
    try:
        # 從環境變數讀取 Google Drive 金鑰
        key_json_str = os.getenv('GOOGLE_DRIVE_KEY_JSON')
        
        if not key_json_str:
            print("ℹ️ Google Drive 未配置（環境變數 GOOGLE_DRIVE_KEY_JSON 未設定）")
            print("   系統將使用本地 upload 資料夾")
            return False
        
        # 延遲導入 Google Drive 相關模組
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            print("⚠️ Google Drive API 模組未安裝")
            print("   請執行: pip install google-auth google-api-python-client")
            return False
        
        # 解析 JSON 金鑰
        try:
            key_dict = json.loads(key_json_str)
        except json.JSONDecodeError as e:
            print(f"⚠️ 無法解析 Google Drive 金鑰 JSON：{e}")
            return False
        
        # 建立認證
        credentials = Credentials.from_service_account_info(
            key_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # 查找「租屋數據」資料夾
        results = drive_service.files().list(
            q=f"name='{GOOGLE_DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            drive_folder_id = files[0]['id']
            drive_available = True
            print(f"✓ Google Drive 連接成功")
            print(f"  - 資料夾: {GOOGLE_DRIVE_FOLDER_NAME}")
            print(f"  - ID: {drive_folder_id}")
            return True
        else:
            print(f"⚠️ 找不到 Google Drive 中的「{GOOGLE_DRIVE_FOLDER_NAME}」資料夾")
            return False
            
    except Exception as e:
        print(f"⚠️ Google Drive 初始化失敗：{e}")
        import traceback
        traceback.print_exc()
        return False

def get_csv_from_drive(city: str, district: str, building_type: str, property_category: str, week_id: str) -> Optional[pd.DataFrame]:
    """從 Google Drive 讀取指定的 CSV 文件"""
    if not drive_available or not drive_service or not drive_folder_id:
        return None
    
    try:
        from googleapiclient.http import MediaIoBaseDownload
        
        # 構建文件名
        filename = f"{building_type}_{property_category}_{week_id}.csv"
        
        # 查找城市資料夾
        city_results = drive_service.files().list(
            q=f"name='{city}' and mimeType='application/vnd.google-apps.folder' and '{drive_folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id)',
            pageSize=1
        ).execute()
        
        city_files = city_results.get('files', [])
        if not city_files:
            return None
        
        city_folder_id = city_files[0]['id']
        
        # 查找區域資料夾
        district_results = drive_service.files().list(
            q=f"name='{district}' and mimeType='application/vnd.google-apps.folder' and '{city_folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id)',
            pageSize=1
        ).execute()
        
        district_files = district_results.get('files', [])
        if not district_files:
            return None
        
        district_folder_id = district_files[0]['id']
        
        # 查找 CSV 文件
        csv_results = drive_service.files().list(
            q=f"name='{filename}' and '{district_folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id)',
            pageSize=1
        ).execute()
        
        csv_files = csv_results.get('files', [])
        if not csv_files:
            return None
        
        csv_file_id = csv_files[0]['id']
        
        # 下載 CSV 文件
        request = drive_service.files().get_media(fileId=csv_file_id)
        file_content = BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_content.seek(0)
        df = pd.read_csv(file_content, encoding='utf-8-sig')
        
        print(f"  ✓ 從 Google Drive 載入: {city}/{district}/{filename}")
        return df
        
    except Exception as e:
        print(f"  ⚠️ 從 Google Drive 讀取 CSV 失敗：{e}")
        return None

def list_google_drive_files(folder_id: str, path: str = "") -> list:
    """遞迴列出 Google Drive 資料夾中的所有 CSV 檔案"""
    if not drive_available or not drive_service:
        return []
    
    files_found = []
    
    try:
        # 列出資料夾中的所有項目
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id, name, mimeType)',
            pageSize=1000
        ).execute()
        
        items = results.get('files', [])
        
        for item in items:
            item_name = item['name']
            item_id = item['id']
            item_type = item['mimeType']
            current_path = f"{path}/{item_name}" if path else item_name
            
            if item_type == 'application/vnd.google-apps.folder':
                # 遞迴進入子資料夾
                sub_files = list_google_drive_files(item_id, current_path)
                files_found.extend(sub_files)
            elif item_name.endswith('.csv'):
                # 找到 CSV 檔案
                files_found.append({
                    'id': item_id,
                    'name': item_name,
                    'path': current_path
                })
        
        return files_found
        
    except Exception as e:
        print(f"⚠️ 列出 Google Drive 資料夾失敗 ({path}): {e}")
        return []

# ============ 本地文件系統 ============

def get_upload_dir():
    global UPLOAD_DIR
    if UPLOAD_DIR:
        return UPLOAD_DIR
    
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "upload"),
        "/app/upload",
        "./upload",
        os.path.join(os.getcwd(), "upload")
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            UPLOAD_DIR = path
            return UPLOAD_DIR
    
    UPLOAD_DIR = possible_paths[0]
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    return UPLOAD_DIR

# ============ 應用啟動事件 ============

@app.on_event("startup")
async def startup_event():
    """應用啟動時初始化數據庫並掃描可用的 CSV 文件"""
    try:
        init_database()
        init_google_drive()  # 嘗試初始化 Google Drive（可選）
        scan_available_csv_files()
    except Exception as e:
        print(f"⚠️ 啟動事件錯誤：{e}")
        import traceback
        traceback.print_exc()

# ============ 數據庫初始化 ============

def init_database():
    """初始化數據庫"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 版本表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id TEXT UNIQUE NOT NULL,
            upload_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # CSV 文件索引表（記錄可用的 CSV 文件）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS csv_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            city TEXT,
            district TEXT,
            building_type TEXT,
            property_category TEXT,
            week_id TEXT,
            record_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'local',
            file_id TEXT,
            last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 嘗試新增 file_id 欄位（如果表已存在但沒有此欄位）
    try:
        cursor.execute("ALTER TABLE csv_index ADD COLUMN file_id TEXT")
    except:
        pass  # 欄位已存在
    
    conn.commit()
    conn.close()

# ============ 工具函數 ============

def get_week_id(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    year = date.year % 100
    week = date.isocalendar()[1]
    return f"{year:02d}{week:02d}"

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def calculate_weeks_since_published(first_published_date: str) -> int:
    if not first_published_date:
        return 0
    try:
        first_date = datetime.strptime(first_published_date, "%Y-%m-%d")
        now = datetime.now()
        delta = now - first_date
        weeks = delta.days // 7
        return max(0, weeks)
    except:
        return 0

def parse_dms_coordinate(coord_str: str):
    """解析度分秒格式的座標字串"""
    if not coord_str or coord_str == 'nan':
        return 0, 0
    
    try:
        coord_str = str(coord_str).strip()
        pattern = r"(\d+)°(\d+)'(\d+(?:\.\d+)?)\"([NSEW])"
        matches = re.findall(pattern, coord_str)
        
        if len(matches) >= 2:
            lat_match = None
            lng_match = None
            
            for match in matches:
                deg, min_, sec, direction = match
                if direction in ['N', 'S']:
                    lat_match = match
                elif direction in ['E', 'W']:
                    lng_match = match
            
            if lat_match and lng_match:
                lat_deg, lat_min, lat_sec, lat_dir = lat_match
                lat = float(lat_deg) + float(lat_min)/60 + float(lat_sec)/3600
                if lat_dir == 'S':
                    lat = -lat
                
                lng_deg, lng_min, lng_sec, lng_dir = lng_match
                lng = float(lng_deg) + float(lng_min)/60 + float(lng_sec)/3600
                if lng_dir == 'W':
                    lng = -lng
                
                return lat, lng
    except Exception as e:
        pass
    
    return 0, 0

def parse_csv_filename(filename: str) -> dict:
    """解析 CSV 文件名，提取相關信息"""
    result = {
        'city': '',
        'district': '',
        'building_type': '',
        'property_category': '',
        'week_id': ''
    }
    
    name = filename.replace('.csv', '')
    
    week_match = re.search(r'_(\d{4})(?:_merged)?$', name)
    if week_match:
        result['week_id'] = week_match.group(1)
    
    if '電梯大樓' in filename or '電梯' in filename:
        result['building_type'] = 'building'
    elif '公寓' in filename:
        result['building_type'] = 'apartment'
    
    if '套房' in filename or '獨立套房' in filename:
        result['property_category'] = '套房'
    elif '住家' in filename or '整層住家' in filename:
        result['property_category'] = '住家'
    
    districts = [
        '板橋區', '三重區', '中和區', '永和區', '新莊區', '新店區', '土城區',
        '蘆洲區', '樹林區', '汐止區', '鶯歌區', '三峽區', '淡水區', '瑞芳區',
        '五股區', '泰山區', '林口區', '深坑區', '石碇區', '坪林區', '三芝區',
        '石門區', '八里區', '平溪區', '雙溪區', '貢寮區', '金山區', '萬里區',
        '烏來區', '大安區', '信義區', '中山區', '松山區', '南港區', '內湖區'
    ]
    
    for district in districts:
        if district in filename:
            result['district'] = district
            result['city'] = '新北市'
            break
    
    if filename.startswith('新北市'):
        result['city'] = '新北市'
    elif filename.startswith('臺北市') or filename.startswith('台北市'):
        result['city'] = '臺北市'
    elif filename.startswith('基隆市'):
        result['city'] = '基隆市'
    elif filename.startswith('桃園市'):
        result['city'] = '桃園市'
    
    return result

def scan_available_csv_files():
    """掃描 upload 資料夾和 Google Drive 中的 CSV 文件並建立索引"""
    upload_dir = get_upload_dir()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 清空舊索引
    cursor.execute("DELETE FROM csv_index")
    
    week_ids = set()
    total_files = 0
    
    # === 掃描本地 upload 資料夾 ===
    if os.path.exists(upload_dir):
        csv_files = [f for f in os.listdir(upload_dir) if f.endswith('.csv')]
        print(f"📁 本地掃描到 {len(csv_files)} 個 CSV 檔案")
        
        for csv_filename in csv_files:
            try:
                info = parse_csv_filename(csv_filename)
                
                csv_path = os.path.join(upload_dir, csv_filename)
                try:
                    record_count = sum(1 for _ in open(csv_path, encoding='utf-8-sig')) - 1
                except:
                    record_count = 0
                
                cursor.execute("""
                    INSERT OR REPLACE INTO csv_index 
                    (filename, city, district, building_type, property_category, week_id, record_count, source, last_scanned)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (csv_filename, info['city'], info['district'], info['building_type'], 
                      info['property_category'], info['week_id'], record_count, 'local', datetime.now().isoformat()))
                
                if info['week_id']:
                    week_ids.add(info['week_id'])
                
                total_files += 1
                print(f"  ✓ [local] {csv_filename}: {info['city']}/{info['district']} / {info['building_type']} / {info['property_category']} / {info['week_id']}")
            
            except Exception as e:
                print(f"  ⚠️ {csv_filename} 處理失敗: {e}")
    else:
        print(f"⚠️ Upload 資料夾不存在: {upload_dir}")
    
    # === 掃描 Google Drive ===
    print(f"📁 Google Drive 狀態: available={drive_available}, folder_id={drive_folder_id}")
    if drive_available and drive_folder_id:
        print(f"📁 開始掃描 Google Drive...")
        try:
            drive_files = list_google_drive_files(drive_folder_id)
            print(f"📁 Google Drive 掃描到 {len(drive_files)} 個 CSV 檔案")
            
            for file_info in drive_files:
                try:
                    filename = file_info['name']
                    file_path = file_info['path']
                    file_id = file_info['id']
                    
                    # 從路徑解析城市和區域
                    # 路徑格式: "縣市/區域/檔案名.csv"
                    path_parts = file_path.split('/')
                    city = ''
                    district = ''
                    
                    if len(path_parts) >= 3:
                        city = path_parts[0]
                        district = path_parts[1]
                    elif len(path_parts) == 2:
                        city = path_parts[0]
                    
                    info = parse_csv_filename(filename)
                    
                    # 如果從路徑解析到了城市和區域，優先使用路徑中的資訊
                    if city:
                        info['city'] = city
                    if district:
                        info['district'] = district
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO csv_index 
                        (filename, city, district, building_type, property_category, week_id, record_count, source, file_id, last_scanned)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (filename, info['city'], info['district'], info['building_type'], 
                          info['property_category'], info['week_id'], 0, 'google_drive', file_id, datetime.now().isoformat()))
                    
                    if info['week_id']:
                        week_ids.add(info['week_id'])
                    
                    total_files += 1
                    print(f"  ✓ [drive] {file_path}: {info['city']}/{info['district']} / {info['building_type']} / {info['property_category']} / {info['week_id']}")
                
                except Exception as e:
                    print(f"  ⚠️ {file_info['name']} 處理失敗: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"⚠️ Google Drive 掃描過程出錯: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"ℹ️ Google Drive 未配置或不可用 (available={drive_available}, folder_id={drive_folder_id})")
    
    # === 更新版本記錄 ===
    for week_id in week_ids:
        cursor.execute("""
            INSERT OR REPLACE INTO versions (week_id, upload_date)
            VALUES (?, ?)
        """, (week_id, datetime.now().strftime("%Y-%m-%d")))
    
    conn.commit()
    conn.close()
    
    print(f"✓ 索引建立完成: {total_files} 個文件, {len(week_ids)} 個週次版本")

def load_csv_data(city: str, district: str, building_type: str, property_category: str, week_id: str) -> List[dict]:
    """
    按需載入 CSV 數據
    優先從 Google Drive 載入，次之從本地 upload 資料夾
    """
    upload_dir = get_upload_dir()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = "SELECT filename FROM csv_index WHERE 1=1"
    params = []
    
    if district:
        query += " AND district = ?"
        params.append(district)
    
    if building_type and building_type != '全部':
        bt = 'apartment' if building_type == '公寓' else 'building' if building_type == '電梯大樓' else building_type
        query += " AND building_type = ?"
        params.append(bt)
    
    if property_category and property_category != '全部':
        query += " AND property_category = ?"
        params.append(property_category)
    
    if week_id:
        query += " AND week_id = ?"
        params.append(week_id)
    
    cursor.execute(query, params)
    csv_files = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    print(f"📂 載入 CSV: district={district}, building={building_type}, category={property_category}, week={week_id}")
    print(f"   找到 {len(csv_files)} 個匹配的 CSV 文件: {csv_files}")
    
    all_properties = []
    
    # 嘗試從 Google Drive 載入
    if drive_available and district and week_id:
        building_types_to_load = []
        if building_type == '全部' or not building_type:
            building_types_to_load = ['公寓', '電梯大樓']
        else:
            building_types_to_load = [building_type]
        
        categories_to_load = []
        if property_category == '全部' or not property_category:
            categories_to_load = ['套房', '住家']
        else:
            categories_to_load = [property_category]
        
        for bt in building_types_to_load:
            for cat in categories_to_load:
                df = get_csv_from_drive(city, district, bt, cat, week_id)
                if df is not None:
                    properties = process_dataframe(df, city, district, bt, cat, week_id)
                    all_properties.extend(properties)
    
    # 如果 Google Drive 沒有數據，從本地載入
    if not all_properties:
        for csv_filename in csv_files:
            try:
                csv_path = os.path.join(upload_dir, csv_filename)
                df = pd.read_csv(csv_path, encoding='utf-8-sig')
                
                file_info = parse_csv_filename(csv_filename)
                
                properties = process_dataframe(
                    df, 
                    file_info['city'], 
                    file_info['district'], 
                    file_info['building_type'], 
                    file_info['property_category'], 
                    file_info['week_id']
                )
                all_properties.extend(properties)
            
            except Exception as e:
                print(f"  ⚠️ {csv_filename} 讀取失敗: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"   載入完成: {len(all_properties)} 筆房源")
    return all_properties

def process_dataframe(df: pd.DataFrame, city: str, district: str, building_type: str, property_category: str, week_id: str) -> List[dict]:
    """處理 DataFrame 並轉換為房源列表"""
    properties = []
    
    for _, row in df.iterrows():
        property_id = row.get('案件編號', '')
        if pd.isna(property_id) or not property_id:
            continue
        property_id = str(int(property_id) if isinstance(property_id, float) else property_id)
        
        title = str(row.get('標題', ''))
        
        raw_address = str(row.get('地址', ''))
        if city and not raw_address.startswith(city):
            raw_address = city + raw_address
        if district and district not in raw_address:
            raw_address = raw_address.replace(city, city + district)
        address = raw_address
        
        rent = row.get('租金', 0)
        if pd.isna(rent):
            rent = 0
        rent = int(rent)
        
        area = row.get('坪數', row.get('坡數', 0))
        if pd.isna(area):
            area = 0
        area = float(area)
        
        room_type = str(row.get('房型', ''))
        if room_type == 'nan':
            room_type = ''
        
        floor = str(row.get('樓層', ''))
        if floor == 'nan':
            floor = ''
        
        building_type_val = building_type or 'unknown'
        property_category_val = property_category or ''
        
        latitude = 0
        longitude = 0
        
        if '緯度' in df.columns and '經度' in df.columns:
            lat_val = row.get('緯度', 0)
            lng_val = row.get('經度', 0)
            if not pd.isna(lat_val) and not pd.isna(lng_val):
                latitude = float(lat_val)
                longitude = float(lng_val)
        
        if latitude == 0 and longitude == 0 and '座標' in df.columns:
            coord_str = row.get('座標', '')
            if not pd.isna(coord_str):
                latitude, longitude = parse_dms_coordinate(str(coord_str))
        
        prop_week_id = row.get('週次', row.get('年週', ''))
        if pd.isna(prop_week_id) or not prop_week_id:
            prop_week_id = week_id or get_week_id()
        prop_week_id = str(prop_week_id)
        if prop_week_id.endswith('.0'):
            prop_week_id = prop_week_id[:-2]
        
        if not address or rent <= 0:
            continue
        
        properties.append({
            'property_id': property_id,
            'title': title,
            'address': address,
            'rent_monthly': rent,
            'area': area,
            'room_type': room_type,
            'floor': floor,
            'latitude': latitude,
            'longitude': longitude,
            'building_type': building_type_val,
            'property_category': property_category_val,
            'upload_week': prop_week_id,
            'status': 'active'
        })
    
    return properties

# ============ API 端點 ============

@app.get("/api/versions")
async def get_versions():
    """獲取所有可用的週次版本"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        conn.close()
        return {"status": "success", "versions": versions, "count": len(versions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available-filters")
async def get_available_filters():
    """獲取可用的篩選選項（基於現有 CSV 文件）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT city, district FROM csv_index WHERE district != '' ORDER BY city, district")
        districts = [{"city": row[0], "district": row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT building_type FROM csv_index WHERE building_type != ''")
        building_types = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT property_category FROM csv_index WHERE property_category != ''")
        property_categories = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT week_id FROM csv_index WHERE week_id != '' ORDER BY week_id DESC")
        week_ids = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "status": "success",
            "filters": {
                "districts": districts,
                "building_types": building_types,
                "property_categories": property_categories,
                "week_ids": week_ids
            },
            "google_drive_available": drive_available
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    """分析 API - 按需載入指定條件的數據"""
    try:
        if lat is not None and lng is not None and lat != 0 and lng != 0:
            query_lat, query_lon = lat, lng
        else:
            query_lat, query_lon = 25.0288, 121.4625
        
        if not district:
            districts = [
                '板橋區', '三重區', '中和區', '永和區', '新莊區', '新店區', '土城區',
                '蘆洲區', '樹林區', '汐止區', '鶯歌區', '三峽區', '淡水區', '瑞芳區',
                '五股區', '泰山區', '林口區', '深坑區', '石碇區', '坪林區', '三芝區',
                '石門區', '八里區', '平溪區', '雙溪區', '貢寮區', '金山區', '萬里區',
                '烏來區', '大安區', '信義區', '中山區', '松山區', '南港區', '內湖區'
            ]
            for d in districts:
                if d in address:
                    district = d
                    break
        
        load_category = None
        if room_type == '套房':
            load_category = '套房'
        elif room_type in ['2房', '3房', '3房以上']:
            load_category = '住家'
        elif property_category:
            load_category = property_category
        
        # 根據區域自動判斷城市（如果未提供）
        if not city:
            taipei_districts = ['中正區', '大同區', '中山區', '松山區', '大安區', '萬華區', '信義區', '士林區', '北投區', '內湖區', '南港區', '文山區']
            if district in taipei_districts:
                city = '台北市'
            else:
                city = '新北市'
        
        all_properties = load_csv_data(
            city=city,
            district=district,
            building_type=building_type,
            property_category=load_category,
            week_id=week_id
        )
        
        filtered_properties = []
        for prop in all_properties:
            if prop['latitude'] == 0 and prop['longitude'] == 0:
                continue
            
            distance = haversine_distance(query_lat, query_lon, prop['latitude'], prop['longitude'])
            
            if distance_min <= distance <= distance_max:
                prop['distance'] = distance
                
                if room_type and room_type != '全部':
                    if room_type == '套房':
                        if prop.get('property_category') != '套房' and '套房' not in prop.get('room_type', ''):
                            continue
                    elif room_type == '2房':
                        if '2' not in prop.get('room_type', '') and '兩' not in prop.get('room_type', ''):
                            continue
                    elif room_type == '3房':
                        if '3' not in prop.get('room_type', '') and '三' not in prop.get('room_type', ''):
                            continue
                    elif room_type == '3房以上':
                        rt = prop.get('room_type', '')
                        has_large = any(str(n) in rt for n in range(4, 10)) or any(c in rt for c in ['四', '五', '六', '七', '八', '九'])
                        if not has_large:
                            continue
                
                filtered_properties.append(prop)
        
        active_properties = [p for p in filtered_properties if p['status'] == 'active']
        
        if active_properties:
            avg_rent = sum(p['rent_monthly'] for p in active_properties) / len(active_properties)
            min_rent = min(p['rent_monthly'] for p in active_properties)
            max_rent = max(p['rent_monthly'] for p in active_properties)
            avg_area = sum(p['area'] for p in active_properties if p['area'] > 0) / max(1, len([p for p in active_properties if p['area'] > 0]))
        else:
            avg_rent = min_rent = max_rent = avg_area = 0
        
        room_type_counts = {}
        for p in active_properties:
            rt = p['room_type'] or '未知'
            room_type_counts[rt] = room_type_counts.get(rt, 0) + 1
        
        room_type_analysis = [{"room_type": rt, "count": count} for rt, count in sorted(room_type_counts.items(), key=lambda x: -x[1])]
        
        return {
            "status": "success",
            "query": {
                "address": address,
                "district": district,
                "coordinates": {"latitude": query_lat, "longitude": query_lon},
                "distance_range": {"min": distance_min, "max": distance_max},
                "building_type": building_type,
                "property_category": load_category,
                "room_type": room_type,
                "week_id": week_id or "current"
            },
            "summary": {
                "total_properties": len(filtered_properties),
                "active_properties": len(active_properties),
                "deleted_properties": len(filtered_properties) - len(active_properties),
                "new_properties": 0,
                "avg_rent_all": round(avg_rent),
                "min_rent": min_rent,
                "max_rent": max_rent,
                "avg_area": round(avg_area, 1)
            },
            "properties": filtered_properties,
            "room_type_analysis": room_type_analysis,
            "data_source": "google_drive" if drive_available else "local"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class ResetRequest(BaseModel):
    password: str

@app.post("/api/admin/reset-database")
async def reset_database(request: ResetRequest):
    """重置數據庫並重新掃描 CSV"""
    if request.password != "1234":
        raise HTTPException(status_code=403, detail="密碼錯誤")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM csv_index")
        cursor.execute("DELETE FROM versions")
        conn.commit()
        conn.close()
        scan_available_csv_files()
        return {"status": "success", "message": "數據庫已重置並重新掃描 CSV 文件"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/database-status")
async def database_status():
    """獲取數據庫狀態"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM csv_index")
        csv_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(record_count) FROM csv_index")
        total_records = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT filename, district, building_type, property_category, week_id, record_count FROM csv_index ORDER BY district, building_type, property_category")
        csv_files = [{"filename": row[0], "district": row[1], "building_type": row[2], "property_category": row[3], "week_id": row[4], "record_count": row[5]} for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "status": "success",
            "database": {
                "csv_files_count": csv_count,
                "total_records": total_records,
                "versions_count": len(versions),
                "versions": versions,
                "csv_files": csv_files
            },
            "google_drive": {
                "available": drive_available,
                "folder_id": drive_folder_id if drive_available else None
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/rescan-csv")
async def rescan_csv():
    """重新掃描 CSV 文件"""
    try:
        scan_available_csv_files()
        
        # 返回掃描結果的詳細資訊
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM csv_index")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT DISTINCT city FROM csv_index")
        cities = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return {
            "status": "success", 
            "message": "CSV 文件已重新掃描",
            "indexed_files": count,
            "cities": cities,
            "drive_available": drive_available,
            "drive_folder_id": drive_folder_id
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/api/admin/drive-status")
async def get_drive_status():
    """診斷 Google Drive 連接狀態"""
    result = {
        "drive_available": drive_available,
        "drive_folder_id": drive_folder_id,
        "drive_folder_name": GOOGLE_DRIVE_FOLDER_NAME,
        "has_service": drive_service is not None,
        "env_key_exists": os.getenv('GOOGLE_DRIVE_KEY_JSON') is not None,
        "files_found": [],
        "error": None
    }
    
    if drive_available and drive_folder_id:
        try:
            files = list_google_drive_files(drive_folder_id)
            result["files_found"] = files[:50]  # 只返回前 50 個檔案
            result["total_files"] = len(files)
        except Exception as e:
            result["error"] = str(e)
    
    return result

# 靜態文件服務
static_dir = os.path.dirname(__file__)
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
