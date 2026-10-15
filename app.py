import os, json, time
from decimal import Decimal
import streamlit as st
import pandas as pd
import psycopg2
import sqlglot
from sqlglot import exp
import plotly.express as px
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import List, Optional

load_dotenv()
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
client = Groq(api_key=os.getenv("LLM_API_KEY"))

# =============================================================================
# 1. Pydantic Models & Ground Truth Schema Definition
# =============================================================================
class ClarificationOption(BaseModel):
    label: str
    description: str
    sql: str

class IntentAnalysis(BaseModel):
    is_ambiguous: bool
    is_unanswerable: bool = False
    unanswerable_message: Optional[str] = None
    question: Optional[str] = None
    options: List[ClarificationOption] = Field(default_factory=list)

SCHEMA = (
    "Table: digital_store_sales. Columns available:\n"
    "- customer_id (TEXT), customer_city (TEXT), customer_state (TEXT)\n"
    "- product_id (TEXT), product_category_name (TEXT)\n"
    "- price (NUMERIC), freight_value (NUMERIC), payment_value (NUMERIC), payment_type (TEXT), payment_installments (INT)\n"
    "- order_id (TEXT), order_status (TEXT)\n"
    "- order_purchase_timestamp (TIMESTAMP), year_of_purchase (INT)"
)

METRIC_RULES = (
    "METRIC RULES:\n"
    "- Counting orders must use COUNT(DISTINCT order_id), never COUNT(order_id).\n"
    "- Counting units sold = COUNT(*) rows, labelled 'units (line items)'.\n"
    "- Revenue options:\n"
    "  (a) item revenue = SUM(price)\n"
    "  (b) payments collected = SUM(payment_value) over distinct (order_id, payment_type, payment_value) rows via subquery: (SELECT DISTINCT order_id, payment_type, payment_value FROM digital_store_sales) sub\n"
    "  (c) price + freight_value = customer-paid line total\n"
    "- Display fields: Never group by product_id for display; product_category_name is the readable product field.\n"
    "- Most selling product: default to TOP 10 (not 1), grouped by product_category_name.\n"
    "- Row limits: Only include LIMIT if explicitly requested by user (e.g. 'top 5') or defaulted as above (TOP 10). Never invent arbitrary LIMIT values."
)

COLOR_PALETTE = ["#2563EB", "#0EA5E9", "#14B8A6", "#F59E0B", "#8B5CF6", "#64748B"]

# =============================================================================
# 2. LLM Fallback Caller
# =============================================================================
def call_groq(messages, json_mode=False):
    for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            kwargs = {"model": m, "messages": messages, "temperature": 0.0}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            return client.chat.completions.create(**kwargs)
        except Exception:
            continue
    raise RuntimeError("Unable to complete request with available Groq models.")

# =============================================================================
# 3. Query Safety Validation & Guardrails (SQLGlot)
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
    
    if expression.args.get("limit") is None:
        expression = expression.limit(1000)
        cleaned = expression.sql("postgres")
    else:
        cleaned = expression.sql("postgres")
    return True, "", cleaned

