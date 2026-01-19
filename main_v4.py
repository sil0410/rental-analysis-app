"""
租屋行情分析系統 - 版本控制 API v4.0
支持週次管理、動畫播放、留置時間著色、建築類型篩選和進階模式
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
app = FastAPI(title="租屋行情分析 API v4.0")

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
    
    # 檢查是否已有版本表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id TEXT UNIQUE NOT NULL,
            upload_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 首先創建 properties 表（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # 檢查 properties 表是否有必要字段
    cursor.execute("PRAGMA table_info(properties)")
    columns = {row[1] for row in cursor.fetchall()}
    
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
    """
    生成週次 ID，格式為 YYWW
    例如：2601 表示 2026 年第 01 週
    """
    if date is None:
        date = datetime.now()
    
    year = date.year % 100  # 取後兩位年份
    week = date.isocalendar()[1]  # 取 ISO 週數
    
    return f"{year:02d}{week:02d}"

def extract_building_type_from_filename(filename: str) -> str:
    """從 CSV 文件名提取建築類型"""
    if '電梯大樓' in filename:
        return 'building'
    elif '公寓' in filename:
        return 'apartment'
    elif '套房' in filename:
        return 'apartment'
    elif '透天' in filename:
        return 'house'
    else:
        return 'apartment'  # 默認值

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點之間的距離（公里）"""
    R = 6371  # 地球半徑（公里）
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c * 1000  # 轉換為公尺

def calculate_weeks_since_published(first_published_date: str) -> int:
    """計算從首次發布到現在的週數"""
    if not first_published_date:
        return 0
    
    try:
        pub_date = datetime.strptime(first_published_date, "%Y-%m-%d")
        today = datetime.now()
        delta = today - pub_date
        return delta.days // 7
    except:
        return 0

# ============ 版本管理 API ============

