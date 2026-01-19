"""
租屋行情分析系統 - 版本控制 API v5.1
支持週次管理、動畫播放、留置時間著色、建築類型篩選和進階模式
支援案件編號（property_id）進行精確房源追蹤
支援原始 CSV 格式（度分秒座標自動轉換）
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

# 初始化 FastAPI
app = FastAPI(title="租屋行情分析 API v5.1")

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 應用啟動事件 ============

@app.on_event("startup")
async def startup_event():
    """應用啟動時初始化數據庫並自動導入 CSV"""
    init_database()
    auto_import_csv_files()


# 數據庫路徑
DB_PATH = os.path.join(os.path.dirname(__file__), "rental.db")

# ============ 數據庫初始化 ============

def init_database():
    """初始化數據庫，添加版本控制字段和建築類型"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id TEXT UNIQUE NOT NULL,
            upload_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id TEXT UNIQUE,
            title TEXT,
            address TEXT,
            rent_monthly INTEGER,
            area REAL,
            room_type TEXT,
            floor TEXT,
            latitude REAL,
            longitude REAL,
            renovation_status TEXT,
            first_published_date TEXT,
            upload_week TEXT,
            status TEXT DEFAULT 'active',
            building_type TEXT DEFAULT 'apartment',
            deleted_date TEXT
        )
    """)
    
    cursor.execute("PRAGMA table_info(properties)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'property_id' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN property_id TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_property_id ON properties(property_id)")
    
    if 'first_published_date' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN first_published_date TEXT")
    
    if 'deleted_date' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN deleted_date TEXT")
    
    if 'upload_week' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN upload_week TEXT")
    
    if 'status' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN status TEXT DEFAULT 'active'")
    
    if 'building_type' not in columns:
        cursor.execute("ALTER TABLE properties ADD COLUMN building_type TEXT DEFAULT 'apartment'")
    
    conn.commit()
    conn.close()

# ============ 工具函數 ============

def get_week_id(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    year = date.year % 100
    week = date.isocalendar()[1]
    return f"{year:02d}{week:02d}"

def extract_building_type_from_filename(filename: str) -> str:
    if '電梯大樓' in filename or '電梯' in filename:
        return 'building'
    elif '公寓' in filename:
        return 'apartment'
    return 'unknown'

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
    """
    解析度分秒格式的座標字串
    支援格式: 25°0'17"N 121°29'47"E 或 25°0'17"N, 121°29'47"E
    返回: (緯度, 經度) 或 (0, 0) 如果解析失敗
    """
    if not coord_str or coord_str == 'nan':
        return 0, 0
    
    try:
        # 移除多餘空白和逗號
        coord_str = str(coord_str).strip()
        
        # 匹配度分秒格式: 25°0'17"N 或 121°29'47"E
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
                # 計算十進位緯度
                lat = lat_match[0] + lat_match[1]/60 + lat_match[2]/3600
                if lat_match[3] == 'S':
                    lat = -lat
                
                # 計算十進位經度
                lng = lng_match[0] + lng_match[1]/60 + lng_match[2]/3600
                if lng_match[3] == 'W':
                    lng = -lng
                
                return round(lat, 6), round(lng, 6)
        
        return 0, 0
    except Exception as e:
        print(f"座標解析錯誤: {coord_str} - {e}")
        return 0, 0

def extract_district_from_address(address: str) -> tuple:
    """
    從地址中提取城市和區域
    返回: (城市, 區域, 清理後的地址)
    """
    if not address:
        return '', '', ''
    
    address = str(address).strip()
    
    # 定義城市和區域的映射
    cities = ['臺北市', '台北市', '新北市', '基隆市', '桃園市', '新竹市', '新竹縣']
    
    # 新北市的區域
    new_taipei_districts = [
        '板橋區', '三重區', '中和區', '永和區', '新莊區', '新店區', '土城區',
        '蘆洲區', '樹林區', '汐止區', '鶯歌區', '三峽區', '淡水區', '瑞芳區',
        '五股區', '泰山區', '林口區', '深坑區', '石碇區', '坪林區', '三芝區',
        '石門區', '八里區', '平溪區', '雙溪區', '貢寮區', '金山區', '萬里區',
        '烏來區'
    ]
    
    city = ''
    district = ''
    
    # 檢查地址是否以城市開頭
    for c in cities:
        if address.startswith(c):
            city = c
            address = address[len(c):]
            break
    
    # 檢查是否包含區域
    for d in new_taipei_districts:
        if address.startswith(d):
            district = d
            if not city:
                city = '新北市'
            break
        elif d in address:
            district = d
            if not city:
                city = '新北市'
            break
    
    # 如果沒有找到城市但找到了區域，根據區域推斷城市
    if not city and district:
        city = '新北市'
    
    # 組合完整地址
    full_address = city + address if city and not address.startswith(city) else address
    if city and district and not full_address.startswith(city):
        full_address = city + full_address
    
    return city, district, full_address

# ============ CSV 導入功能 ============

def auto_import_csv_files():
    import pandas as pd
    
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "upload"),
        "/app/upload",
        "./upload",
        os.path.join(os.getcwd(), "upload")
    ]
    
    upload_dir = None
    for path in possible_paths:
        if os.path.exists(path):
            upload_dir = path
            print(f"✅ 找到 upload 資料夾: {upload_dir}")
            break
    
    if upload_dir is None:
        upload_dir = possible_paths[0]
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
            print(f"✅ 已創建 upload 資料夾: {upload_dir}")
            return
    
    csv_files = [f for f in os.listdir(upload_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print("⚠️  upload 資料夾中沒有找到 CSV 檔案")
        return
    
    print(f"📁 找到 {len(csv_files)} 個 CSV 檔案，開始導入...")
    
    week_data = {}
    
    for csv_filename in csv_files:
        try:
            csv_path = os.path.join(upload_dir, csv_filename)
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            
            # 從文件名提取建築類型
            filename_building_type = extract_building_type_from_filename(csv_filename)
            
            # 從文件名提取週次
            filename_week = None
            week_match = re.search(r'_(\d{4})\.csv$', csv_filename)
            if week_match:
                filename_week = week_match.group(1)
            # 也嘗試匹配 _2603_merged.csv 格式
            week_match2 = re.search(r'_(\d{4})_merged\.csv$', csv_filename)
            if week_match2:
                filename_week = week_match2.group(1)
            
            print(f"  處理: {csv_filename} (建築類型: {filename_building_type}, 週次: {filename_week})")
            
            for _, row in df.iterrows():
                # 提取案件編號
                property_id = row.get('案件編號', '')
                if pd.isna(property_id) or not property_id:
                    continue
                property_id = str(int(property_id) if isinstance(property_id, float) else property_id)
                
                # 提取標題
                title = str(row.get('標題', ''))
                
                # 提取地址並補充城市區域
                raw_address = str(row.get('地址', ''))
                city, district, address = extract_district_from_address(raw_address)
                
                # 租金
                rent = row.get('租金', 0)
                if pd.isna(rent):
                    rent = 0
                rent = int(rent)
                
                # 坪數（支援「坪數」和「坡數」兩種欄位名）
                area = row.get('坪數', row.get('坡數', 0))
                if pd.isna(area):
                    area = 0
                area = float(area)
                
                # 房型
                room_type = str(row.get('房型', ''))
                if room_type == 'nan':
                    room_type = ''
                
                # 樓層
                floor = str(row.get('樓層', ''))
                if floor == 'nan':
                    floor = ''
                
                # 建築類型（優先從 CSV 欄位讀取，否則從文件名推斷）
                csv_building_type = str(row.get('建築類型', ''))
                if csv_building_type and csv_building_type != 'nan':
                    if '電梯' in csv_building_type or '大樓' in csv_building_type:
                        building_type = 'building'
                    elif '公寓' in csv_building_type:
                        building_type = 'apartment'
                    else:
                        building_type = filename_building_type
                else:
                    building_type = filename_building_type
                
                # 座標處理：支援兩種格式
                # 1. 新格式：獨立的「緯度」和「經度」欄位
                # 2. 原始格式：「座標」欄位（度分秒格式）
                latitude = 0
                longitude = 0
                
                if '緯度' in df.columns and '經度' in df.columns:
                    # 新格式
                    lat_val = row.get('緯度', 0)
                    lng_val = row.get('經度', 0)
                    if not pd.isna(lat_val) and not pd.isna(lng_val):
                        latitude = float(lat_val)
                        longitude = float(lng_val)
                
                if latitude == 0 and longitude == 0 and '座標' in df.columns:
                    # 原始格式：度分秒
                    coord_str = row.get('座標', '')
                    if not pd.isna(coord_str):
                        latitude, longitude = parse_dms_coordinate(str(coord_str))
                
                # 週次（支援「週次」和「年週」兩種欄位名）
                week_id = row.get('週次', row.get('年週', ''))
                if pd.isna(week_id) or not week_id:
                    week_id = filename_week if filename_week else get_week_id()
                week_id = str(week_id)
                if week_id.endswith('.0'):
                    week_id = week_id[:-2]
                # 確保週次是4位數字
                if len(week_id) == 4 and week_id.isdigit():
                    pass  # 格式正確
                else:
                    week_id = filename_week if filename_week else get_week_id()
                
                # 裝修狀態
                renovation_status = str(row.get('裝修狀態', 'unknown'))
                if renovation_status == 'nan':
                    renovation_status = 'unknown'
                
                # 跳過無效數據
                if not address or rent <= 0:
                    continue
                
                # 按週次分組
                if week_id not in week_data:
                    week_data[week_id] = []
                
                week_data[week_id].append({
                    'property_id': property_id,
                    'title': title,
                    'address': address,
                    'rent': rent,
                    'area': area,
                    'room_type': room_type,
                    'floor': floor,
                    'latitude': latitude,
                    'longitude': longitude,
                    'building_type': building_type,
                    'renovation_status': renovation_status
                })
            
            print(f"  ✓ 讀取完成: {csv_filename} ({len(df)} 行)")
        
        except Exception as e:
            print(f"  ⚠️  {csv_filename} 讀取失敗: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not week_data:
        print("❌ 沒有成功讀取任何數據")
        return
    
    # 導入到數據庫
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    upload_date = datetime.now().strftime("%Y-%m-%d")
    total_new = 0
    total_updated = 0
    
    for week_id, properties in sorted(week_data.items()):
        print(f"\n📅 處理週次 {week_id}...")
        
        cursor.execute("INSERT OR REPLACE INTO versions (week_id, upload_date) VALUES (?, ?)", (week_id, upload_date))
        
        current_week_ids = set()
        
        # 去重（基於 property_id）
        seen_ids = set()
        unique_properties = []
        for prop in properties:
            if prop['property_id'] not in seen_ids:
                seen_ids.add(prop['property_id'])
                unique_properties.append(prop)
        
        print(f"  去重後: {len(unique_properties)} 筆")
        
        week_new = 0
        week_updated = 0
        
        for prop in unique_properties:
            try:
                current_week_ids.add(prop['property_id'])
                
                cursor.execute("SELECT id, first_published_date FROM properties WHERE property_id = ?", (prop['property_id'],))
                result = cursor.fetchone()
                
                if result:
                    cursor.execute("""
                        UPDATE properties 
                        SET title = ?, address = ?, rent_monthly = ?, area = ?,
                            room_type = ?, floor = ?, latitude = ?, longitude = ?,
                            building_type = ?, renovation_status = ?,
                            status = 'active', upload_week = ?, deleted_date = NULL
                        WHERE property_id = ?
                    """, (prop['title'], prop['address'], prop['rent'], prop['area'],
                          prop['room_type'], prop['floor'], prop['latitude'], prop['longitude'],
                          prop['building_type'], prop['renovation_status'],
                          week_id, prop['property_id']))
                    week_updated += 1
                else:
                    first_published_date = upload_date
                    cursor.execute("""
                        INSERT INTO properties 
                        (property_id, title, address, rent_monthly, area, room_type, floor, 
                         latitude, longitude, building_type, renovation_status, 
                         first_published_date, upload_week, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (prop['property_id'], prop['title'], prop['address'], prop['rent'], 
                          prop['area'], prop['room_type'], prop['floor'], 
                          prop['latitude'], prop['longitude'], prop['building_type'], 
                          prop['renovation_status'], first_published_date, week_id))
                    week_new += 1
            except Exception as e:
                print(f"    ⚠️ 導入失敗 {prop['property_id']}: {e}")
                continue
        
        print(f"  新增: {week_new} 筆, 更新: {week_updated} 筆")
        total_new += week_new
        total_updated += week_updated
        
        # 標記本週未出現的房源為 deleted（只對最新週次執行）
        all_weeks = sorted(week_data.keys())
        if week_id == all_weeks[-1] and current_week_ids:
            placeholders = ','.join(['?' for _ in current_week_ids])
            cursor.execute(f"""
                UPDATE properties 
                SET status = 'deleted', deleted_date = ?
                WHERE status = 'active' 
                AND property_id NOT IN ({placeholders})
                AND upload_week < ?
            """, [upload_date] + list(current_week_ids) + [week_id])
            
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"  標記下架: {deleted_count} 筆")
    
    conn.commit()
    
    # 統計有座標的房源
    cursor.execute("SELECT COUNT(*) FROM properties WHERE latitude != 0 AND longitude != 0")
    with_coords = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n✅ CSV 導入完成！")
    print(f"  總新增: {total_new} 筆")
    print(f"  總更新: {total_updated} 筆")
    print(f"  有座標: {with_coords}/{total} 筆")
    print(f"  週次版本: {', '.join(sorted(week_data.keys()))}")

