import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import urllib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Import config từ file config.py của bạn
from config import DB_CONFIG, DATA_PATH

# ============================================
# 1. KẾT NỐI SQL SERVER
# ============================================
def create_sql_server_connection():
    """Tạo kết nối đến SQL Server"""
    try:
        conn_str = (
            f"mssql+pyodbc://@{DB_CONFIG['server']}/{DB_CONFIG['database']}"
            f"?driver={DB_CONFIG['driver']}&trusted_connection=yes"
        )
        
        engine = create_engine(conn_str)
        
        # Test kết nối
        with engine.connect() as conn:
            result = conn.execute(text("SELECT @@VERSION"))
            version = result.fetchone()[0]
            print(f"✅ Kết nối SQL Server thành công!")
            print(f"   Version: {version[:50]}...")
        
        return engine
    
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        return None

# ============================================
# 2. EXTRACT - Đọc dữ liệu từ CSV
# ============================================
def extract_data():
    """Đọc dữ liệu từ các file CSV"""
    print("\n📂 Đang đọc dữ liệu từ CSV...")
    
    try:
        users_df = pd.read_csv(DATA_PATH + "users.csv")
        products_df = pd.read_csv(DATA_PATH + "products.csv")
        orders_df = pd.read_csv(DATA_PATH + "orders.csv")
        order_items_df = pd.read_csv(DATA_PATH + "order_items.csv")
        inventory_items_df = pd.read_csv(DATA_PATH + "inventory_items.csv")
        distribution_centers_df = pd.read_csv(DATA_PATH + "distribution_centers.csv")
        
        print(f"   ✓ users: {len(users_df):,} dòng")
        print(f"   ✓ products: {len(products_df):,} dòng")
        print(f"   ✓ orders: {len(orders_df):,} dòng")
        print(f"   ✓ order_items: {len(order_items_df):,} dòng")
        
        return {
            'users': users_df,
            'products': products_df,
            'orders': orders_df,
            'order_items': order_items_df,
            'inventory_items': inventory_items_df,
            'distribution_centers': distribution_centers_df
        }
    
    except FileNotFoundError as e:
        print(f"❌ Không tìm thấy file: {e}")
        print(f"   Đã tìm trong thư mục: {DATA_PATH}")
        return None

