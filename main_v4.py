"""
租屋行情分析系統 - 版本控制 API v6.0
支持四象限分類（建物類型 x 房型大類）按需載入 CSV
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

# 初始化 FastAPI
app = FastAPI(title="租屋行情分析 API v6.0")

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
    init_database()
    scan_available_csv_files()

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
            last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
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
                    lat_match = (float(deg), float(min_), float(sec), direction)
                elif direction in ['E', 'W']:
                    lng_match = (float(deg), float(min_), float(sec), direction)
            
            if lat_match and lng_match:
                lat = lat_match[0] + lat_match[1]/60 + lat_match[2]/3600
                if lat_match[3] == 'S':
                    lat = -lat
                
                lng = lng_match[0] + lng_match[1]/60 + lng_match[2]/3600
                if lng_match[3] == 'W':
                    lng = -lng
                
                return round(lat, 6), round(lng, 6)
        
        return 0, 0
    except Exception as e:
        print(f"座標解析錯誤: {coord_str} - {e}")
        return 0, 0

def parse_csv_filename(filename: str) -> dict:
    """
    解析 CSV 文件名，提取分類信息
    支援格式：
    - 新格式: 新北市_中和區_公寓_套房_2604.csv
    - 舊格式: 591_中和區_公寓_整層住家_page1.csv
    - 合併格式: 中和公寓套房_2603_merged.csv
    """
    result = {
        'city': '',
        'district': '',
        'building_type': '',  # apartment 或 building
        'property_category': '',  # 套房 或 住家
        'week_id': ''
    }
    
    # 移除 .csv 後綴
    name = filename.replace('.csv', '')
    
    # 嘗試提取週次
    week_match = re.search(r'_(\d{4})(?:_merged)?$', name)
    if week_match:
        result['week_id'] = week_match.group(1)
    
    # 提取建築類型
    if '電梯大樓' in filename or '電梯' in filename:
        result['building_type'] = 'building'
    elif '公寓' in filename:
        result['building_type'] = 'apartment'
    
    # 提取房型大類
    if '套房' in filename or '獨立套房' in filename:
        result['property_category'] = '套房'
    elif '住家' in filename or '整層住家' in filename:
        result['property_category'] = '住家'
    
    # 提取區域
    districts = [
        '板橋區', '三重區', '中和區', '永和區', '新莊區', '新店區', '土城區',
        '蘆洲區', '樹林區', '汐止區', '鶯歌區', '三峽區', '淡水區', '瑞芳區',
        '五股區', '泰山區', '林口區', '深坑區', '石碇區', '坪林區', '三芝區',
        '石門區', '八里區', '平溪區', '雙溪區', '貢寮區', '金山區', '萬里區',
        '烏來區'
    ]
    
    for district in districts:
        if district in filename:
            result['district'] = district
            result['city'] = '新北市'
            break
    
    # 如果文件名以城市開頭
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
    """掃描 upload 資料夾中的 CSV 文件並建立索引"""
    upload_dir = get_upload_dir()
    
    if not os.path.exists(upload_dir):
        print(f"⚠️ Upload 資料夾不存在: {upload_dir}")
        return
    
    csv_files = [f for f in os.listdir(upload_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print("⚠️ upload 資料夾中沒有找到 CSV 檔案")
        return
    
    print(f"📁 掃描到 {len(csv_files)} 個 CSV 檔案")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 清空舊索引
    cursor.execute("DELETE FROM csv_index")
    
    week_ids = set()
    
    for csv_filename in csv_files:
        try:
            info = parse_csv_filename(csv_filename)
            
            # 計算記錄數
            csv_path = os.path.join(upload_dir, csv_filename)
            try:
                df = pd.read_csv(csv_path, encoding='utf-8-sig', nrows=0)
                record_count = sum(1 for _ in open(csv_path, encoding='utf-8-sig')) - 1
            except:
                record_count = 0
            
            cursor.execute("""
                INSERT OR REPLACE INTO csv_index 
                (filename, city, district, building_type, property_category, week_id, record_count, last_scanned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (csv_filename, info['city'], info['district'], info['building_type'], 
                  info['property_category'], info['week_id'], record_count, datetime.now().isoformat()))
            
            if info['week_id']:
                week_ids.add(info['week_id'])
            
            print(f"  ✓ {csv_filename}: {info['district']} / {info['building_type']} / {info['property_category']} / {info['week_id']}")
        
        except Exception as e:
            print(f"  ⚠️ {csv_filename} 解析失敗: {e}")
    
    # 更新版本表
    upload_date = datetime.now().strftime("%Y-%m-%d")
    for week_id in week_ids:
        cursor.execute("INSERT OR REPLACE INTO versions (week_id, upload_date) VALUES (?, ?)", (week_id, upload_date))
    
    conn.commit()
    conn.close()
    
    print(f"✅ CSV 索引建立完成，週次版本: {', '.join(sorted(week_ids))}")

