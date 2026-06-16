import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import urllib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Import config
from config import DB_CONFIG, DATA_PATH, AGE_GROUPS

# ============================================
# 1. KẾT NỐI SQL SERVER
# ============================================
def create_sql_server_connection():
    """Tạo kết nối đến SQL Server"""
    try:
        # Cách 1: Dùng Windows Authentication
        conn_str = (
            f"mssql+pyodbc://@{DB_CONFIG['server']}/{DB_CONFIG['database']}"
            f"?driver={DB_CONFIG['driver']}&trusted_connection=yes"
        )
        
        # Cách 2: Dùng SQL Authentication (bỏ comment nếu cần)
        # conn_str = (
        #     f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}"
        #     f"@{DB_CONFIG['server']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver']}"
        # )
        
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
        print("\n🔧 Cách khắc phục:")
        print("1. Kiểm tra SQL Server đã bật chưa? (Services -> SQL Server)")
        print("2. Kiểm tra tên server trong SSMS (kết nối vào xem)")
        print("3. Cài ODBC Driver 17: https://go.microsoft.com/fwlink/?linkid=2249006")
        return None

# ============================================
# 2. EXTRACT - Đọc dữ liệu từ CSV
# ============================================
def extract_data():
    """Đọc dữ liệu từ các file CSV"""
    print("\n📂 Bắt đầu Extract dữ liệu...")
    
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
        print(f"   ✓ inventory_items: {len(inventory_items_df):,} dòng")
        print(f"   ✓ distribution_centers: {len(distribution_centers_df):,} dòng")
        
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
        print("   Hãy kiểm tra lại đường dẫn trong file config.py")
        return None

# ============================================
# 3. TRANSFORM - Xử lý và biến đổi dữ liệu
# ============================================
def get_age_group(age):
    """Phân nhóm tuổi"""
    if pd.isna(age):
        return 'Unknown'
    elif age <= 25:
        return '18-25'
    elif age <= 35:
        return '26-35'
    elif age <= 50:
        return '36-50'
    else:
        return '51+'

def transform_data(dfs):
    """Biến đổi dữ liệu thành các bảng Dimension và Fact"""
    print("\n🔄 Bắt đầu Transform dữ liệu...")
    
    # Lọc đơn hàng hoàn thành
    orders_complete = dfs['orders'][dfs['orders']['status'] == 'Complete'].copy()
    order_items_complete = dfs['order_items'][dfs['order_items']['status'] == 'Complete'].copy()
    print(f"   ✓ Đơn hàng Complete: {len(orders_complete):,} (trên {len(dfs['orders']):,})")
    
    # ===== 3.1 DimUser =====
    dim_user = dfs['users'].copy()
    dim_user['age_group'] = dim_user['age'].apply(get_age_group)
    dim_user['full_name'] = dim_user['first_name'] + ' ' + dim_user['last_name']
    dim_user = dim_user[['id', 'full_name', 'age', 'age_group', 'gender', 
                         'traffic_source', 'created_at']].copy()
    dim_user.columns = ['user_id', 'full_name', 'age', 'age_group', 
                        'gender', 'traffic_source', 'user_created_at']
    print(f"   ✓ DimUser: {len(dim_user):,} dòng")
    
    # ===== 3.2 DimProduct =====
    dim_product = dfs['products'][['id', 'name', 'category', 'brand', 
                                    'department', 'retail_price', 'cost']].copy()
    dim_product.columns = ['product_id', 'product_name', 'category', 
                           'brand', 'department', 'retail_price', 'cost']
    print(f"   ✓ DimProduct: {len(dim_product):,} dòng")
    
    # ===== 3.3 DimRegion =====
    dim_region = dfs['users'][['state', 'city']].drop_duplicates().copy()
    dim_region['country'] = 'USA'
    dim_region = dim_region.reset_index(drop=True)
    dim_region.index = dim_region.index + 1
    dim_region.index.name = 'region_key'
    dim_region = dim_region.reset_index()
    
    # Mapping state-city to region_key
    state_city_to_key = dict(zip(
        zip(dim_region['state'], dim_region['city']), 
        dim_region['region_key']
    ))
    print(f"   ✓ DimRegion: {len(dim_region):,} dòng")
    
    # ===== 3.4 DimTime =====
    all_dates = pd.to_datetime(order_items_complete['created_at'], format='mixed', errors='coerce').dt.date.unique()
    date_range = pd.DataFrame({'full_date': sorted(all_dates)})
    
    def create_dim_time(df):
        df = df.copy()
        df['full_date'] = pd.to_datetime(df['full_date'])
        df['time_key'] = df['full_date'].dt.strftime('%Y%m%d').astype(int)
        df['year'] = df['full_date'].dt.year
        df['quarter'] = df['full_date'].dt.quarter
        df['month'] = df['full_date'].dt.month
        df['month_name'] = df['full_date'].dt.strftime('%B')
        df['week_of_year'] = df['full_date'].dt.isocalendar().week
        df['day_of_week'] = df['full_date'].dt.dayofweek + 1
        df['day_of_week_name'] = df['full_date'].dt.strftime('%A')
        df['day_of_month'] = df['full_date'].dt.day
        df['is_weekend'] = df['day_of_week'].isin([6, 7])
        return df[['time_key', 'full_date', 'year', 'quarter', 'month',
                   'month_name', 'week_of_year', 'day_of_week',
                   'day_of_week_name', 'day_of_month', 'is_weekend']]
    
    dim_time = create_dim_time(date_range)
    date_to_key = dict(zip(dim_time['full_date'], dim_time['time_key']))
    print(f"   ✓ DimTime: {len(dim_time):,} dòng")
    

    # ===== 3.5 FactOrderItems (CÁCH ĐƠN GIẢN NHẤT) =====
    # Mapping keys
    product_id_to_key = dict(zip(dim_product['product_id'], dim_product.index + 1))
    user_id_to_key = dict(zip(dim_user['user_id'], dim_user.index + 1))
    
    # Merge đơn giản: order_items + orders
    fact = order_items_complete.merge(
        orders_complete[['order_id', 'user_id']], 
        on='order_id', 
        how='inner'
    )
    
    # Gán region_key mặc định = 1 cho tất cả
    fact['region_key'] = 1
    
    # Xử lý thời gian
    if 'created_at' in fact.columns:
        fact['created_at_clean'] = fact['created_at'].astype(str).str.replace(' UTC', '')
    else:
        # Nếu có nhiều cột created_at, lấy cột đầu tiên
        created_col = [col for col in fact.columns if 'created_at' in col][0]
        fact['created_at_clean'] = fact[created_col].astype(str).str.replace(' UTC', '')
    
    fact['order_date'] = pd.to_datetime(fact['created_at_clean'], errors='coerce').dt.date
    fact['time_key'] = fact['order_date'].map(date_to_key)
    fact['product_key'] = fact['product_id'].map(product_id_to_key)
    
    # Lấy user_id - có thể là 'user_id', 'user_id_x', hoặc 'user_id_y'
    user_col = [col for col in fact.columns if 'user_id' in col][0]
    fact['user_key'] = fact[user_col].map(user_id_to_key)
    
    # Chọn cột cho fact table
    dim_fact = fact[['id', 'order_id', 'user_key', 'product_key', 
                     'region_key', 'time_key', 'sale_price', 'status']].copy()
    dim_fact['quantity'] = 1
    dim_fact = dim_fact.rename(columns={'id': 'order_item_id'})
    
    # Loại bỏ null
    before = len(dim_fact)
    dim_fact = dim_fact.dropna(subset=['user_key', 'product_key', 'time_key'])
    after = len(dim_fact)
    print(f"   ✓ FactOrderItems: {after:,} dòng (đã loại {before - after:,} dòng null)")
    
    return {
        'dim_user': dim_user,
        'dim_product': dim_product,
        'dim_region': dim_region,
        'dim_time': dim_time,
        'fact_order_items': dim_fact
    }