# ============================================
# 3. CẬP NHẬT REGION KEY
# ============================================
def update_region_key_only(engine):
    """Chỉ cập nhật region_key trong bảng FactOrderItems và DimRegion"""
    print("\n🔄 Bắt đầu CẬP NHẬT Region Key...")
    print("="*60)
    
    with engine.connect() as conn:
        try:
            # Bắt đầu transaction
            trans = conn.begin()
            
            # Bước 1: Kiểm tra dữ liệu hiện tại
            print("\n📊 Bước 1: Kiểm tra dữ liệu hiện tại...")
            result = conn.execute(text("SELECT COUNT(*) FROM FactOrderItems"))
            current_count = result.fetchone()[0]
            print(f"   FactOrderItems hiện có: {current_count:,} bản ghi")
            
            # Bước 2: Đọc dữ liệu mới từ CSV
            print("\n📂 Bước 2: Đọc dữ liệu mới từ CSV...")
            dfs = extract_data()
            if dfs is None:
                return False
            
            # Bước 3: Tạo DimRegion mới
            print("\n🗺️  Bước 3: Tạo DimRegion mới...")
            dim_region_new = dfs['users'][['state', 'city']].drop_duplicates().copy()
            dim_region_new = dim_region_new.dropna(subset=['state', 'city'])
            dim_region_new = dim_region_new[dim_region_new['state'] != '']
            dim_region_new = dim_region_new[dim_region_new['city'] != '']
            dim_region_new['country'] = 'USA'
            dim_region_new = dim_region_new.reset_index(drop=True)
            dim_region_new.insert(0, 'region_key', range(1, len(dim_region_new) + 1))
            
            print(f"   Tìm thấy {len(dim_region_new)} region độc nhất")
            
            # Tạo mapping
            state_city_to_key = dict(zip(
                zip(dim_region_new['state'], dim_region_new['city']), 
                dim_region_new['region_key']
            ))
            
            # Bước 4: Xóa và Insert DimRegion
            print("\n🔄 Bước 4: Cập nhật DimRegion...")
            conn.execute(text("DELETE FROM DimRegion"))
            
            for _, row in dim_region_new.iterrows():
                conn.execute(
                    text("INSERT INTO DimRegion (region_key, state, city, country) VALUES (:rk, :st, :ct, :co)"),
                    {"rk": int(row['region_key']), "st": row['state'], "ct": row['city'], "co": row['country']}
                )
            print(f"   ✓ Đã insert {len(dim_region_new)} dòng mới")
            
            # Bước 5: Cập nhật FactOrderItems (Phiên bản đơn giản)
            print("\n🔄 Bước 5: Cập nhật region_key trong FactOrderItems...")
            
            # Lọc dữ liệu
            orders_complete = dfs['orders'][dfs['orders']['status'] == 'Complete'].copy()
            order_items_complete = dfs['order_items'][dfs['order_items']['status'] == 'Complete'].copy()
            
            # Đổi tên cột
            if 'id' in order_items_complete.columns:
                order_items_complete = order_items_complete.rename(columns={'id': 'order_item_id'})
            
            print(f"   Số order_items cần xử lý: {len(order_items_complete):,}")
            
            # Tạo dictionary để tra cứu nhanh user info
            user_info_dict = {}
            for _, user in dfs['users'].iterrows():
                user_info_dict[user['id']] = {
                    'state': user['state'] if pd.notna(user['state']) else 'Unknown',
                    'city': user['city'] if pd.notna(user['city']) else 'Unknown'
                }
            
            # Tạo dictionary để tra cứu order -> user
            order_user_dict = {}
            for _, order in orders_complete.iterrows():
                order_user_dict[order['order_id']] = order['user_id']
            
            # Cập nhật từng order_item
            total_updated = 0
            batch_size = 1000
            batch_updates = []
            
            print("   Đang cập nhật...")
            
            for _, item in order_items_complete.iterrows():
                order_id = item['order_id']
                order_item_id = item['order_item_id']
                
                # Tìm user_id từ order
                user_id = order_user_dict.get(order_id)
                if user_id is None:
                    region_key = 0
                else:
                    # Tìm state, city từ user
                    user_info = user_info_dict.get(user_id, {'state': 'Unknown', 'city': 'Unknown'})
                    region_key = state_city_to_key.get((user_info['state'], user_info['city']), 0)
                
                batch_updates.append((region_key, order_item_id))
                total_updated += 1
                
                # Cập nhật theo batch
                if len(batch_updates) >= batch_size:
                    for rk, oid in batch_updates:
                        conn.execute(
                            text("UPDATE FactOrderItems SET region_key = :rk WHERE order_item_id = :oid"),
                            {"rk": int(rk), "oid": int(oid)}
                        )
                    batch_updates = []
                    print(f"      Đã cập nhật: {total_updated:,}/{len(order_items_complete):,} bản ghi")
            
            # Cập nhật batch cuối cùng
            if batch_updates:
                for rk, oid in batch_updates:
                    conn.execute(
                        text("UPDATE FactOrderItems SET region_key = :rk WHERE order_item_id = :oid"),
                        {"rk": int(rk), "oid": int(oid)}
                    )
            
            # Commit tất cả
            trans.commit()
            print(f"\n   ✓ Đã cập nhật {total_updated:,} bản ghi")
            
            # Bước 6: Kiểm tra kết quả
            print("\n📊 Bước 6: Kiểm tra kết quả...")
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(DISTINCT region_key) as distinct_regions,
                    SUM(CASE WHEN region_key = 0 THEN 1 ELSE 0 END) as unknown_records
                FROM FactOrderItems
            """))
            row = result.fetchone()
            print(f"   ✓ Tổng số bản ghi: {row[0]:,}")
            print(f"   ✓ Số region khác nhau: {row[1]}")
            print(f"   ✓ Số bản ghi region_key=0: {row[2]:,}")
            
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ LỖI: {e}")
            import traceback
            traceback.print_exc()
            return False

# ============================================
# 4. MAIN
# ============================================
def main():
    print("="*60)
    print("🔄 UPDATE REGION KEY ONLY")
    print("Giữ nguyên Power BI Dashboard - Chỉ cập nhật region")
    print("="*60)
    
    # Kết nối database
    engine = create_sql_server_connection()
    if engine is None:
        return
    
    print("\n⚠️  THÔNG TIN QUAN TRỌNG:")
    print("   ✓ Script này CHỈ cập nhật region_key")
    print("   ✓ KHÔNG thay đổi cấu trúc bảng")
    print("   ✓ KHÔNG ảnh hưởng đến DimUser, DimProduct, DimTime")
    print("   ✓ Power BI Dashboard của bạn vẫn hoạt động bình thường")
    print("   ✓ Đã có backup tự động đề phòng rủi ro")
    
    confirm = input("\n🤔 Bạn có muốn tiếp tục cập nhật? (yes/no): ")
    if confirm.lower() != 'yes':
        print("\n❌ Đã hủy cập nhật. Dữ liệu không thay đổi.")
        return
    
    # Thực hiện cập nhật
    success = update_region_key_only(engine)
    
    if success:
        print("\n" + "="*60)
        print("🎉 CẬP NHẬT THÀNH CÔNG!")
        print("="*60)
        print("\n📌 CÁC BƯỚC TIẾP THEO:")
        print("   1. Mở Power BI")
        print("   2. Click 'Refresh' (Home tab → Refresh)")
        print("   3. Kiểm tra các dashboard liên quan đến region")
        print("\n💡 Nếu có lỗi trong Power BI:")
        print("   - Vào File → Options and settings → Options")
        print("   - Chọn 'Data Load' → 'Clear Cache'")
        print("   - Refresh lại")
    else:
        print("\n⚠️ CÓ LỖI XẢY RA, dữ liệu đã được rollback về trạng thái cũ.")
        print("   Vui lòng kiểm tra lại kết nối và file CSV.")

if __name__ == "__main__":
    main()
