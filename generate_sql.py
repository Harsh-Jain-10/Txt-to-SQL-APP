import os
try:
    import psycopg2
except Exception:
    psycopg2 = None
import pg8000.dbapi
from dotenv import load_dotenv
from groq import Groq

# 1. Load database and LLM credentials from .env
load_dotenv()
client = Groq(api_key=os.getenv("LLM_API_KEY"))

def ask_sql(question: str):
    # 2. Schema context & instructions prompting LLM for raw SQL
    prompt = (
        "You are a PostgreSQL expert. Table: digital_store_sales. "
        "Columns: order_id, customer_id, customer_city, customer_state, product_id, "
        "product_category_name, payment_type, payment_installments, payment_value, "
        "price, freight_value, order_purchase_timestamp, year_of_purchase, order_status. "
        "Return ONLY raw SQL with a default LIMIT 5, no markdown backticks. "
        f"Question: {question}"
    )

    # 3. Request SQL generation from Groq (llama-3.3-70b-versatile with fallback)
    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
            )
            break
        except Exception:
            continue

    # 4. Strip markdown formatting to get clean executable SQL
    sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    print(f"Generated SQL: {sql}\nResults:")

    # 5. Connect to PostgreSQL and print structured rows
    db_name = os.getenv("DB_NAME", "digital_store")
    db_user = os.getenv("DB_USER")
    db_pwd = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))

    if psycopg2 is not None:
        try:
            conn = psycopg2.connect(dbname=db_name, user=db_user, password=db_pwd, host=db_host, port=db_port)
        except Exception:
            conn = pg8000.dbapi.connect(database=db_name, user=db_user, password=db_pwd, host=db_host, port=db_port)
    else:
        conn = pg8000.dbapi.connect(database=db_name, user=db_user, password=db_pwd, host=db_host, port=db_port)

    cur = conn.cursor()
    try:
        cur.execute(sql)
        for row in cur.fetchall():
            print(row)
    finally:
        cur.close()
    conn.close()

if __name__ == "__main__":
    # Test query
    ask_sql("Show the top 5 cities with the highest number of orders")