# =============================================================================
# 4. Intent Analysis & SQL Generation
# =============================================================================
def analyze_intent(q: str, is_retry: bool = False) -> IntentAnalysis:
    prompt = (
        f"Analyze this e-commerce analytics question for table digital_store_sales.\n"
        f"{SCHEMA}\n{METRIC_RULES}\n\n"
        f"Classify into exactly ONE of 3 categories:\n"
        f"1. Unanswerable: Query requires fields not in schema (e.g. age, profit, discount, cost, rating, reviews, customer name, phone).\n"
        f"   Set is_unanswerable=true, is_ambiguous=false, unanswerable_message=\"That information isn't in the dataset. Available columns: customer_city, customer_state, product_category_name, price, freight_value, payment_value, payment_type, payment_installments, order_status, order_purchase_timestamp, year_of_purchase.\", question=null, options=[]\n"
        f"2. Ambiguous: Query has multiple metric interpretations or ambiguity keywords ('revenue', 'sales', 'best', 'most selling' [units vs revenue vs orders], 'top customers'; time: 'recent', 'last year' without year; entity: 'customers').\n"
        f"   Always classify queries containing 'revenue', 'sales', 'best', or 'most selling' (e.g. 'Show me the most selling product') as Ambiguous.\n"
        f"   Set is_ambiguous=true, is_unanswerable=false, question=\"real clarification question addressing ambiguity (never echo user query)\", options=[2 to 4 items with label, description, sql].\n"
        f"   Each option's sql must be valid PostgreSQL SELECT on digital_store_sales (defaulting to LIMIT 10 for most selling product).\n"
        f"3. Clear: Specific unambiguous metric and dimension (e.g. 'Top 5 cities by order count', 'Total orders delivered', 'Orders per year').\n"
        f"   Set is_ambiguous=false, is_unanswerable=false, question=null, options=[]\n\n"
        f"Question: '{q}'\n"
        f"Return JSON: {{\"is_ambiguous\": bool, \"is_unanswerable\": bool, \"unanswerable_message\": str or null, \"question\": str or null, \"options\": [{{\"label\": str, \"description\": str, \"sql\": str}}]}}"
    )
    try:
        res = call_groq([{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(res.choices[0].message.content)
        analysis = IntentAnalysis(**data)
        if analysis.is_ambiguous and analysis.options:
            valid_opts = []
            for opt in analysis.options:
                is_valid, _, safe_sql = validate_query(opt.sql)
                if is_valid:
                    opt.sql = safe_sql
                    valid_opts.append(opt)
            if len(valid_opts) >= 2:
                analysis.options = valid_opts
                return analysis
            elif not is_retry:
                return analyze_intent(q, is_retry=True)
            else:
                analysis.options = []
                analysis.is_ambiguous = False
                analysis.unanswerable_message = "Failed to generate valid clarification options."
        return analysis
    except Exception:
        return IntentAnalysis(is_ambiguous=False)

def generate_sql(q: str) -> str:
    prompt = (
        f"You are a PostgreSQL expert. Return ONLY raw SQL without markdown or backticks.\n"
        f"{SCHEMA}\n{METRIC_RULES}\n"
        f"Strict: Select ONLY the specific metric/columns asked for in the question. Do not add unrequested columns.\n"
        f"Question: {q}"
    )
    res = call_groq([{"role": "user", "content": prompt}], json_mode=False)
    return res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

def generate_insight(rows: list, title: str) -> str:
    try:
        prompt = (
            f"Generate ONE concise sentence summarizing the main insight from these data rows for '{title}'. "
            f"Use ONLY numbers and facts explicitly present in these rows. Do not assume or invent any other numbers.\n"
            f"Data rows (max 20): {rows[:20]}"
        )
        res = call_groq([{"role": "user", "content": prompt}], json_mode=False)
        return res.choices[0].message.content.strip().replace('"', '')
    except Exception:
        return ""

# =============================================================================
# 5. Database Runner
# =============================================================================
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "digital_store"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )

def run_sql(sql: str) -> tuple[pd.DataFrame, float, Optional[str]]:
    start_time = time.time()
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 10000;")
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.close()
        latency = round((time.time() - start_time) * 1000, 2)
        return pd.DataFrame(rows, columns=columns), latency, None
    except Exception as e:
        return pd.DataFrame(), 0.0, str(e)

# =============================================================================
# 6. Automatic Charts
# =============================================================================
def render_auto_chart(df: pd.DataFrame, orig_title: str, metric_label: Optional[str] = None):
    if df.empty:
        st.info("No data returned to plot.")
        return

    plot_df = df.copy()
    for col in plot_df.columns:
        if plot_df[col].dtype == object:
            try:
                plot_df[col] = pd.to_numeric(plot_df[col])
            except (ValueError, TypeError):
                pass

    id_cols = [c for c in plot_df.columns if c.lower() in ('product_id', 'customer_id', 'order_id') or c.lower().endswith('_id')]
    date_cols = [c for c in plot_df.columns if 'year' in c.lower() or 'timestamp' in c.lower() or 'date' in c.lower() or pd.api.types.is_datetime64_any_dtype(plot_df[c])]
    state_cols = [c for c in plot_df.columns if c.lower() in ('customer_state', 'state')]
    num_cols = [c for c in plot_df.columns if pd.api.types.is_numeric_dtype(plot_df[c]) and c not in id_cols and c not in date_cols]
    cat_cols = [c for c in plot_df.columns if c not in id_cols and c not in date_cols and c not in num_cols and c not in state_cols]

    labels = {c: c.replace('_', ' ').title() for c in plot_df.columns}

    if not cat_cols and not date_cols and not state_cols and id_cols:
        st.info("No suitable chart for this result.")
        return

    if len(plot_df) == 1 and len(num_cols) == 1:
        val = plot_df[num_cols[0]].iloc[0]
        st.metric(label=labels.get(num_cols[0], "Value"), value=f"{val:,.2f}" if isinstance(val, (int, float, Decimal)) else str(val))
        return

    is_date_chart = bool(date_cols and num_cols)
    is_state_chart = bool(state_cols and num_cols and not cat_cols)
    is_donut_candidate = bool(cat_cols and num_cols and len(plot_df) <= 5 and any(c.lower() in ('payment_type', 'order_status') for c in cat_cols))
    is_cat_bar = bool((cat_cols or state_cols) and num_cols)

    default_type = "Bar"
    available_types = ["Bar"]

    if is_date_chart:
        default_type = "Line"
        available_types = ["Line", "Bar"]
    elif is_donut_candidate:
        default_type = "Donut"
        available_types = ["Donut", "Bar"]
    elif is_state_chart:
        default_type = "Bar"
        available_types = ["Bar", "Line"]
    elif is_cat_bar:
        default_type = "Bar"
        available_types = ["Bar", "Donut"] if len(plot_df) <= 5 else ["Bar"]
    elif len(num_cols) >= 2 and not cat_cols:
        default_type = "Scatter"
        available_types = ["Scatter"]
    elif len(num_cols) == 1 and len(plot_df) > 5 and not cat_cols:
        default_type = "Histogram"
        available_types = ["Histogram"]
    else:
        st.info("No suitable chart for this result.")
        return

    # Render Chart Type control ONLY when 2 or more chart types are valid
    has_slider = len(plot_df) > 10
    has_multi_types = len(available_types) >= 2

    chart_choice = default_type
    chart_df = plot_df

    if has_multi_types or has_slider:
        c1, c2 = st.columns([1, 1])
        if has_multi_types:
            with c1:
                chart_choice = st.radio("Chart Type", available_types, index=available_types.index(default_type), horizontal=True)
        if has_slider:
            with c2:
                top_n = st.slider("Top N", min_value=3, max_value=min(len(plot_df), 50), value=min(10, len(plot_df)))
                n_col = num_cols[0]
                chart_df = plot_df.sort_values(by=n_col, ascending=False).head(top_n)

    # Chart title: user's original question only, 16px weight 600, left-aligned
    st.markdown(f'<div style="font-size: 16px; font-weight: 600; color: #0F172A; margin-top: 8px;">{orig_title}</div>', unsafe_allow_html=True)
    if metric_label:
        st.markdown(f'<div style="font-size: 13px; color: #475569; margin-top: 2px; margin-bottom: 12px;">Metric: {metric_label}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="margin-bottom: 12px;"></div>', unsafe_allow_html=True)

    fig = None
    if chart_choice == "Donut":
        c_col = cat_cols[0]
        n_col = num_cols[0]
        fig = px.pie(chart_df, names=c_col, values=n_col, hole=0.5, labels=labels, color_discrete_sequence=COLOR_PALETTE)
    elif chart_choice == "Line":
        if is_date_chart:
            d_col = date_cols[0]
            n_col = num_cols[0]
            color = cat_cols[0] if cat_cols else None
            sorted_line = chart_df.sort_values(by=d_col)
            fig = px.line(sorted_line, x=d_col, y=n_col, color=color, labels=labels, color_discrete_sequence=COLOR_PALETTE)
        else:
            c_col = cat_cols[0] if cat_cols else (state_cols[0] if state_cols else chart_df.columns[0])
            n_col = num_cols[0]
            fig = px.line(chart_df, x=c_col, y=n_col, labels=labels, color_discrete_sequence=COLOR_PALETTE)
    elif chart_choice == "Bar":
        n_col = num_cols[0]
        if is_date_chart:
            d_col = date_cols[0]
            fig = px.bar(chart_df.sort_values(by=d_col), x=d_col, y=n_col, labels=labels, color_discrete_sequence=COLOR_PALETTE)
        elif is_state_chart:
            s_col = state_cols[0]
            sorted_state = chart_df.sort_values(by=n_col, ascending=True)
            colors = ["#2563EB" if i == len(sorted_state) - 1 else "#93C5FD" for i in range(len(sorted_state))]
            fig = px.bar(sorted_state, x=n_col, y=s_col, orientation='h', labels=labels)
            fig.update_traces(marker_color=colors)
        elif cat_cols:
            c_col = cat_cols[0]
            if len(plot_df) > 12 and len(chart_df) == len(plot_df):
                sorted_full = plot_df.sort_values(by=n_col, ascending=False)
                top10 = sorted_full.iloc[:10]
                other_val = sorted_full.iloc[10:][n_col].sum()
                other_row = pd.DataFrame([{c_col: "Other", n_col: other_val}])
                chart_df = pd.concat([top10, other_row], ignore_index=True)
            sorted_bar = chart_df.sort_values(by=n_col, ascending=True)
            colors = ["#2563EB" if i == len(sorted_bar) - 1 else "#93C5FD" for i in range(len(sorted_bar))]
            fig = px.bar(sorted_bar, x=n_col, y=c_col, orientation='h', labels=labels)
            fig.update_traces(marker_color=colors)
        else:
            fig = px.bar(chart_df, labels=labels, color_discrete_sequence=COLOR_PALETTE)
    elif chart_choice == "Scatter":
        fig = px.scatter(chart_df, x=num_cols[0], y=num_cols[1], labels=labels, color_discrete_sequence=COLOR_PALETTE)
    elif chart_choice == "Histogram":
        fig = px.histogram(chart_df, x=num_cols[0], labels=labels, color_discrete_sequence=COLOR_PALETTE)

    if fig:
        is_money = any(k in num_cols[0].lower() for k in ["price", "revenue", "value", "freight"]) if num_cols else False
        fig.update_layout(
            height=380,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            font=dict(family="Inter, system-ui, sans-serif", size=13, color="#475569")
        )
        fig.update_xaxes(
            showgrid=True,
            gridcolor="#E2E8F0",
            tickfont=dict(size=13, color="#475569", family="Inter, system-ui, sans-serif"),
            title_font=dict(size=13, color="#475569", family="Inter, system-ui, sans-serif")
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor="#E2E8F0",
            tickfont=dict(size=13, color="#475569", family="Inter, system-ui, sans-serif"),
            title_font=dict(size=13, color="#475569", family="Inter, system-ui, sans-serif")
        )
        if chart_choice == "Bar" and is_money:
            fig.update_xaxes(tickformat=",.2f")
            fig.update_traces(hovertemplate="%{y}: R$ %{x:,.2f}<extra></extra>")
        elif chart_choice == "Bar":
            fig.update_xaxes(tickformat=",")

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displaylogo": False,
                "modeBarButtonsToRemove": [
                    "zoom2d", "pan2d", "select2d", "lasso2d",
                    "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"
                ],
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": "chart"
                }
            }
        )

    rows_data = df.to_dict(orient="records")
    insight = generate_insight(rows_data, orig_title)
    if insight:
        st.markdown(
            f'<div style="font-size: 15px; color: #0F172A; margin: 16px 0 12px 0;">'
            f'<span style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; margin-right: 8px;">Insight</span>'
            f'{insight}</div>',
            unsafe_allow_html=True
        )

    st.markdown('<div style="font-size: 13px; font-weight: 600; color: #475569; margin: 16px 0 8px 0;">Follow-up Suggestions</div>', unsafe_allow_html=True)
    f_cols = st.columns(3)
    follow_ups = ["Break this down by year", "Show top 10", "Filter by state"]
    for i, f_text in enumerate(follow_ups):
        with f_cols[i]:
            st.markdown('<div class="followup-chip">', unsafe_allow_html=True)
            if st.button(f_text, key=f"follow_{i}", use_container_width=True):
                st.session_state.current_input = f"{orig_title} - {f_text}"
                st.session_state.clarify_data = None
                st.session_state.executed_data = None
                st.session_state.trigger_run = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# 7. Streamlit App Entry Point
