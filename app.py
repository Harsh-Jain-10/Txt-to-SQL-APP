import os, json
import streamlit as st
import pandas as pd
import psycopg2
import sqlglot; from sqlglot import exp
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field; from typing import List, Optional

# 1. Config & Grounded Pydantic Schemas
load_dotenv()
st.set_page_config(page_title="Text to SQL Analytics", page_icon="⚡", layout="wide")
st.title("⚡ Text to SQL Analytics Dashboard")
client = Groq(api_key=os.getenv("LLM_API_KEY"))

class ClarificationOption(BaseModel):
    id: int; label: str; metric_description: str; sql_expression: str

class IntentAnalysis(BaseModel):
    is_ambiguous: bool; question: Optional[str] = None; options: List[ClarificationOption] = Field(default_factory=list)

SCHEMA = (
    "Table: digital_store_sales. Columns: customer_id, customer_city, customer_state, product_id, product_category_name, "
    "price, freight_value, payment_value, payment_type, payment_installments, order_id, order_status, order_purchase_timestamp, year_of_purchase.\n"
    "Guardrails: Only use allowed columns. Never suggest customer names or ratings. "
    "- 'top customers': rank by SUM(payment_value), COUNT(DISTINCT order_id), or SUM(price). "
    "- 'best products': rank by COUNT(order_id) or SUM(price). - 'revenue': offer SUM(payment_value) vs SUM(price)."
)

# 2. Stage 4: Query Safety Validation & Guardrails
def validate_query(sql: str) -> tuple[bool, str, str]:
    cleaned = sql.strip().rstrip(";")
    if ";" in cleaned: return False, "Multiple statements separated by semicolons are not permitted.", sql
    try:
        exprs = sqlglot.parse(cleaned, read="postgres")
    except Exception as e: return False, f"SQL syntax error: {e}", sql
    if len(exprs) != 1 or not exprs[0]: return False, "Invalid statement.", sql
    expression = exprs[0]
    if not isinstance(expression, exp.Select): return False, "Only read-only SELECT queries are permitted.", sql
    for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "EXECUTE"]:
        if kw in cleaned.upper(): return False, f"Keyword '{kw}' is strictly forbidden.", sql
    tables = [t.name.lower() for t in expression.find_all(exp.Table)]
    if not tables or any(t != "digital_store_sales" for t in tables):
        return False, "Query must strictly target the 'digital_store_sales' table.", sql
    if not expression.args.get("limit"): cleaned = f"{cleaned} LIMIT 50"
    return True, "", cleaned

# 3. Intent Analysis via Groq JSON Mode
def analyze_intent(q: str) -> IntentAnalysis:
    prompt = (
        f"Analyze if this e-commerce analytics question is ambiguous.\n{SCHEMA}\nQuestion: '{q}'\n"
        'Return JSON: {"is_ambiguous": bool, "question": "string or null", "options": [{"id": int, "label": "str", "metric_description": "str", "sql_expression": "exact SQL formula"}]}'
    )
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(model=m, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}, temperature=0.0)
            return IntentAnalysis(**json.loads(res.choices[0].message.content))
        except Exception:
            continue
    return IntentAnalysis(is_ambiguous=False)

# 4. Safe Execution Flow with Statement Timeout
def run_query(resolved_prompt: str):
    prompt = f"You are a PostgreSQL expert. Return ONLY raw SQL without markdown. Always add LIMIT 5 unless specified.\nSchema:\n{SCHEMA}\nQuestion: {resolved_prompt}"
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(model=m, messages=[{"role": "user", "content": prompt}], temperature=0.0)
            break
        except Exception:
            continue

    raw_sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    is_valid, rejection_reason, safe_sql = validate_query(raw_sql)
    if not is_valid:
        st.error(f"🚨 Security Alert: {rejection_reason}"); return

    with st.expander("🔍 Inspect Generated SQL Query", expanded=True): st.code(safe_sql, language="sql")
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "digital_store"), user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432")
        )
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 5000;")
            cur.execute(safe_sql)
            df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        conn.close()
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows Returned", len(df)); c2.metric("Total Columns", len(df.columns)); c3.metric("Status", "200 Success")
        st.dataframe(df, use_container_width=True)
        if len(df.columns) >= 2:
            st.subheader("📊 Interactive Visualization")
            chart_df = df.copy(); val_col = chart_df.columns[1]
            chart_df[val_col] = pd.to_numeric(chart_df[val_col], errors="coerce")
            st.bar_chart(chart_df.set_index(chart_df.columns[0])[[val_col]])
    except Exception as e:
        st.error(f"Execution Error: {e}")

# 5. User Interface & Full-Width Clarification

for key in ["clarify_data", "resolved_query"]:
    if key not in st.session_state: st.session_state[key] = None

q_input = st.text_input("Enter your business question:", value="Show me the top 5 customers")
if st.button("Generate & Run", type="primary"):
    st.session_state.resolved_query = None
    with st.spinner("Analyzing intent with schema guardrails..."):
        analysis = analyze_intent(q_input)
        if analysis.is_ambiguous and analysis.options:
            st.session_state.clarify_data = {"orig": q_input, "analysis": analysis}
        else:
            st.session_state.clarify_data = None; st.session_state.resolved_query = q_input

if st.session_state.clarify_data:
    orig = st.session_state.clarify_data["orig"]
    analysis = st.session_state.clarify_data["analysis"]
    st.warning(f"🤔 **Clarification Needed:** {analysis.question or 'Please choose a specific metric formula:'}")
    btn_cols = st.columns(min(len(analysis.options), 3))
    for i, opt in enumerate(analysis.options):
        with btn_cols[i % len(btn_cols)]:
            label_text = f"📌 {opt.label}\n\nFormula: {opt.sql_expression}\n\n({opt.metric_description})"
            if st.button(label_text, key=f"opt_{opt.id}", use_container_width=True):
                st.session_state.resolved_query = f"{orig} (calculate strictly using formula: {opt.sql_expression} - {opt.metric_description})"
                st.session_state.clarify_data = None; st.rerun()

if st.session_state.resolved_query:
    st.info(f"🎯 **Resolved Request:** {st.session_state.resolved_query}")
    run_query(st.session_state.resolved_query)
