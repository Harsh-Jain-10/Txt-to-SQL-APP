import os
import psycopg2
from dotenv import load_dotenv

# 1. Load database credentials from .env
load_dotenv()

user = os.getenv("DB_USER")
pwd = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")
db = os.getenv("DB_NAME", "digital_store")

# 2. Test connection and query row count
try:
    conn = psycopg2.connect(
        dbname=db,
        user=user,
        password=pwd,
        host=host,
        port=port
    )
    cursor = conn.cursor()
    # Verify table existence and count total records
    cursor.execute("SELECT COUNT(*) FROM digital_store_sales;")
    count = cursor.fetchone()[0]
    print(f"Connection Successful! Total rows found: {count}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Connection error: {e}")