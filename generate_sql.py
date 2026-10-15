import os
import psycopg2
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

    # 5. Connect to PostgreSQL via psycopg2, execute query, and print structured rows
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432")
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            print(row)
    conn.close()

if __name__ == "__main__":
    # Test query
    ask_sql("Show the top 5 cities with the highest number of orders")