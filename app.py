import os
import streamlit as st
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from groq import Groq

# 1. Page Configuration & Environment Setup
load_dotenv()
st.set_page_config(page_title="Text to SQL Analytics", layout="wide")
st.title("⚡ Text to SQL Analytics Dashboard")
st.markdown("Transform natural language questions into PostgreSQL queries, structured tables, and interactive charts.")

# Initialize the Groq LLM client
client = Groq(api_key=os.getenv("LLM_API_KEY"))

# 2. User Input: capture the business question from the user
question = st.text_input(
    "Enter your business question:",
    value="Show the top 5 cities with the highest number of orders"
)
run_btn = st.button("Generate & Run", type="primary")

# 3. Query Execution, Table Building, and Chart Visualization
if run_btn and question:
    # Minimal schema context for LLM prompt
    prompt = (
        "You are a PostgreSQL expert. Table: digital_store_sales. "
        "Columns: order_id, customer_city, product_category_name, price, payment_value, order_status. "
        "Return ONLY raw SQL without markdown or backticks. Always add LIMIT 5 unless specified. "
        f"Question: {question}"
    )

    try:
        # Step A: Generate SQL from natural language using Groq LLM (with fallback support)
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
            try:
                res = client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
                )
                break
            except Exception:
                continue

        # Clean markdown/backtick tags from LLM response
        sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

        # Step B: Display the generated SQL in an expandable code block
        with st.expander("🔍 Generated SQL Query", expanded=True):
            st.code(sql, language="sql")

        # Step C: Connect to PostgreSQL and execute the query
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432")
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        conn.close()

        # Step D [Structured Output]: Convert raw SQL rows and column headers into a pandas DataFrame
        df = pd.DataFrame(rows, columns=columns)

        # Step E [Metrics & Table Display]: Render total row count and the interactive data table
        st.metric(label="Total Rows Returned", value=len(df))
        st.dataframe(df, use_container_width=True)

        # Step F [Visualization & Charting]: Auto-render interactive bar chart for 2-column results
        if len(df.columns) == 2:
            st.subheader("📊 Interactive Visualization")
            chart_df = df.copy()
            # Ensure the metric column is numeric so the chart renders properly
            chart_df[chart_df.columns[1]] = pd.to_numeric(chart_df[chart_df.columns[1]], errors="coerce")
            st.bar_chart(chart_df.set_index(chart_df.columns[0]))

    except Exception as e:
        # Step G: Display user-friendly UI alert on any execution or connection error
        st.error(f"Error executing query: {e}")