@app.get("/api/versions")
async def get_versions():
    """獲取所有版本列表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT week_id, upload_date 
            FROM versions 
            ORDER BY week_id ASC
        """)
        
        versions = [
            {'week_id': row[0], 'upload_date': row[1]}
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return {
            'status': 'success',
            'versions': versions
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

# ============ 數據導入 API ============


# ============ 自動導入 CSV ============

def auto_import_csv_files():
    """自動導入 upload 資料夾中的所有 CSV 檔案（合併導入模式）"""
    import pandas as pd
    
    # 使用多個可能的路徑
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
    
    # 如果都不存在，嘗試創建
    if upload_dir is None:
        upload_dir = possible_paths[0]
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
            print(f"✅ 已創建 upload 資料夾: {upload_dir}")
            return
    
    # 掃描所有 CSV 檔案
    csv_files = [f for f in os.listdir(upload_dir) if f.endswith('.csv') and not f.endswith('_converted.csv')]
    
    if not csv_files:
        print("⚠️  upload 資料夾中沒有找到 CSV 檔案")
        return
    
    print(f"📁 找到 {len(csv_files)} 個 CSV 檔案，開始合併導入...")
    print(f"📂 upload 資料夾路徑: {upload_dir}")
    
    # 第一步：合併所有 CSV 檔案
    all_data = []
    for csv_filename in csv_files:
        try:
            csv_path = os.path.join(upload_dir, csv_filename)
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            all_data.append(df)
            print(f"  ✓ 讀取: {csv_filename} ({len(df)} 行)")
        except Exception as e:
            print(f"  ⚠️  {csv_filename} 讀取失敗: {e}")
            continue
    
    if not all_data:
        print("❌ 沒有成功讀取任何 CSV 檔案")
        return
    
    # 合併所有數據
    merged_df = pd.concat(all_data, ignore_index=True)
    print(f"✅ 已合併 {len(merged_df)} 行數據")
    
    # 去重：保留第一次出現的房源（基於地址 + 租金）
    merged_df = merged_df.drop_duplicates(subset=['地址', '租金'], keep='first')
    print(f"✅ 去重後 {len(merged_df)} 行數據")
    
    # 第二步：導入到數據庫
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    week_id = get_week_id()
    upload_date = datetime.now().strftime("%Y-%m-%d")
    
    # 記錄新版本
    cursor.execute("""
        INSERT OR REPLACE INTO versions (week_id, upload_date)
        VALUES (?, ?)
    """, (week_id, upload_date))
    
    # 獲取現有房源 ID（在導入前）
    cursor.execute("SELECT id FROM properties WHERE status = 'active'")
    existing_ids = {row[0] for row in cursor.fetchall()}
    
    # 處理新數據
    new_ids = set()
    imported_count = 0
    
    for _, row in merged_df.iterrows():
        try:
            # 提取數據
            title = str(row.get('標題', ''))
            address = str(row.get('地址', ''))
            rent = int(row.get('租金', 0)) if pd.notna(row.get('租金', 0)) else 0
            area = float(row.get('坪數', 0)) if pd.notna(row.get('坪數', 0)) else 0
            room_type = str(row.get('房型', ''))
            floor = str(row.get('樓層', ''))
            latitude = float(row.get('緯度', 0)) if pd.notna(row.get('緯度', 0)) else 0
            longitude = float(row.get('經度', 0)) if pd.notna(row.get('經度', 0)) else 0
            renovation_status = str(row.get('裝修狀態', 'unknown'))
            
            # 跳過無效數據
            if not address or not title or rent <= 0:
                continue
            
            # 檢查是否已存在
            cursor.execute("""
                SELECT id FROM properties 
                WHERE address = ? AND rent_monthly = ?
            """, (address, rent))
            
            result = cursor.fetchone()
            
            if result:
                # 已存在，更新狀態
                prop_id = result[0]
                new_ids.add(prop_id)
                
                cursor.execute("""
                    UPDATE properties 
                    SET status = 'active', upload_week = ?, building_type = ?
                    WHERE id = ?
                """, (week_id, 'apartment', prop_id))
            else:
                # 新房源
                first_published_date = datetime.now().strftime("%Y-%m-%d")
                
                cursor.execute("""
                    INSERT INTO properties 
                    (title, address, rent_monthly, area, room_type, floor, latitude, longitude, 
                     building_type, renovation_status, first_published_date, upload_week, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """, (title, address, rent, area, room_type, floor, latitude, longitude,
                      'apartment', renovation_status, first_published_date, week_id))
                
                new_ids.add(cursor.lastrowid)
                imported_count += 1
        
        except Exception as e:
            continue
    
    # 標記已刪除的房源（只在所有檔案都導入完成後）
    deleted_ids = existing_ids - new_ids
    for prop_id in deleted_ids:
        cursor.execute("""
            UPDATE properties 
            SET status = 'deleted', deleted_date = ?
            WHERE id = ?
        """, (upload_date, prop_id))
    
    conn.commit()
    conn.close()
    
    print(f"✅ CSV 導入完成！")
    print(f"  新增房源: {imported_count}")
    print(f"  已刪除房源: {len(deleted_ids)}")
    print(f"  總房源數: {len(new_ids)}")

@app.post("/api/import_data")
async def import_data(csv_filename: str):
    """
    導入 CSV 數據並創建新版本
    """
    try:
        import pandas as pd
        
        csv_path = os.path.join(os.path.dirname(__file__), "upload", csv_filename)
        
        if not os.path.exists(csv_path):
            return {
                "status": "error",
                "message": f"文件不存在: {csv_path}"
            }
        
        # 讀取 CSV
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        
        # 從文件名提取建築類型
        building_type = extract_building_type_from_filename(csv_filename)
        
        # 生成週次 ID
        week_id = get_week_id()
        upload_date = datetime.now().strftime("%Y-%m-%d")
        
        # 連接數據庫
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 記錄新版本
        cursor.execute("""
            INSERT OR REPLACE INTO versions (week_id, upload_date)
            VALUES (?, ?)
        """, (week_id, upload_date))
        
        # 獲取現有房源 ID
        cursor.execute("SELECT id FROM properties WHERE status = 'active'")
        existing_ids = {row[0] for row in cursor.fetchall()}
        
        # 處理新數據
        new_ids = set()
        for _, row in df.iterrows():
            try:
                # 提取數據
                title = str(row.get('標題', ''))
                address = str(row.get('地址', ''))
                rent = int(row.get('租金', 0))
                area = float(row.get('坪數', 0))
                room_type = str(row.get('房型', ''))
                floor = str(row.get('樓層', ''))
                latitude = float(row.get('緯度', 0))
                longitude = float(row.get('經度', 0))
                renovation_status = str(row.get('裝修狀態', 'unknown'))
                
                # 檢查是否已存在
                cursor.execute("""
                    SELECT id, first_published_date FROM properties 
                    WHERE address = ? AND rent_monthly = ?
                """, (address, rent))
                
                result = cursor.fetchone()
                
                if result:
                    # 已存在，更新狀態
                    prop_id = result[0]
                    first_published_date = result[1]
                    new_ids.add(prop_id)
                    
                    cursor.execute("""
                        UPDATE properties 
                        SET status = 'active', upload_week = ?, building_type = ?
                        WHERE id = ?
                    """, (week_id, building_type, prop_id))
                else:
                    # 新房源
                    first_published_date = datetime.now().strftime("%Y-%m-%d")
                    
                    cursor.execute("""
                        INSERT INTO properties 
                        (title, address, rent_monthly, area, room_type, floor, latitude, longitude, 
                         building_type, renovation_status, first_published_date, upload_week, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (title, address, rent, area, room_type, floor, latitude, longitude,
                          building_type, renovation_status, first_published_date, week_id))
                    
                    new_ids.add(cursor.lastrowid)
            
            except Exception as e:
                print(f"處理行失敗: {e}")
                continue
        
        # 標記已刪除的房源
        deleted_ids = existing_ids - new_ids
        for prop_id in deleted_ids:
            cursor.execute("""
                UPDATE properties 
                SET status = 'deleted', deleted_date = ?
                WHERE id = ?
            """, (upload_date, prop_id))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "week_id": week_id,
            "upload_date": upload_date,
            "new_properties": len(new_ids),
            "deleted_properties": len(deleted_ids),
            "message": f"成功導入數據。新增: {len(new_ids)}, 刪除: {len(deleted_ids)}"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

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
    """
    分析 API v4 - 支持版本查詢、留置時間著色和建築類型篩選
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 優先使用前端傳來的座標，否則使用默認座標
        if lat is not None and lng is not None and lat != 0 and lng != 0:
            query_lat = lat
            query_lon = lng
        else:
            # 使用默認座標（中和區中心）
            query_lat, query_lon = 25.0288, 121.4625
        
        # 查詢房源
        query = "SELECT * FROM properties WHERE status IN ('active', 'deleted')"
        params = []
        
        if week_id:
            # 如果指定週次，只查詢該週及之前的房源
            query += " AND upload_week <= ?"
            params.append(week_id)
        
        cursor.execute(query, params)
        all_properties = cursor.fetchall()
        
        # 獲取列名
        cursor.execute("PRAGMA table_info(properties)")
        columns = {row[1]: row[0] for row in cursor.fetchall()}
        
        # 篩選距離範圍內的房源
        filtered_properties = []
        for prop in all_properties:
            # 跳過沒有經緯度的房源
            if prop[columns['latitude']] is None or prop[columns['longitude']] is None:
                continue
            
            # 跳過座標異常的房源 (0,0)
            if prop[columns['latitude']] == 0.0 and prop[columns['longitude']] == 0.0:
                continue
            
            prop_dict = {
                'id': prop[columns['id']],
                'title': prop[columns['title']],
                'address': prop[columns['address']],
                'rent_monthly': prop[columns['rent_monthly']],
                'area': prop[columns['area']],
                'floor': prop[columns['floor']] if 'floor' in columns else '',
                'room_type': prop[columns['room_type']],
                'latitude': prop[columns['latitude']],
                'longitude': prop[columns['longitude']],
                'building_type': prop[columns['building_type']] if 'building_type' in columns else 'apartment',
                'renovation_status': prop[columns['renovation_status']],
                'first_published_date': prop[columns['first_published_date']],
                'upload_week': prop[columns['upload_week']],
                'status': prop[columns['status']]
            }
            
            # 計算距離
            distance = haversine_distance(query_lat, query_lon, prop_dict['latitude'], prop_dict['longitude'])
            
            if distance_min <= distance <= distance_max:
                # 計算留置週數
                weeks_since = calculate_weeks_since_published(prop_dict['first_published_date'])
                prop_dict['weeks_since_first_published'] = weeks_since
                prop_dict['distance'] = distance
                
                # 應用篩選條件
                if building_type and prop_dict['building_type'] != building_type:
                    continue
                if room_type and prop_dict['room_type'] != room_type:
                    continue
                
                filtered_properties.append(prop_dict)
        
        # 計算統計數據
        if filtered_properties:
            rents = [p['rent_monthly'] for p in filtered_properties if p['status'] == 'active']
            areas = [p['area'] for p in filtered_properties if p['status'] == 'active']
            
            summary = {
                'total_properties': len(filtered_properties),
                'active_properties': len([p for p in filtered_properties if p['status'] == 'active']),
                'deleted_properties': len([p for p in filtered_properties if p['status'] == 'deleted']),
                'new_properties': len([p for p in filtered_properties if p['weeks_since_first_published'] == 0]),
                'avg_rent_all': sum(rents) / len(rents) if rents else 0,
                'min_rent': min(rents) if rents else 0,
                'max_rent': max(rents) if rents else 0,
                'avg_area': sum(areas) / len(areas) if areas else 0,
            }
        else:
            summary = {
                'total_properties': 0,
                'active_properties': 0,
                'deleted_properties': 0,
                'new_properties': 0,
                'avg_rent_all': 0,
                'min_rent': 0,
                'max_rent': 0,
                'avg_area': 0,
            }
        
        # 房型分析
        room_type_analysis = {}
        for prop in filtered_properties:
            if prop['status'] == 'active':
                rt = prop['room_type']
                room_type_analysis[rt] = room_type_analysis.get(rt, 0) + 1
        
        room_type_analysis = [
            {'room_type': k, 'count': v}
            for k, v in sorted(room_type_analysis.items(), key=lambda x: x[1], reverse=True)
        ]
        
        conn.close()
        
        return {
            'status': 'success',
            'query': {
                'address': address,
                'coordinates': {'latitude': query_lat, 'longitude': query_lon},
                'distance_range': {'min': distance_min, 'max': distance_max},
                'week_id': week_id or 'current'
            },
            'summary': summary,
            'properties': filtered_properties,
            'room_type_analysis': room_type_analysis
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

# ============ 管理員 API ============

# 管理員密碼（MVP 測試用）
ADMIN_PASSWORD = "1234"

class ResetRequest(BaseModel):
    password: str
    confirm: bool = False

@app.post("/api/admin/reset-database")
async def reset_database(request: ResetRequest):
    """
    清空數據庫 API（需要密碼驗證）
    
    使用方法：
    POST /api/admin/reset-database
    Body: {"password": "1234", "confirm": true}
    """
    # 驗證密碼
    if request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="密碼錯誤")
    
    # 驗證確認參數
    if not request.confirm:
        raise HTTPException(status_code=400, detail="請設置 confirm=true 以確認清空操作")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 統計刪除前的數據
        cursor.execute("SELECT COUNT(*) FROM properties")
        properties_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM versions")
        versions_count = cursor.fetchone()[0]
        
        # 清空所有表
        cursor.execute("DELETE FROM properties")
        cursor.execute("DELETE FROM versions")
        
        # 重置自增 ID
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='properties'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='versions'")
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "數據庫已清空",
            "deleted": {
                "properties": properties_count,
                "versions": versions_count
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空失敗: {str(e)}")

@app.get("/api/admin/database-status")
async def database_status():
    """
    查看數據庫狀態（不需要密碼）
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 統計房源數量
        cursor.execute("SELECT COUNT(*) FROM properties")
        total_properties = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE status='active'")
        active_properties = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE status='deleted'")
        deleted_properties = cursor.fetchone()[0]
        
        # 統計版本數量
        cursor.execute("SELECT COUNT(*) FROM versions")
        versions_count = cursor.fetchone()[0]
        
        # 獲取所有版本
        cursor.execute("SELECT week_id, upload_date FROM versions ORDER BY week_id DESC")
        versions = [{"week_id": row[0], "upload_date": row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "status": "success",
            "database": {
                "total_properties": total_properties,
                "active_properties": active_properties,
                "deleted_properties": deleted_properties,
                "versions_count": versions_count,
                "versions": versions
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")

# ============ 靜態文件 ============

# 挂載靜態文件（必須在所有 API 路由之後）
app.mount("/", StaticFiles(directory=os.path.dirname(__file__), html=True), name="static")

# ============ 啟動 ============

if __name__ == "__main__":
    init_database()
    
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
