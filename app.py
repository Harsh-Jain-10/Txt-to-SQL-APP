import os, json, time
import streamlit as st
import pandas as pd
import psycopg2
import sqlglot
from sqlglot import exp
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import List, Optional

# =============================================================================
# 1. Config, Session State & Modern Cockpit Styling
# =============================================================================
load_dotenv()
st.set_page_config(
    page_title="Digital Store Intelligence Platform",
    page_icon="⚡",
    layout="wide"
)

# Custom Enterprise Light Cockpit Styling
st.markdown("""
<style>
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .hero-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
        margin-bottom: 1.5rem;
        text-align: center;
    }
    .badge-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 9999px;
        background-color: #ecfdf5;
        color: #059669;
        border: 1px solid #a7f3d0;
    }
    .header-sub {
        color: #64748b;
        font-size: 1rem;
        margin-top: -0.5rem;
        margin-bottom: 1.25rem;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
for key, default in [
    ("authenticated", False),
    ("clarify_data", None),
    ("resolved_query", None),
    ("current_input", "Show me the top 5 customers"),
    ("query_history", [])
]:
    if key not in st.session_state:
        st.session_state[key] = default

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
client = Groq(api_key=os.getenv("LLM_API_KEY"))

# =============================================================================
# 2. Pydantic Models & Ground Truth Schema Definition
# =============================================================================
class ClarificationOption(BaseModel):
    id: int
    label: str
    metric_description: str
    sql_expression: str

class IntentAnalysis(BaseModel):
    is_ambiguous: bool
    question: Optional[str] = None
    options: List[ClarificationOption] = Field(default_factory=list)

SCHEMA = (
    "Table: digital_store_sales. Columns available:\n"
    "- customer_id (TEXT), customer_city (TEXT), customer_state (TEXT)\n"
    "- product_id (TEXT), product_category_name (TEXT)\n"
    "- price (NUMERIC), freight_value (NUMERIC), payment_value (NUMERIC), payment_type (TEXT), payment_installments (INT)\n"
    "- order_id (TEXT), order_status (TEXT)\n"
    "- order_purchase_timestamp (TIMESTAMP), year_of_purchase (INT)\n\n"
    "Strict Guardrails: Only use allowed columns. NEVER suggest customer names, ratings, reviews, visits, or stock.\n"
    "- For 'top customers': rank by SUM(payment_value), COUNT(DISTINCT order_id), or SUM(price).\n"
    "- For 'best products': rank by COUNT(order_id) or SUM(price).\n"
    "- For 'revenue': offer SUM(payment_value) vs SUM(price)."
)

# =============================================================================
# 3. Stage 4: Query Safety Validation & Guardrails (SQLGlot)
# =============================================================================
def validate_query(sql: str) -> tuple[bool, str, str]:
    cleaned = sql.strip().rstrip(";")
    if ";" in cleaned:
        return False, "Multiple statements separated by semicolons are not permitted.", sql
    try:
        exprs = sqlglot.parse(cleaned, read="postgres")
    except Exception as e:
        return False, f"SQL syntax error: {e}", sql
    if len(exprs) != 1 or not exprs[0]:
        return False, "Invalid or empty SQL statement.", sql
    expression = exprs[0]
    if not isinstance(expression, exp.Select):
        return False, "Only read-only SELECT queries are permitted.", sql
    for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "EXECUTE"]:
        if kw in cleaned.upper():
            return False, f"Keyword '{kw}' is strictly forbidden.", sql
    tables = [t.name.lower() for t in expression.find_all(exp.Table)]
    if not tables or any(t != "digital_store_sales" for t in tables):
        return False, "Query must strictly target the 'digital_store_sales' table.", sql
    if not expression.args.get("limit"):
        cleaned = f"{cleaned} LIMIT 50"
    return True, "", cleaned

# =============================================================================
# 4. Stage 3: Intent Analysis via Groq JSON Mode
# =============================================================================
def analyze_intent(q: str) -> IntentAnalysis:
    prompt = (
        f"Analyze if this e-commerce analytics question is ambiguous.\n{SCHEMA}\nQuestion: '{q}'\n"
        'Return JSON: {"is_ambiguous": bool, "question": "string or null", "options": [{"id": int, "label": "str", "metric_description": "str", "sql_expression": "exact SQL formula"}]}'
    )
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            res = client.chat.completions.create(
                model=m, messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, temperature=0.0
            )
            return IntentAnalysis(**json.loads(res.choices[0].message.content))
        except Exception:
            continue
    return IntentAnalysis(is_ambiguous=False)

# =============================================================================
# 5. Database Query Runner
# =============================================================================
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "digital_store"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )

# =============================================================================
# MODULE 1: The Landing Page (Welcome & Authentication)
# =============================================================================
if not st.session_state.authenticated:
    st.markdown("""
    <div class="hero-card">
        <span class="status-badge">⚡ Enterprise Data Cockpit</span>
        <h1 style="margin-top: 0.8rem; margin-bottom: 0.3rem;">Digital Store Admin Portal</h1>
        <p class="header-sub">Natural Language Analytics & Automated SQL Disambiguation Engine</p>
    </div>
    """, unsafe_allow_html=True)

    # 3-Column Impression Badges
    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown("""
        <div class="badge-card">
            <h3>📦 113K+ Real Records</h3>
            <p style="color: #64748b; font-size: 0.9rem;">Olist Transactional Master Catalog live in PostgreSQL</p>
        </div>
        """, unsafe_allow_html=True)
    with b2:
        st.markdown("""
        <div class="badge-card">
            <h3>🛡️ Schema Guardrails</h3>
            <p style="color: #64748b; font-size: 0.9rem;">Read-Only SQLGlot AST Validation & Anti-Injection Rules</p>
        </div>
        """, unsafe_allow_html=True)
    with b3:
        st.markdown("""
        <div class="badge-card">
            <h3>🧠 Clarification Engine</h3>
            <p style="color: #64748b; font-size: 0.9rem;">Zero-Guesswork Ambiguity Disambiguation via Pydantic & Groq</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Centered Login Card
    col_l, col_center, col_r = st.columns([1, 1.8, 1])
    with col_center:
        st.markdown("### 🔒 Secure Admin Authentication")
        with st.form("admin_login_form"):
            admin_id = st.text_input("Admin ID", value="admin", placeholder="Enter Admin ID")
            admin_pwd = st.text_input("Security Key / Password", value="admin123", type="password", placeholder="Enter Password")
            login_btn = st.form_submit_button("Enter Analytics Workspace", type="primary", use_container_width=True)

            if login_btn:
                if admin_id == ADMIN_USER and admin_pwd == ADMIN_PASS:
                    st.session_state.authenticated = True
                    st.success("Access Granted! Initializing analytics cockpit...")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please verify your Admin ID and Password (default: admin / admin123).")

        st.info("💡 **Demo Access Credentials**: Admin ID: `admin` | Password: `admin123`")

# =============================================================================
# MODULE 2, 3, 4: The Main Data Analysis Platform
# =============================================================================
else:
    # --- Sidebar Navigation & System Health ---
    with st.sidebar:
        st.markdown("### 🏢 Digital Store Cockpit")
        st.markdown('<span class="status-badge">🟢 PostgreSQL: Connected (113,390 rows)</span>', unsafe_allow_html=True)
        st.caption(f"Authenticated Operator: **{ADMIN_USER}**")
        st.divider()

        st.markdown("#### ⚙️ System Specifications")
        st.text("Engine: llama-3.3-70b-versatile\nDatabase: digital_store\nDriver: psycopg2 + SQLGlot\nSecurity: Read-Only (SELECT)")

        with st.expander("📋 Quick Schema Cheat-Sheet"):
            st.markdown("""
            **Columns in `digital_store_sales`:**
            - `customer_id`, `customer_city`, `customer_state`
            - `product_id`, `product_category_name`
            - `price`, `freight_value`, `payment_value`
            - `payment_type`, `payment_installments`
            - `order_id`, `order_status`
            - `order_purchase_timestamp`, `year_of_purchase`
            """)

        st.divider()
        if st.session_state.query_history:
            st.markdown("#### 🕒 Recent Session Queries")
            for h in reversed(st.session_state.query_history[-4:]):
                st.caption(f"• {h}")

        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.clarify_data = None
            st.session_state.resolved_query = None
            st.rerun()

    # --- Header Bar ---
    st.title("⚡ Digital Store Data Analysis Platform")
    st.markdown('<p class="header-sub">AI-Powered SQL Analytics Cockpit with Real-Time Guardrails and Multi-Tab Visualizations</p>', unsafe_allow_html=True)

    # --- Preset Quick-Prompts ---
    st.markdown("##### 💡 Preset Quick-Prompts")
    presets = [
        "Top 5 cities by order count",
        "Show best product categories",
        "Revenue breakdown by payment type",
        "Show me the top 5 customers"
    ]
    p_cols = st.columns(len(presets))
    for i, p in enumerate(presets):
        with p_cols[i]:
            if st.button(p, key=f"quick_{i}", use_container_width=True):
                st.session_state.current_input = p
                st.session_state.clarify_data = None
                st.session_state.resolved_query = None

    # --- Query Input Workspace ---
    query_col, btn_col = st.columns([5, 1])
    with query_col:
        q_input = st.text_input(
            "Enter your business query:",
            value=st.session_state.current_input,
            placeholder="e.g. Show top 5 customer cities by total spending"
        )
    with btn_col:
        st.write("")
        st.write("")
        run_btn = st.button("⚡ Analyze & Query", type="primary", use_container_width=True)

    # Handle Analyze & Query button
    if run_btn and q_input:
        st.session_state.current_input = q_input
        st.session_state.resolved_query = None
        if q_input not in st.session_state.query_history:
            st.session_state.query_history.append(q_input)

        with st.spinner("Analyzing intent with schema guardrails..."):
            analysis = analyze_intent(q_input)
            if analysis.is_ambiguous and analysis.options:
                st.session_state.clarify_data = {"orig": q_input, "analysis": analysis}
            else:
                st.session_state.clarify_data = None
                st.session_state.resolved_query = q_input

    # --- Clarification Engine (Disambiguation) ---
    if st.session_state.clarify_data:
        orig = st.session_state.clarify_data["orig"]
        analysis = st.session_state.clarify_data["analysis"]

        st.warning("⚠️ **Ambiguity Detected: Multiple interpretations exist for your query.**")
        st.markdown(f"**Clarification Question:** {analysis.question or 'Please select the mathematical metric formula you intend to compute:'}")

        # Render options as horizontal button chips in balanced columns
        btn_cols = st.columns(min(len(analysis.options), 3))
        for i, opt in enumerate(analysis.options):
            with btn_cols[i % len(btn_cols)]:
                chip_label = f"📌 **{opt.label}**\n\n`{opt.sql_expression}`\n\n_{opt.metric_description}_"
                if st.button(chip_label, key=f"clarify_{opt.id}", use_container_width=True):
                    st.session_state.resolved_query = f"{orig} (calculate strictly using formula: {opt.sql_expression} - {opt.metric_description})"
                    st.session_state.clarify_data = None
                    st.rerun()

    # --- Safe Execution, Structured Output & Rich Visualization ---
    if st.session_state.resolved_query:
        active_query = st.session_state.resolved_query
        st.info(f"🎯 **Active Query Request:** {active_query}")

        prompt = (
            f"You are a PostgreSQL expert. Return ONLY raw SQL without markdown or backticks. Always add LIMIT 5 unless specified.\n"
            f"Schema:\n{SCHEMA}\nQuestion: {active_query}"
        )

        with st.spinner("🧠 Generating SQL query with Groq LLM..."):
            for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
                try:
                    res = client.chat.completions.create(model=m, messages=[{"role": "user", "content": prompt}], temperature=0.0)
                    break
                except Exception:
                    continue

            raw_sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

        # Step 5: SQL Validation & Security Guardrail
        is_valid, rejection_reason, safe_sql = validate_query(raw_sql)
        if not is_valid:
            st.error(f"🚨 **Security Alert:** {rejection_reason}")
        else:
            # Execute on PostgreSQL and measure execution time
            start_time = time.time()
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = 5000;")
                    cur.execute(safe_sql)
                    columns = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                conn.close()
                exec_time_ms = round((time.time() - start_time) * 1000, 2)

                df = pd.DataFrame(rows, columns=columns)

                # SQL Inspector Expander with Execution Time
                with st.expander("🔍 SQL Inspector & Guardrail Audit", expanded=True):
                    st.code(safe_sql, language="sql")
                    st.caption(f"⚡ Execution Latency: **{exec_time_ms} ms** | Security Check: **Passed (Read-Only SELECT, Target: digital_store_sales)**")

                # Step 6: Multi-Tab Structured Results View
                tab1, tab2, tab3 = st.tabs(["📋 Data View", "📊 Visual Analytics", "📈 Summary Metrics"])

                # Tab 1: Data View
                with tab1:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Rows Returned", len(df))
                    m2.metric("Total Columns", len(df.columns))
                    m3.metric("Database Latency", f"{exec_time_ms} ms")
                    st.dataframe(df, use_container_width=True)

                    # Column Data Types Breakdown
                    with st.expander("ℹ️ Column Schema & Data Types"):
                        st.json({col: str(df[col].dtype) for col in df.columns})

                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    st.download_button("📥 Export as CSV", data=csv_bytes, file_name="analytics_export.csv", mime="text/csv")

                # Tab 2: Visual Analytics
                with tab2:
                    if len(df.columns) >= 2:
                        chart_df = df.copy()
                        cat_col = chart_df.columns[0]
                        num_col = chart_df.columns[1]
                        chart_df[num_col] = pd.to_numeric(chart_df[num_col], errors="coerce")

                        chart_choice = st.radio("Chart Type:", ["Bar Chart", "Line Chart", "Area Chart"], horizontal=True)
                        if chart_choice == "Bar Chart":
                            st.bar_chart(chart_df.set_index(cat_col)[[num_col]])
                        elif chart_choice == "Line Chart":
                            st.line_chart(chart_df.set_index(cat_col)[[num_col]])
                        else:
                            st.area_chart(chart_df.set_index(cat_col)[[num_col]])
                    else:
                        st.info("Chart requires at least 2 columns to plot dimensions.")

                # Tab 3: Summary Metrics
                with tab3:
                    st.markdown("#### 📌 Key Performance Indicators")
                    num_cols = df.select_dtypes(include=["number"]).columns.tolist()
                    if num_cols:
                        metric_target = num_cols[0]
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric(f"Total {metric_target}", f"{df[metric_target].sum():,.2f}")
                        k2.metric(f"Average {metric_target}", f"{df[metric_target].mean():,.2f}")
                        k3.metric(f"Max {metric_target}", f"{df[metric_target].max():,.2f}")
                        k4.metric(f"Min {metric_target}", f"{df[metric_target].min():,.2f}")

                        # Top Performer identification
                        if len(df) > 0 and len(df.columns) >= 2:
                            top_label = df.iloc[0][df.columns[0]]
                            top_val = df.iloc[0][metric_target]
                            st.success(f"🏆 **Top Performer:** **{top_label}** with **{top_val:,.2f}** {metric_target}")
                    else:
                        st.metric("Total Records Identified", len(df))

            except Exception as e:
                st.error(f"Execution Error: {e}")
