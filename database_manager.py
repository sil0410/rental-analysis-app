#!/usr/bin/env python3
"""
租賃分析系統 - 數據庫管理工具
用於在 NAS 上管理數據庫、導入 CSV、備份等操作
"""

import sqlite3
import os
import sys
import json
from datetime import datetime
from pathlib import Path

class DatabaseManager:
    """數據庫管理類"""
    
    def __init__(self, db_path="/app/data/rental.db"):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """連接到數據庫"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            print(f"✅ 已連接到數據庫: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ 連接失敗: {e}")
            return False
    
    def close(self):
        """關閉數據庫連接"""
        if self.conn:
            self.conn.close()
            print("✅ 數據庫連接已關閉")
    
    def get_statistics(self):
        """獲取數據庫統計信息"""
        if not self.conn:
            print("❌ 未連接到數據庫")
            return None
        
        try:
            cursor = self.conn.cursor()
            
            # 房源統計
            cursor.execute("SELECT COUNT(*) FROM properties WHERE status = 'active'")
            active_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM properties WHERE status = 'deleted'")
            deleted_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM properties")
            total_count = cursor.fetchone()[0]
            
            # 租金統計
            cursor.execute("SELECT MIN(rent_monthly), MAX(rent_monthly), AVG(rent_monthly) FROM properties WHERE rent_monthly > 0")
            min_rent, max_rent, avg_rent = cursor.fetchone()
            
            # 房型分布
            cursor.execute("SELECT room_type, COUNT(*) FROM properties WHERE status = 'active' GROUP BY room_type ORDER BY COUNT(*) DESC LIMIT 5")
            room_types = cursor.fetchall()
            
            stats = {
                'active_properties': active_count,
                'deleted_properties': deleted_count,
                'total_properties': total_count,
                'min_rent': min_rent or 0,
                'max_rent': max_rent or 0,
                'avg_rent': avg_rent or 0,
                'room_types': [{'type': rt[0], 'count': rt[1]} for rt in room_types]
            }
            
            return stats
        except Exception as e:
            print(f"❌ 獲取統計信息失敗: {e}")
            return None
    
    def print_statistics(self):
        """打印統計信息"""
        stats = self.get_statistics()
        if not stats:
            return
        
        print("\n" + "="*50)
        print("📊 數據庫統計信息")
        print("="*50)
        print(f"活躍房源: {stats['active_properties']}")
        print(f"已刪除房源: {stats['deleted_properties']}")
        print(f"總房源數: {stats['total_properties']}")
        print(f"\n💰 租金統計:")
        print(f"  最低: ${stats['min_rent']}")
        print(f"  最高: ${stats['max_rent']}")
        print(f"  平均: ${stats['avg_rent']:.0f}")
        print(f"\n📋 房型分布 (前 5):")
        for rt in stats['room_types']:
            print(f"  {rt['type']}: {rt['count']}")
        print("="*50 + "\n")
    
    def backup_database(self, backup_dir="/app/data/backups"):
        """備份數據庫"""
        try:
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"rental_{timestamp}.db")
            
            if self.conn:
                self.conn.close()
            
            # 複製數據庫文件
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            self.connect()
            print(f"✅ 數據庫已備份到: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ 備份失敗: {e}")
            return None
    
    def clear_database(self):
        """清空數據庫（謹慎使用）"""
        if not self.conn:
            print("❌ 未連接到數據庫")
            return False
        
        try:
            confirm = input("⚠️  確定要清空所有數據嗎？(yes/no): ")
            if confirm.lower() != 'yes':
                print("❌ 已取消操作")
                return False
            
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM properties")
            cursor.execute("DELETE FROM versions")
            self.conn.commit()
            
            print("✅ 數據庫已清空")
            return True
        except Exception as e:
            print(f"❌ 清空失敗: {e}")
            return False
    
    def export_to_json(self, output_file="/app/data/export.json"):
        """將數據庫導出為 JSON"""
        if not self.conn:
            print("❌ 未連接到數據庫")
            return False
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM properties WHERE status = 'active'")
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 已導出 {len(data)} 條房源到: {output_file}")
            return True
        except Exception as e:
            print(f"❌ 導出失敗: {e}")
            return False

def main():
    """主函數"""
    print("🏠 租賃分析系統 - 數據庫管理工具")
    print("="*50)
    
    # 檢查數據庫文件
    db_path = "/app/data/rental.db"
    if not os.path.exists(db_path):
        print(f"⚠️  數據庫文件不存在: {db_path}")
        print("💡 提示: 系統首次啟動時會自動創建數據庫")
    
    manager = DatabaseManager(db_path)
    
    if not manager.connect():
        sys.exit(1)
    
    # 顯示菜單
    while True:
        print("\n📋 請選擇操作:")
        print("1. 查看統計信息")
        print("2. 備份數據庫")
        print("3. 導出為 JSON")
        print("4. 清空數據庫")
        print("5. 退出")
        
        choice = input("\n請輸入選項 (1-5): ").strip()
        
        if choice == '1':
            manager.print_statistics()
        elif choice == '2':
            manager.backup_database()
        elif choice == '3':
            manager.export_to_json()
        elif choice == '4':
            manager.clear_database()
        elif choice == '5':
            print("👋 再見！")
            break
        else:
            print("❌ 無效選項，請重試")
    
    manager.close()

if __name__ == "__main__":
    main()
