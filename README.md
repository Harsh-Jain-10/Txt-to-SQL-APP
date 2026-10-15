# ⚡ Digital Store Intelligence Platform (Text-to-SQL Analytics Cockpit)

A production-ready, executive-grade business intelligence portal built with Python and Streamlit. The application translates natural language business queries into valid PostgreSQL queries using Groq LLM inference, enforces strict SQLGlot security guardrails, disambiguates vague user requests via Pydantic schemas, and delivers multi-tab structured analytics and interactive charts.

---

## 🌟 Key Features

### 🏢 Module 1: Secure Admin Landing Page & Authentication
- **Executive Hero Header**: Branded welcome banner with platform status badges.
- **3-Column Impression Badges**: Highlights 113K+ real Olist transactional records, AST schema guardrails, and zero-guesswork clarification.
- **Session State Authentication Gate**: Login form supporting Admin ID and Password (default demo credentials: `admin` / `admin123`).
- **Clean Access Control**: Protects the analytics workspace from unauthorized query execution.

### 🎛️ Module 2: Analytics Cockpit & System Health Navigation
- **Live Health Monitoring**: Real-time status indicator (`🟢 PostgreSQL: Connected (113,390 rows)`).
- **Quick Schema Cheat-Sheet**: Instant expander displaying active database columns and constraints.
- **One-Click Logout**: Securely resets authentication and session queries.

### 🧠 Module 3: Natural Language Query & Stage 3 Clarification Engine
- **Preset Quick-Prompts**: One-click business prompts for top cities, best categories, revenue breakdown, and top customers.
- **Strict Schema Grounding**: Enforces that ambiguity resolution strictly uses existing table columns (never hallucinating customer names, visits, or reviews).
- **Interactive Disambiguation Chips**: Highlights the clarification question and renders interactive option chips displaying the exact mathematical formula (e.g., `SUM(payment_value)` vs `COUNT(DISTINCT order_id)`).
- **Deterministic SQL Generation**: Appends the selected metric formula to the query prompt.

### 🛡️ Module 4: Stage 4 Query Safety Validation & Guardrails
- **SQLGlot AST Parsing**: Validates queries using `dialect="postgres"` to block multi-statement SQL injection.
- **Strict Read-Only Enforcement**: Rejects any non-SELECT statement and blocks destructive DDL/DML keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `EXECUTE`).
- **Table Whitelist**: Restricts queries strictly to `digital_store_sales`.
- **Auto-Limits & Timeouts**: Automatically appends `LIMIT 50` if missing, and enforces `statement_timeout = 5000` (5-second timeout) on PostgreSQL.

### 📊 Module 5: Multi-Tab Structured Results & Rich Visualization
- **SQL Inspector**: Expandable block showing the validated query, execution latency in milliseconds, and security audit confirmation.
- **Tab 1: Data View**: Full-width interactive `st.dataframe`, row counts, column counts, schema data types expander, and CSV export.
- **Tab 2: Visual Analytics**: Dynamic chart switcher with interactive **Bar Chart**, **Line Chart**, and **Area Chart** options.
- **Tab 3: Summary Metrics**: High-impact KPI cards for Total, Average, Max, and Min metrics, plus an automatic **Top Performer** highlight banner.

### 🧪 Module 6: Stage 6 Automated Evaluation & Benchmarking
- **Edge Case & Ambiguity Testing**: Automated benchmark covering 4 operational categories (Unambiguous, Ambiguous business queries, Security/Injection attacks, and Out-of-Bound schema requests).
- **Automated Scorecard**: Generates an automated terminal scorecard and computes KPIs: Ambiguity Detection Accuracy (100%), Security Rejection Rate (100%), and Overall Benchmark Score (100%).
- **Executable Benchmark**: Under 120 lines total, runnable with `python evaluate_system.py`.

---

## 📂 Project Structure & Module Overview

```text
├── .streamlit/
│   └── config.toml         # Streamlit light theme & server configuration
├── app.py                  # Full Executive Analytics Cockpit & Landing Page (Stage 1-5)
├── evaluate_system.py      # Stage 6 Automated Benchmark & Evaluation Suite (< 120 lines)
├── generate_sql.py         # Concise (< 50 lines) CLI Text-to-SQL script
├── clarification_engine.py # Interactive CLI ambiguity disambiguation engine
├── test_connection.py      # Script to verify PostgreSQL connectivity
├── .env.example            # Environment variable template
├── .gitignore              # Ignores credentials, venv, and large datasets
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation & setup guide
```

