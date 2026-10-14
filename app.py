import os, json
import streamlit as st
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import List, Optional

# 1. Config & Pydantic Schemas for Intent Analysis
load_dotenv()
st.set_page_config(page_title="Text to SQL Analytics", layout="wide")
st.title("⚡ Text to SQL Analytics Dashboard")
client = Groq(api_key=os.getenv("LLM_API_KEY"))

class ClarificationOption(BaseModel):
    id: int
    label: str
    metric_description: str

class IntentAnalysis(BaseModel):
    is_ambiguous: bool
    question: Optional[str] = None
    options: List[ClarificationOption] = Field(default_factory=list)

# 2. Ambiguity Detection via Groq JSON Mode
def analyze_intent(q: str) -> IntentAnalysis:
    prompt = (
        "Analyze if this e-commerce analytics question is ambiguous. "
        "Words like 'top', 'best', 'active', 'valuable' can mean different metrics (e.g. payment_value vs orders). "
        f"Question: '{q}'. Schema: digital_store_sales. Return JSON strictly matching: "
        '{"is_ambiguous": bool, "question": "string or null", "options": [{"id": 1, "label": "string", "metric_description": "string"}]}'
    )
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(
                model=m, messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, temperature=0.0
            )
            break
        except Exception:
            continue
    data = json.loads(res.choices[0].message.content)
    return IntentAnalysis(**data)

# 3. SQL Generation & Execution Flow
def run_query(resolved_prompt: str):
    schema = "Table: digital_store_sales. Columns: order_id, customer_id, customer_city, product_category_name, price, payment_value, order_status."
    prompt = f"You are a PostgreSQL expert. Return ONLY raw SQL without markdown. Always add LIMIT 5 unless specified.\nSchema: {schema}\nQuestion: {resolved_prompt}"
    
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(model=m, messages=[{"role": "user", "content": prompt}], temperature=0.0)
            break
        except Exception:
            continue

    sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    with st.expander("🔍 Generated SQL Query", expanded=True):
        st.code(sql, language="sql")

    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "digital_store"), user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432")
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        conn.close()

        df = pd.DataFrame(rows, columns=columns)
        st.metric("Total Rows", len(df))
        st.dataframe(df, use_container_width=True)

        # Bar chart for 2-column results
        if len(df.columns) == 2:
            st.subheader("📊 Visualization")
            chart_df = df.copy()
            chart_df[chart_df.columns[1]] = pd.to_numeric(chart_df[chart_df.columns[1]], errors="coerce")
            st.bar_chart(chart_df.set_index(chart_df.columns[0]))
    except Exception as e:
        st.error(f"Execution Error: {e}")

# 4. User Interface & Interactive Clarification Loop
if "clarify_data" not in st.session_state:
    st.session_state.clarify_data = None

question = st.text_input("Enter your business question:", value="Show me the top 5 customers")

if st.button("Generate & Run", type="primary"):
    with st.spinner("Analyzing query intent..."):
        analysis = analyze_intent(question)
        if analysis.is_ambiguous and analysis.options:
            st.session_state.clarify_data = {"orig": question, "analysis": analysis}
        else:
            st.session_state.clarify_data = None
            run_query(question)

# Interactive Clarification Buttons
if st.session_state.clarify_data:
    orig = st.session_state.clarify_data["orig"]
    data = st.session_state.clarify_data["analysis"]
    st.warning(f"🤔 Clarification Needed: {data.question or 'Please choose a specific metric'}")
    cols = st.columns(len(data.options))
    for i, opt in enumerate(data.options):
        with cols[i]:
            if st.button(f"{opt.label}\n({opt.metric_description})", key=f"opt_{opt.id}"):
                combined = f"{orig} (defined as: {opt.label} - {opt.metric_description})"
                st.session_state.clarify_data = None
                st.info(f"Resolved Request: {combined}")
                run_query(combined)