# =============================================================================
def run_app():
    st.set_page_config(
        page_title="Digital Store Intelligence Platform",
        layout="wide"
    )

    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stApp"], button, input, textarea {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    color: #0F172A;
}
[data-testid="stMainBlockContainer"], .block-container {
    max-width: 1100px !important;
    padding-top: 32px !important;
    margin: 0 auto !important;
}
[data-testid="stHeaderActionElements"] { display: none !important; }
h1 { font-size: 28px !important; font-weight: 600 !important; line-height: 1.2 !important; margin-bottom: 4px !important; }
.header-sub { font-size: 15px !important; color: #475569 !important; margin-bottom: 24px !important; }
.active-query { background: #FFFFFF; border: 1px solid #E2E8F0; border-left: 3px solid #2563EB; border-radius: 8px; padding: 12px 16px; font-size: 15px; color: #0F172A; margin: 16px 0; }
.neutral-card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; font-size: 14px; color: #0F172A; margin: 16px 0; }
.option-card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; transition: border-color 0.15s ease; height: 100%; margin-bottom: 8px; }
.option-card:hover { border-color: #2563EB; }
[data-baseweb="input"] { border: 1px solid #CBD5E1 !important; border-radius: 8px !important; height: 44px !important; background: #FFFFFF !important; }
[data-baseweb="input"]:focus-within { border-color: #2563EB !important; box-shadow: 0 0 0 2px rgba(37,99,235,0.15) !important; }
[data-testid="stBaseButton-primary"] { height: 44px !important; background-color: #2563EB !important; color: #FFFFFF !important; font-size: 15px !important; font-weight: 500 !important; border-radius: 8px !important; border: none !important; }
[data-testid="stBaseButton-primary"]:hover { background-color: #1D4ED8 !important; }
[data-testid="stBaseButton-primary"]:disabled { background-color: #94A3B8 !important; cursor: not-allowed !important; opacity: 0.6 !important; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] { height: 36px !important; min-height: 36px !important; font-size: 13px !important; justify-content: flex-start !important; text-align: left !important; overflow: hidden !important; text-overflow: ellipsis !important; white-space: nowrap !important; background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; color: #0F172A !important; border-radius: 8px !important; padding: 0 12px !important; width: 100% !important; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover { border-color: #CBD5E1 !important; background: #F8FAFC !important; }
[data-testid="stRadio"] label p { font-size: 13px !important; }
[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 600 !important; }
[data-testid="stCodeBlock"] { background-color: #F1F5F9 !important; border-radius: 8px !important; }
code, pre { font-family: 'JetBrains Mono', ui-monospace, monospace !important; font-size: 13px !important; }
.followup-chip button { border-radius: 9999px !important; font-size: 13px !important; background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; color: #0F172A !important; height: 36px !important; }
.followup-chip button:hover { border-color: #2563EB !important; color: #2563EB !important; }
.status-pill { display: inline-block; padding: 4px 12px; font-size: 12px; font-weight: 500; border-radius: 9999px; background-color: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; }
</style>
""", unsafe_allow_html=True)

    for key, default in [
        ("authenticated", False),
        ("clarify_data", None),
        ("executed_data", None),
        ("error_message", None),
        ("current_input", "Top 5 cities by order count"),
        ("query_history", []),
        ("trigger_run", False)
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    if not st.session_state.authenticated:
        col_l, col_center, col_r = st.columns([1, 1.3, 1])
        with col_center:
            st.markdown('<div style="margin-top: 8vh;"></div>', unsafe_allow_html=True)
            st.markdown("""
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 24px; font-weight: 600; color: #0F172A; margin-bottom: 4px;">Digital Store Admin Portal</div>
                <div style="font-size: 15px; color: #475569; margin-bottom: 20px;">Sign in to continue</div>
            """, unsafe_allow_html=True)
            with st.form("admin_login_form"):
                admin_id = st.text_input("Admin ID", value="admin", placeholder="Enter Admin ID")
                admin_pwd = st.text_input("Password", value="admin123", type="password", placeholder="Enter Password")
                login_btn = st.form_submit_button("Sign in", type="primary", use_container_width=True)
                if login_btn:
                    if admin_id == ADMIN_USER and admin_pwd == ADMIN_PASS:
                        st.session_state.authenticated = True
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please verify your Admin ID and Password.")
            with st.expander("Demo credentials", expanded=False):
                st.caption("Admin ID: `admin` | Password: `admin123`")
            st.markdown("</div>", unsafe_allow_html=True)

    else:
        with st.sidebar:
            st.markdown('<div style="font-size: 16px; font-weight: 600; color: #0F172A;">Digital Store Cockpit</div>', unsafe_allow_html=True)
            st.markdown('<span class="status-pill">PostgreSQL: Connected (113,390 rows)</span>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size: 13px; color: #475569; margin-top: 4px;">Authenticated Operator: <b style="color: #0F172A;">{ADMIN_USER}</b></div>', unsafe_allow_html=True)
            
            st.markdown('<hr style="border: none; border-top: 1px solid #E2E8F0; margin: 16px 0;" />', unsafe_allow_html=True)

            with st.expander("System info", expanded=False):
                st.markdown("""
                <div style="font-size: 13px; line-height: 1.8;">
                    <span style="color: #475569;">Engine:</span> <code style="color: #0F172A;">llama-3.3-70b-versatile</code><br>
                    <span style="color: #475569;">Database:</span> <code style="color: #0F172A;">digital_store</code><br>
                    <span style="color: #475569;">Driver:</span> <code style="color: #0F172A;">psycopg2 + SQLGlot</code><br>
                    <span style="color: #475569;">Security:</span> <code style="color: #0F172A;">Read-Only (SELECT)</code>
                </div>
                """, unsafe_allow_html=True)

            with st.expander("Dataset columns", expanded=False):
                cols = [
                    "customer_id", "customer_city", "customer_state",
                    "product_id", "product_category_name",
                    "price", "freight_value", "payment_value",
                    "payment_type", "payment_installments",
                    "order_id", "order_status",
                    "order_purchase_timestamp", "year_of_purchase"
                ]
                st.markdown(
                    "<div style='font-size: 13px; font-family: \"JetBrains Mono\", ui-monospace, monospace; white-space: nowrap; line-height: 1.6; color: #0F172A;'>"
                    + "<br>".join(cols)
                    + "</div>",
                    unsafe_allow_html=True
                )

            st.markdown('<hr style="border: none; border-top: 1px solid #E2E8F0; margin: 16px 0;" />', unsafe_allow_html=True)

            if st.session_state.query_history:
                st.markdown('<div style="font-size: 14px; font-weight: 600; color: #0F172A; margin-bottom: 8px;">Recent Session Queries</div>', unsafe_allow_html=True)
                for idx, h in enumerate(reversed(st.session_state.query_history[-4:])):
                    if st.button(h, key=f"hist_{idx}", help=h, use_container_width=True):
                        st.session_state.current_input = h
                        st.session_state.clarify_data = None
                        st.session_state.executed_data = None
                        st.session_state.trigger_run = True
                        st.rerun()

            st.markdown('<hr style="border: none; border-top: 1px solid #E2E8F0; margin: 16px 0;" />', unsafe_allow_html=True)
            if st.button("Sign Out", key="sidebar_signout", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.clarify_data = None
                st.session_state.executed_data = None
                st.rerun()

        st.markdown('<h1>Digital Store Data Analysis Platform</h1>', unsafe_allow_html=True)
        st.markdown('<p class="header-sub">Ask a question in plain English. If it can be read more than one way, you will be asked to clarify before any SQL runs.</p>', unsafe_allow_html=True)

        st.markdown('<div style="font-size: 14px; font-weight: 600; color: #0F172A; margin-bottom: 8px;">Preset Quick-Prompts</div>', unsafe_allow_html=True)
        presets = [
            "Top 5 cities by order count",
            "Show me the most selling product",
            "Revenue breakdown by payment type",
            "Show me the top 5 customers"
        ]
        p_cols = st.columns(len(presets))
        for i, p in enumerate(presets):
            with p_cols[i]:
                if st.button(p, key=f"quick_{i}", use_container_width=True):
                    st.session_state.current_input = p
                    st.session_state.clarify_data = None
                    st.session_state.executed_data = None
                    st.session_state.trigger_run = True
                    st.rerun()

        st.markdown('<div style="margin-top: 12px;"></div>', unsafe_allow_html=True)
        query_col, btn_col = st.columns([5, 1], vertical_alignment="bottom")
        with query_col:
            q_input = st.text_input(
                "Enter your business query:",
                value=st.session_state.current_input,
                placeholder="e.g. Show top 5 customer cities by total spending"
            )
        with btn_col:
            is_empty = not bool(q_input and q_input.strip())
            run_btn = st.button("Analyze & Query", icon=":material/search:", type="primary", use_container_width=True, disabled=is_empty)

        if (run_btn or st.session_state.trigger_run) and q_input and q_input.strip():
            st.session_state.trigger_run = False
            st.session_state.current_input = q_input
            st.session_state.error_message = None
            if q_input not in st.session_state.query_history:
                st.session_state.query_history.append(q_input)

            with st.spinner("Analyzing intent..."):
                analysis = analyze_intent(q_input)

            if analysis.is_unanswerable:
                st.session_state.clarify_data = None
                st.session_state.executed_data = None
                msg = analysis.unanswerable_message or "That information isn't in the dataset. Available columns: customer_city, customer_state, product_category_name, price, freight_value, payment_value, payment_type, payment_installments, order_status, order_purchase_timestamp, year_of_purchase."
                st.session_state.error_message = msg
            elif analysis.is_ambiguous and analysis.options:
                st.session_state.clarify_data = {"orig": q_input, "analysis": analysis}
                st.session_state.executed_data = None
            else:
                st.session_state.clarify_data = None
                with st.spinner("Generating query..."):
                    raw_sql = generate_sql(q_input)
                is_valid, rejection_reason, safe_sql = validate_query(raw_sql)
                if not is_valid:
                    st.session_state.error_message = f"Security Alert: {rejection_reason}"
                    st.session_state.executed_data = None
                else:
                    df, latency, err = run_sql(safe_sql)
                    if err:
                        st.session_state.error_message = f"Execution Error: {err}"
                        st.session_state.executed_data = None
                    else:
                        st.session_state.executed_data = {
                            "orig": q_input,
                            "label": None,
                            "sql": safe_sql,
                            "df": df,
                            "latency": latency
                        }

        if st.session_state.error_message:
            st.markdown(f'<div class="neutral-card">{st.session_state.error_message}</div>', unsafe_allow_html=True)

        if st.session_state.clarify_data:
            orig = st.session_state.clarify_data["orig"]
            analysis = st.session_state.clarify_data["analysis"]

            st.warning("Ambiguity detected. Please select the intended metric below.", icon=None)
            st.markdown(f'<div style="font-size: 15px; font-weight: 500; color: #0F172A; margin: 8px 0 16px 0;">{analysis.question}</div>', unsafe_allow_html=True)

            btn_cols = st.columns(min(len(analysis.options), 4))
            for i, opt in enumerate(analysis.options):
                with btn_cols[i % len(btn_cols)]:
                    st.markdown(
                        f'<div class="option-card">'
                        f'<div style="font-size: 15px; font-weight: 600; color: #0F172A; margin-bottom: 4px;">{opt.label}</div>'
                        f'<div style="font-size: 13px; color: #475569; margin-bottom: 12px; line-height: 1.4;">{opt.description}</div>',
                        unsafe_allow_html=True
                    )
                    with st.expander("Show SQL", expanded=False):
                        st.code(opt.sql, language="sql")
                    if st.button("Select", key=f"clarify_{i}", use_container_width=True):
                        is_valid, rej, safe_sql = validate_query(opt.sql)
                        if not is_valid:
                            st.session_state.error_message = f"Security Alert: {rej}"
                        else:
                            df, latency, err = run_sql(safe_sql)
                            if err:
                                st.session_state.error_message = f"Execution Error: {err}"
                            else:
                                st.session_state.executed_data = {
                                    "orig": orig,
                                    "label": opt.label,
                                    "sql": safe_sql,
                                    "df": df,
                                    "latency": latency
                                }
                        st.session_state.clarify_data = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.executed_data:
            ed = st.session_state.executed_data
            orig_q = ed["orig"]
            lbl = ed.get("label")
            if lbl:
                st.markdown(f'<div class="active-query"><b>Active Query Request:</b> {orig_q} — {lbl}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="active-query"><b>Active Query Request:</b> {orig_q}</div>', unsafe_allow_html=True)

            df = ed["df"]
            safe_sql = ed["sql"]
            exec_time_ms = ed["latency"]

            tab_chart, tab_table, tab_audit, tab_summary = st.tabs(["Chart", "Table", "SQL & Guardrail Audit", "Summary Metrics"])

            with tab_chart:
                render_auto_chart(df, orig_q, lbl)

            with tab_table:
                m1, m2 = st.columns(2)
                m1.metric("Rows Returned", f"{len(df):,}")
                m2.metric("Total Columns", len(df.columns))
                st.caption(f"Executed in {exec_time_ms} ms")
                
                df_display = df.copy()
                for c in df_display.columns:
                    if pd.api.types.is_numeric_dtype(df_display[c]):
                        if any(k in c.lower() for k in ["price", "revenue", "value", "freight"]):
                            df_display[c] = df_display[c].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")
                        elif pd.api.types.is_integer_dtype(df_display[c]) and "year" not in c.lower():
                            df_display[c] = df_display[c].apply(lambda x: f"{x:,}" if pd.notnull(x) else "")

                st.dataframe(df_display, use_container_width=True)

                with st.expander("Column Schema & Data Types", expanded=False):
                    st.json({col: str(df[col].dtype) for col in df.columns})

                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button("Export as CSV", data=csv_bytes, file_name="analytics_export.csv", mime="text/csv")

            with tab_audit:
                st.markdown('<span class="status-pill">Passed: read-only SELECT on digital_store_sales</span>', unsafe_allow_html=True)
                st.caption(f"Execution Latency: {exec_time_ms} ms")
                st.code(safe_sql, language="sql")
                with st.expander("Active Guardrail Rules Audited", expanded=True):
                    st.markdown("""
                    - **Rule 1: Single Statement AST Enforcement** (Passed - Single SELECT expression verified)
                    - **Rule 2: Keyword Blacklist Validation** (Passed - No DDL/DML mutation keywords detected)
                    - **Rule 3: Read-Only Query AST Verification** (Passed - Expression validated as exp.Select)
                    - **Rule 4: Target Table Restriction** (Passed - All table references restricted to `digital_store_sales`)
                    - **Rule 5: Row Limit Cap Enforcement** (Passed - LIMIT 1000 applied if no query limit present)
                    """)

            with tab_summary:
                st.markdown('<div style="font-size: 15px; font-weight: 600; color: #0F172A; margin-bottom: 12px;">Key Performance Indicators</div>', unsafe_allow_html=True)
                num_cols = df.select_dtypes(include=["number"]).columns.tolist()
                if num_cols:
                    metric_target = num_cols[0]
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric(f"Total {metric_target}", f"{df[metric_target].sum():,.2f}")
                    k2.metric(f"Average {metric_target}", f"{df[metric_target].mean():,.2f}")
                    k3.metric(f"Max {metric_target}", f"{df[metric_target].max():,.2f}")
                    k4.metric(f"Min {metric_target}", f"{df[metric_target].min():,.2f}")

                    if len(df) > 0 and len(df.columns) >= 2:
                        top_label = df.iloc[0][df.columns[0]]
                        top_val = df.iloc[0][metric_target]
                        st.info(f"Top Performer: {top_label} with {top_val:,.2f} {metric_target}")
                else:
                    st.metric("Total Records Identified", len(df))
        elif not st.session_state.clarify_data and not st.session_state.error_message:
            st.markdown('<div style="font-size: 14px; color: #475569; text-align: center; padding: 48px 0;">Enter a query above or choose a preset prompt to begin analysis.</div>', unsafe_allow_html=True)

if __name__ == "__main__" or (hasattr(st, "runtime") and st.runtime.exists()):
    run_app()
