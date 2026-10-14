import os
import psycopg2
from dotenv import load_dotenv
from groq import Groq

# Load environment variables and initialize Groq client
load_dotenv()
client = Groq(api_key=os.getenv("LLM_API_KEY"))

def ask_sql(question: str):
    # Minimal schema context and instructions for PostgreSQL
    prompt = (
        "You are a PostgreSQL expert. Table: digital_store_sales. "
        "Columns: order_id, customer_id, customer_city, customer_state, product_id, "
        "product_category_name, payment_type, payment_installments, payment_value, "
        "price, freight_value, order_purchase_timestamp, year_of_purchase, order_status. "
        "Return ONLY raw SQL with a default LIMIT 5, no markdown backticks. "
        f"Question: {question}"
    )

    # Call Groq (trying llama-3.3-70b-versatile, llama-3.1-8b-instant, or active model)
    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
            )
            break
        except Exception:
            continue

    sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    print(f"Generated SQL: {sql}")

    # Connect via psycopg2, execute query, and print rows
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
    ask_sql("Show the top 5 cities with the highest number of orders")