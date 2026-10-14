import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("DB_USER")
pwd = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")
db = os.getenv("DB_NAME", "digital_store")

try:
    conn = psycopg2.connect(
        dbname=db,
        user=user,
        password=pwd,
        host=host,
        port=port
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM digital_store_sales;")
    count = cursor.fetchone()[0]
    print(f"Connection Successful! Total rows found: {count}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Connection error: {e}")