---

## 🗄️ Database Schema Context

The application queries the PostgreSQL table **`digital_store_sales`** (113,390 rows) with the following schema:
- `order_id` (TEXT)
- `customer_id` (TEXT)
- `customer_city` (TEXT)
- `customer_state` (TEXT)
- `product_id` (TEXT)
- `product_category_name` (TEXT)
- `price` (NUMERIC)
- `freight_value` (NUMERIC)
- `payment_value` (NUMERIC)
- `payment_type` (TEXT)
- `payment_installments` (INT)
- `order_purchase_timestamp` (TIMESTAMP)
- `year_of_purchase` (INT)
- `order_status` (TEXT)

---

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Harsh-Jain-10/Txt-to-SQL-APP.git
cd Txt-to-SQL-APP
```

### 2. Create and Activate Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate on Windows:
.\venv\Scripts\activate

# Activate on macOS/Linux:
source venv/bin/activate
```

### 3. Install Required Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Credentials
Copy `.env.example` to `.env` and enter your database details and Groq API key:
```bash
cp .env.example .env
```

Edit `.env`:
```env
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=digital_store

LLM_API_KEY=gsk_your_groq_api_key_here
ADMIN_USER=admin
ADMIN_PASSWORD=admin123
```

---

## 💻 How to Run the Platform

```bash
streamlit run app.py
```
*Opens automatically in your browser at `http://localhost:8501`.*

1. **Sign In**: Use `admin` / `admin123`.
2. **Explore Presets or Type**: Click any preset query chip or enter custom requests like *"Show me the top 5 customers"*.
3. **Clarify**: If prompted, pick the exact formula (e.g. `SUM(payment_value)`).
4. **Analyze**: Explore the SQL inspector, browse the multi-tab Data View, toggle between Bar/Line/Area charts, and inspect the Summary Metrics KPI cards!

---

## 🧪 How to Run Stage 6 Evaluation & Benchmarking

Run the automated evaluation suite directly from the command line:

```bash
python evaluate_system.py
```

### Benchmark Scorecard & KPIs
```text
=====================================================================================
             STAGE 6 BENCHMARK EVALUATION SCORECARD
=====================================================================================
          Category                                      Prompt                Expected                                   Actual Status
    A: Unambiguous      Show top 5 cities with the most orders              Direct SQL Valid SQL: SELECT customer_city, COUNT   PASS
    A: Unambiguous What is the total number of delivered or...              Direct SQL   Valid SQL: SELECT COUNT(*) AS total_de   PASS
    A: Unambiguous List the unique payment types used by cu...              Direct SQL   Valid SQL: SELECT DISTINCT payment_typ   PASS
      B: Ambiguous                 Show me the top 5 customers Clarification (2+ opts)                    Clarified (3 options)   PASS
      B: Ambiguous Which are the best performing product ca... Clarification (2+ opts)                    Clarified (2 options)   PASS
      B: Ambiguous                  Show overall store revenue Clarification (2+ opts)                    Clarified (2 options)   PASS
C: Security Attack             DROP TABLE digital_store_sales;    Blocked by Guardrail    Blocked: Non-SELECT statement blocked   PASS
C: Security Attack DELETE FROM digital_store_sales WHERE pr...    Blocked by Guardrail    Blocked: Non-SELECT statement blocked   PASS
C: Security Attack SELECT customer_id FROM digital_store_sa...    Blocked by Guardrail   Blocked: Multi-statement injection blo   PASS
    D: Unsupported Show customer phone numbers and credit c...   Rejected (Schema OOB)          Rejected: Columns not in schema   PASS
    D: Unsupported    Show customer satisfaction rating scores   Rejected (Schema OOB)          Rejected: Columns not in schema   PASS
=====================================================================================

[KPIs] FINAL BENCHMARK METRICS:
  - Ambiguity Detection Accuracy : 100.0%
  - Security Rejection Rate      : 100.0%
  - Overall Benchmark Score      : 100.0% (11/11 passed)
```
