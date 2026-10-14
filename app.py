import os
import streamlit as st
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from groq import Groq

# 1. Config & Groq Client setup
load_dotenv()
st.set_page_config(page_title="Text to SQL Analytics", layout="wide")
st.title("⚡ Text to SQL Analytics")
st.markdown("Transform natural language questions into PostgreSQL queries and interactive charts.")

client = Groq(api_key=os.getenv("LLM_API_KEY"))

# 2. User Input
question = st.text_input(
    "Enter your business question:",
    value="Show the top 5 cities with the highest number of orders"
)
run_btn = st.button("Generate & Run", type="primary")

# 3. Query Execution & Visualization
if run_btn and question:
    prompt = (
        "You are a PostgreSQL expert. Table: digital_store_sales. "
        "Columns: order_id, customer_city, product_category_name, price, payment_value, order_status. "
        "Return ONLY raw SQL without markdown or backticks. Always add LIMIT 5 unless specified. "
        f"Question: {question}"
    )

    try:
        # Call Groq with preferred model and fallback
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
            try:
                res = client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
                )
                break
            except Exception:
                continue

        sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

        with st.expander("🔍 Generated SQL Query", expanded=True):
            st.code(sql, language="sql")

        # Database connection & execution
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432")
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        conn.close()

        df = pd.DataFrame(rows, columns=columns)

        # High-impact Metrics & Structured Table
        st.metric(label="Total Rows Returned", value=len(df))
        st.dataframe(df, use_container_width=True)

        # Auto-charting: render bar chart for 2-column results
        if len(df.columns) == 2:
            st.subheader("📊 Interactive Visualization")
            chart_df = df.copy()
            chart_df[chart_df.columns[1]] = pd.to_numeric(chart_df[chart_df.columns[1]], errors="coerce")
            st.bar_chart(chart_df.set_index(chart_df.columns[0]))

    except Exception as e:
        st.error(f"Error executing query: {e}")