def load_csv_data(city: str, district: str, building_type: str = None, property_category: str = None, week_id: str = None) -> list:
    """
    按需載入指定條件的 CSV 數據
    
    參數:
    - city: 縣市
    - district: 區域
    - building_type: 建築類型 (apartment/building/None=全部)
    - property_category: 房型大類 (套房/住家/None=全部)
    - week_id: 週次
    
    返回: 房源列表
    """
    upload_dir = get_upload_dir()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 構建查詢條件
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
    
    for csv_filename in csv_files:
        try:
            csv_path = os.path.join(upload_dir, csv_filename)
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            
            # 從文件名提取信息
            file_info = parse_csv_filename(csv_filename)
            
            for _, row in df.iterrows():
                # 提取案件編號
                property_id = row.get('案件編號', '')
                if pd.isna(property_id) or not property_id:
                    continue
                property_id = str(int(property_id) if isinstance(property_id, float) else property_id)
                
                # 提取標題
                title = str(row.get('標題', ''))
                
                # 提取地址
                raw_address = str(row.get('地址', ''))
                # 補充城市和區域
                if file_info['city'] and not raw_address.startswith(file_info['city']):
                    raw_address = file_info['city'] + raw_address
                if file_info['district'] and file_info['district'] not in raw_address:
                    raw_address = raw_address.replace(file_info['city'], file_info['city'] + file_info['district'])
                address = raw_address
                
                # 租金
                rent = row.get('租金', 0)
                if pd.isna(rent):
                    rent = 0
                rent = int(rent)
                
                # 坪數
                area = row.get('坪數', row.get('坡數', 0))
                if pd.isna(area):
                    area = 0
                area = float(area)
                
                # 房型（細分）
                room_type = str(row.get('房型', ''))
                if room_type == 'nan':
                    room_type = ''
                
                # 樓層
                floor = str(row.get('樓層', ''))
                if floor == 'nan':
                    floor = ''
                
                # 建築類型
                building_type_val = file_info['building_type'] or 'unknown'
                
                # 房型大類
                property_category_val = file_info['property_category'] or ''
                
                # 座標處理
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
                
                # 週次
                prop_week_id = row.get('週次', row.get('年週', ''))
                if pd.isna(prop_week_id) or not prop_week_id:
                    prop_week_id = file_info['week_id'] or get_week_id()
                prop_week_id = str(prop_week_id)
                if prop_week_id.endswith('.0'):
                    prop_week_id = prop_week_id[:-2]
                
                # 跳過無效數據
                if not address or rent <= 0:
                    continue
                
                all_properties.append({
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
        
        except Exception as e:
            print(f"  ⚠️ {csv_filename} 讀取失敗: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"   載入完成: {len(all_properties)} 筆房源")
    return all_properties

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
        
        # 獲取可用的區域
        cursor.execute("SELECT DISTINCT city, district FROM csv_index WHERE district != '' ORDER BY city, district")
        districts = [{"city": row[0], "district": row[1]} for row in cursor.fetchall()]
        
        # 獲取可用的建築類型
        cursor.execute("SELECT DISTINCT building_type FROM csv_index WHERE building_type != ''")
        building_types = [row[0] for row in cursor.fetchall()]
        
        # 獲取可用的房型大類
        cursor.execute("SELECT DISTINCT property_category FROM csv_index WHERE property_category != ''")
        property_categories = [row[0] for row in cursor.fetchall()]
        
        # 獲取可用的週次
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
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis_v4")
async def analysis_v4(
    address: str,
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
    分析 API - 按需載入指定條件的數據
    
    新增參數:
    - district: 區域（用於決定載入哪些 CSV）
    - property_category: 房型大類（套房/住家，用於決定載入哪些 CSV）
    - room_type: 房型細分（套房/2房/3房/3房以上，用於前端篩選）
    """
    try:
        # 確定查詢座標
        if lat is not None and lng is not None and lat != 0 and lng != 0:
            query_lat, query_lon = lat, lng
        else:
            query_lat, query_lon = 25.0288, 121.4625
        
        # 從地址提取區域（如果未指定）
        if not district:
            districts = [
                '板橋區', '三重區', '中和區', '永和區', '新莊區', '新店區', '土城區',
                '蘆洲區', '樹林區', '汐止區', '鶯歌區', '三峽區', '淡水區', '瑞芳區',
                '五股區', '泰山區', '林口區', '深坑區', '石碇區', '坪林區', '三芝區',
                '石門區', '八里區', '平溪區', '雙溪區', '貢寮區', '金山區', '萬里區',
                '烏來區'
            ]
            for d in districts:
                if d in address:
                    district = d
                    break
        
        # 決定要載入的房型大類
        # 如果 room_type 是「套房」，只載入套房 CSV
        # 如果 room_type 是「2房」「3房」「3房以上」，只載入住家 CSV
        # 如果 room_type 是「全部」或未指定，載入全部
        load_category = None
        if room_type == '套房':
            load_category = '套房'
        elif room_type in ['2房', '3房', '3房以上']:
            load_category = '住家'
        elif property_category:
            load_category = property_category
        
        # 按需載入 CSV 數據
        all_properties = load_csv_data(
            city='新北市',
            district=district,
            building_type=building_type,
            property_category=load_category,
            week_id=week_id
        )
        
        # 篩選符合條件的房源
        filtered_properties = []
        for prop in all_properties:
            # 檢查座標
            if prop['latitude'] == 0 and prop['longitude'] == 0:
                continue
            
            # 計算距離
            distance = haversine_distance(query_lat, query_lon, prop['latitude'], prop['longitude'])
            
            # 距離篩選
            if distance_min <= distance <= distance_max:
                prop['distance'] = distance
                
                # 房型細分篩選（前端篩選）
                if room_type and room_type != '全部':
                    if room_type == '套房':
                        # 套房：只顯示套房
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
                        # 檢查是否有 4房以上
                        has_large = any(str(n) in rt for n in range(4, 10)) or any(c in rt for c in ['四', '五', '六', '七', '八', '九'])
                        if not has_large:
                            continue
                
                filtered_properties.append(prop)
        
        # 計算統計數據
        active_properties = [p for p in filtered_properties if p['status'] == 'active']
        
        if active_properties:
            avg_rent = sum(p['rent_monthly'] for p in active_properties) / len(active_properties)
            min_rent = min(p['rent_monthly'] for p in active_properties)
            max_rent = max(p['rent_monthly'] for p in active_properties)
            avg_area = sum(p['area'] for p in active_properties if p['area'] > 0) / max(1, len([p for p in active_properties if p['area'] > 0]))
        else:
            avg_rent = min_rent = max_rent = avg_area = 0
        
        # 房型分布統計
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
            "room_type_analysis": room_type_analysis
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
        
        # CSV 文件統計
        cursor.execute("SELECT COUNT(*) FROM csv_index")
        csv_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(record_count) FROM csv_index")
        total_records = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        
        # CSV 文件詳情
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
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/rescan-csv")
async def rescan_csv():
    """重新掃描 CSV 文件"""
    try:
        scan_available_csv_files()
        return {"status": "success", "message": "CSV 文件已重新掃描"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 靜態文件服務
static_dir = os.path.dirname(__file__)
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