# ============ API 端點 ============

@app.get("/api/versions")
async def get_versions():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        conn.close()
        return {"status": "success", "versions": versions, "count": len(versions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis_v4")
async def analysis_v4(
    address: str,
    distance_min: int = 300,
    distance_max: int = 3000,
    building_type: Optional[str] = None,
    room_type: Optional[str] = None,
    week_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None
):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if lat is not None and lng is not None and lat != 0 and lng != 0:
            query_lat, query_lon = lat, lng
        else:
            query_lat, query_lon = 25.0288, 121.4625
        
        query = "SELECT * FROM properties WHERE status IN ('active', 'deleted')"
        params = []
        
        if week_id:
            query += " AND upload_week <= ?"
            params.append(week_id)
        
        cursor.execute(query, params)
        all_properties = cursor.fetchall()
        
        cursor.execute("PRAGMA table_info(properties)")
        columns = {row[1]: row[0] for row in cursor.fetchall()}
        
        filtered_properties = []
        for prop in all_properties:
            lat_idx = columns.get('latitude')
            lng_idx = columns.get('longitude')
            if lat_idx is None or lng_idx is None:
                continue
            if prop[lat_idx] is None or prop[lng_idx] is None:
                continue
            if prop[lat_idx] == 0.0 and prop[lng_idx] == 0.0:
                continue
            
            prop_dict = {
                'id': prop[columns['id']],
                'property_id': prop[columns.get('property_id', columns['id'])] if 'property_id' in columns else None,
                'title': prop[columns['title']],
                'address': prop[columns['address']],
                'rent_monthly': prop[columns['rent_monthly']],
                'area': prop[columns['area']],
                'floor': prop[columns['floor']] if 'floor' in columns else '',
                'room_type': prop[columns['room_type']],
                'latitude': prop[columns['latitude']],
                'longitude': prop[columns['longitude']],
                'building_type': prop[columns['building_type']] if 'building_type' in columns else 'apartment',
                'renovation_status': prop[columns['renovation_status']] if 'renovation_status' in columns else 'unknown',
                'first_published_date': prop[columns['first_published_date']] if 'first_published_date' in columns else None,
                'upload_week': prop[columns['upload_week']] if 'upload_week' in columns else None,
                'status': prop[columns['status']] if 'status' in columns else 'active'
            }
            
            distance = haversine_distance(query_lat, query_lon, prop_dict['latitude'], prop_dict['longitude'])
            
            if distance_min <= distance <= distance_max:
                weeks_since = calculate_weeks_since_published(prop_dict['first_published_date'])
                prop_dict['weeks_since_first_published'] = weeks_since
                prop_dict['distance'] = distance
                
                if building_type and building_type != '全部':
                    prop_building = prop_dict['building_type']
                    if building_type == '公寓' and prop_building != 'apartment':
                        continue
                    if building_type == '電梯大樓' and prop_building != 'building':
                        continue
                
                if room_type and room_type != '全部' and prop_dict['room_type'] != room_type:
                    continue
                
                filtered_properties.append(prop_dict)
        
        conn.close()
        
        active_properties = [p for p in filtered_properties if p['status'] == 'active']
        deleted_properties = [p for p in filtered_properties if p['status'] == 'deleted']
        
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
                "coordinates": {"latitude": query_lat, "longitude": query_lon},
                "distance_range": {"min": distance_min, "max": distance_max},
                "week_id": week_id or "current"
            },
            "summary": {
                "total_properties": len(filtered_properties),
                "active_properties": len(active_properties),
                "deleted_properties": len(deleted_properties),
                "new_properties": len([p for p in active_properties if p.get('weeks_since_first_published', 0) == 0]),
                "avg_rent_all": round(avg_rent),
                "min_rent": min_rent,
                "max_rent": max_rent,
                "avg_area": round(avg_area, 1)
            },
            "properties": filtered_properties,
            "room_type_analysis": room_type_analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ResetRequest(BaseModel):
    password: str

@app.post("/api/admin/reset-database")
async def reset_database(request: ResetRequest):
    if request.password != "1234":
        raise HTTPException(status_code=403, detail="密碼錯誤")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM properties")
        cursor.execute("DELETE FROM versions")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='properties'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='versions'")
        conn.commit()
        conn.close()
        auto_import_csv_files()
        return {"status": "success", "message": "數據庫已重置並重新導入數據"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/database-status")
async def database_status():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM properties")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE status = 'active'")
        active = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE status = 'deleted'")
        deleted = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE latitude != 0 AND longitude != 0")
        with_coords = cursor.fetchone()[0]
        
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "status": "success",
            "database": {
                "total_properties": total,
                "active_properties": active,
                "deleted_properties": deleted,
                "with_coordinates": with_coords,
                "versions_count": len(versions),
                "versions": versions
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

static_dir = os.path.dirname(__file__)
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