# ============================================
# 4. LOAD - Ghi vào SQL Server
# ============================================
def load_data(engine, tables):
    """Load dữ liệu vào SQL Server"""
    print("\n💾 Bắt đầu Load dữ liệu vào SQL Server...")
    
    try:
        # Tạo bảng DimUser (IDENTITY tự động tăng)
        tables['dim_user'].to_sql('DimUser', engine, if_exists='replace', 
                                   index=True, index_label='UserKey')
        print("   ✓ Đã load DimUser")
        
        # DimProduct
        tables['dim_product'].to_sql('DimProduct', engine, if_exists='replace',
                                      index=True, index_label='ProductKey')
        print("   ✓ Đã load DimProduct")
        
        # DimRegion
        tables['dim_region'].to_sql('DimRegion', engine, if_exists='replace', 
                                     index=False)
        print("   ✓ Đã load DimRegion")
        
        # DimTime
        tables['dim_time'].to_sql('DimTime', engine, if_exists='replace', 
                                   index=False)
        print("   ✓ Đã load DimTime")
        
        # FactOrderItems
        tables['fact_order_items'].to_sql('FactOrderItems', engine, 
                                           if_exists='replace', index=False)
        print("   ✓ Đã load FactOrderItems")
        
        print("\n✅ ETL HOÀN TẤT!")
        
        # Kiểm tra kết quả
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM FactOrderItems"))
            count = result.fetchone()[0]
            print(f"\n📊 Kiểm tra: FactOrderItems có {count:,} bản ghi")
        
        return True
        
    except Exception as e:
        print(f"❌ Lỗi khi load dữ liệu: {e}")
        return False

# ============================================
# 5. MAIN - Chạy toàn bộ ETL
# ============================================
def main():
    print("="*60)
    print("🚀 ETL SYSTEM FOR ECOM SMART")
    print("="*60)
    
    # Kết nối database
    engine = create_sql_server_connection()
    if engine is None:
        return
    
    # Extract
    dfs = extract_data()
    if dfs is None:
        return
    
    # Transform
    tables = transform_data(dfs)
    
    # Load
    success = load_data(engine, tables)
    
    if success:
        print("\n🎉 HOÀN THÀNH! Bạn có thể mở SSMS để kiểm tra dữ liệu.")
    else:
        print("\n⚠️ CÓ LỖI XẢY RA. Hãy kiểm tra log phía trên.")

if __name__ == "__main__":
    main()
