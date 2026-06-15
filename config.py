# config.py - Cấu hình cho SQL Server

# Thông tin kết nối SQL Server
DB_CONFIG = {
    'server': 'DESKTOP-UU5A7B5',  # hoặc 'DESKTOP-XXXX\SQLEXPRESS'
    'database': 'BI_final',
    'driver': 'ODBC Driver 17 for SQL Server',  # hoặc 'SQL Server Native Client 11.0'
    'trusted_connection': 'yes'  # dùng Windows Authentication
}

# Hoặc dùng SQL Authentication:
# DB_CONFIG = {
#     'server': 'localhost',
#     'database': 'EcomSmart_DW',
#     'username': 'sa',
#     'password': 'your_password',
#     'driver': 'ODBC Driver 17 for SQL Server'
# }

DATA_PATH = "D:/học kỳ 2 năm 4/quản trị nghiệp vụ thông minh/Project BI Final (new)/BI_dataset(new)/"  # SỬA ĐƯỜNG DẪN NÀY

# Mapping cho phân nhóm tuổi
AGE_GROUPS = {
    (0, 25): '18-25',
    (26, 35): '26-35',
    (36, 50): '36-50',
    (51, 200): '51+'
}
