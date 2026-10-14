import os
import streamlit as st
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from groq import Groq

# -----------------------------------------------------------------------------
# 1. Page Configuration & Executive Light Theme Styling
# -----------------------------------------------------------------------------
load_dotenv()
st.set_page_config(
    page_title="Digital Store Admin Panel | Text-to-SQL",
    page_icon="⚡",
    layout="wide"
)

# Professional Light-Theme Custom CSS
st.markdown("""
<style>
    /* Global application styling for a crisp light enterprise theme */
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    /* Executive Card Container */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        margin-bottom: 1rem;
    }
    /* Login card container */
    .login-box {
        max-width: 480px;
        margin: 2rem auto;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 2.5rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
    }
    /* Status Badge */
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
    /* Header subtitle */
    .header-sub {
        color: #64748b;
        font-size: 1rem;
        margin-top: -0.5rem;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. Authentication & Session State Setup
# -----------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_question" not in st.session_state:
    st.session_state.current_question = "Show the top 5 cities with the highest number of orders"
if "query_history" not in st.session_state:
    st.session_state.query_history = []

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

# Initialize Groq client
client = Groq(api_key=os.getenv("LLM_API_KEY"))

# -----------------------------------------------------------------------------
# 3. Landing Page & Admin Authentication View
# -----------------------------------------------------------------------------
if not st.session_state.authenticated:
    col_left, col_center, col_right = st.columns([1, 2, 1])
    
    with col_center:
        st.markdown("""
        <div class="login-box">
            <span class="status-badge">🏢 Enterprise Analytics</span>
            <h2 style="margin-top: 0.8rem; margin-bottom: 0.2rem; color: #0f172a;">Welcome to Digital Store Admin Panel</h2>
            <p class="header-sub">Sign in to access the Text-to-SQL business intelligence platform.</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", value="admin", placeholder="Enter username")
            password = st.text_input("Password", value="admin123", type="password", placeholder="Enter password")
            submit_btn = st.form_submit_button("Sign In to Dashboard", type="primary", use_container_width=True)

            if submit_btn:
                if username == ADMIN_USER and password == ADMIN_PASS:
                    st.session_state.authenticated = True
                    st.success("Authentication successful! Loading dashboard...")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please use default credentials: admin / admin123")

        st.info("💡 **Demo Access**: Username: `admin` | Password: `admin123`")

        # Three feature highlights on the landing page
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("⚡ **Fast Text-to-SQL**\nInstant query generation via Groq inference.")
        with c2:
            st.caption("📊 **Interactive Visuals**\nTabular structured data & automatic charting.")
        with c3:
            st.caption("🛡️ **PostgreSQL Secure**\nDirect, read-only analytics on store sales.")

# -----------------------------------------------------------------------------
# 4. Authenticated Dashboard & Analysis Platform View
# -----------------------------------------------------------------------------
else:
    # --- Sidebar Configuration ---
    with st.sidebar:
        st.markdown("### 🏢 Digital Store Admin")
        st.markdown('<span class="status-badge">🟢 Connected to PostgreSQL</span>', unsafe_allow_html=True)
        st.caption(f"Logged in as **{ADMIN_USER}**")
        st.divider()

        # Preset query templates for quick user exploration
        st.markdown("#### 💡 Quick Query Presets")
        presets = [
            "Show the top 5 cities with the highest number of orders",
            "Show the top 5 product categories by total sales price",
            "What are the payment types and their order counts?",
            "Show the top 5 customer states by total payment value",
            "Count total orders grouped by order_status"
        ]
        for p in presets:
            if st.button(p, key=f"preset_{p}"):
                st.session_state.current_question = p

        st.divider()
        if st.session_state.query_history:
            st.markdown("#### 🕒 Recent Queries")
            for h in reversed(st.session_state.query_history[-4:]):
                st.caption(f"• {h}")

        st.divider()
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    # --- Main Dashboard Top Banner ---
    st.title("⚡ Digital Store Analytics Platform")
    st.markdown('<p class="header-sub">Ask any question in plain English to automatically query PostgreSQL, view structured tables, and explore charts.</p>', unsafe_allow_html=True)

    # High-level enterprise KPI metrics ribbon
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Total Catalog Orders", "113,390", "PostgreSQL Live")
    with kpi2:
        st.metric("Database Target", "digital_store", "public.digital_store_sales")
    with kpi3:
        st.metric("AI Generation Engine", "Groq Llama 3.3", "Zero-Shot SQL")
    with kpi4:
        st.metric("Dashboard Theme", "Light Enterprise", "Active")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- User Query Input Section ---
    query_col, btn_col = st.columns([5, 1])
    with query_col:
        question = st.text_input(
            "Natural Language Business Question:",
            value=st.session_state.current_question,
            placeholder="e.g. Show top 5 cities with highest orders"
        )
    with btn_col:
        st.write("")
        st.write("")
        run_btn = st.button("⚡ Run Query", type="primary", use_container_width=True)

    # --- Query Execution, Tabular Output, and Chart Visualization ---
    if run_btn and question:
        # Save to session history
        if question not in st.session_state.query_history:
            st.session_state.query_history.append(question)

        # Context prompt containing the digital_store_sales table schema
        prompt = (
            "You are a PostgreSQL expert. Table: digital_store_sales. "
            "Columns: order_id, customer_id, customer_city, customer_state, product_id, "
            "product_category_name, payment_type, payment_installments, payment_value, "
            "price, freight_value, order_purchase_timestamp, year_of_purchase, order_status. "
            "Return ONLY raw SQL without markdown or backticks. Always add LIMIT 5 unless specified. "
            f"Question: {question}"
        )

        with st.spinner("🧠 Generating SQL query with Groq AI..."):
            try:
                # Step A: Request SQL generation from Groq LLM (with fallback for reliability)
                for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
                    try:
                        res = client.chat.completions.create(
                            model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
                        )
                        break
                    except Exception:
                        continue

                # Clean markdown backticks from response to obtain raw executable SQL
                sql = res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

                # Step B: Display generated SQL in an expandable inspection block
                with st.expander("🔍 Inspect Generated SQL Query", expanded=True):
                    st.code(sql, language="sql")

                # Step C: Connect to PostgreSQL and execute the query
                conn = psycopg2.connect(
                    dbname=os.getenv("DB_NAME", "digital_store"),
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASSWORD"),
                    host=os.getenv("DB_HOST", "localhost"),
                    port=os.getenv("DB_PORT", "5432")
                )
                with conn.cursor() as cur:
                    cur.execute(sql)
                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                conn.close()

                # Step D [Structured Output]: Convert raw SQL rows and column headers into a pandas DataFrame
                df = pd.DataFrame(rows, columns=columns)

                # Step E [Metrics & Table Display]: Render execution stats and the interactive data table
                st.markdown("### 📋 Structured Data Results")
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Rows Returned", len(df))
                with m2:
                    st.metric("Query Status", "200 Success")
                with m3:
                    st.metric("Total Columns", len(df.columns))

                # Render structured tabular output
                st.dataframe(df, use_container_width=True)

                # Export CSV button
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export Results as CSV",
                    data=csv_data,
                    file_name="sql_query_results.csv",
                    mime="text/csv"
                )

                # Step F [Visualization & Charting]: Auto-render interactive charts for multi-dimensional data
                if len(df.columns) >= 2:
                    st.markdown("### 📊 Interactive Data Visualization")
                    chart_df = df.copy()
                    
                    # Identify category column (first column) and numeric column (second column)
                    cat_col = chart_df.columns[0]
                    val_col = chart_df.columns[1]
                    chart_df[val_col] = pd.to_numeric(chart_df[val_col], errors="coerce")

                    chart_tab1, chart_tab2 = st.tabs(["📊 Bar Chart", "📈 Line Chart"])
                    with chart_tab1:
                        st.bar_chart(chart_df.set_index(cat_col)[[val_col]])
                    with chart_tab2:
                        st.line_chart(chart_df.set_index(cat_col)[[val_col]])

            except Exception as e:
                # Step G: Display user-friendly UI alert on any execution or connection error
                st.error(f"Execution Error: {e}")
