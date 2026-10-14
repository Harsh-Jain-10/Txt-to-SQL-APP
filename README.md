# ⚡ Text-to-SQL Analytics Application & Dashboard with Clarification Engine

A beginner-friendly, production-ready Python and Streamlit application that converts natural language business queries into valid PostgreSQL queries using Groq LLM inference, executes them against an e-commerce database, and outputs structured data tables and interactive charts.

---

## 🌟 Key Features

- **Stage 3 Clarification Engine in Streamlit (`app.py`)**:
  - **Pydantic Structured Output**: Defines `ClarificationOption` and `IntentAnalysis` models.
  - **Ambiguity Detection**: Evaluates whether keywords like *"top"*, *"best"*, or *"valuable"* have multiple metrics in the database schema (e.g., total spend vs order count).
  - **Interactive Disambiguation Buttons**: If ambiguous, displays the clarification question and renders interactive option buttons for the user to select.
  - **Intent-Resolved SQL**: Combines the original question with the chosen metric to produce deterministic, accurate SQL.
- **Interactive Tabular Output & Visualizations**:
  - Structured `pandas.DataFrame` rendered via `st.dataframe`.
  - Automatic bar chart visualization (`st.bar_chart`) for 2-column categorical/metric outputs.
  - Expandable SQL code inspection block (`st.code`).
- **Direct CLI Text-to-SQL (`generate_sql.py`)**:
  - Concise (< 50 lines), beginner-friendly script for fast terminal query generation and execution.
- **Standalone Clarification CLI Engine (`clarification_engine.py`)**:
  - Interactive terminal tool for ambiguity detection.
- **Resilient Model Fallback**:
  - Prioritizes `llama-3.3-70b-versatile` / `llama-3.1-8b-instant`, with graceful fallback to active production models (`openai/gpt-oss-120b`) to prevent 404/rate-limit aborts.

---

## 📂 Project Structure & Code Line Breakdown

```text
├── .streamlit/
│   └── config.toml         # Streamlit light theme & server configuration
├── app.py                  # Streamlit dashboard with Stage 3 Clarification Engine (< 120 lines)
├── generate_sql.py         # Concise (< 50 lines) CLI Text-to-SQL script
├── clarification_engine.py # Interactive CLI ambiguity disambiguation engine
├── test_connection.py      # Script to verify PostgreSQL connectivity
├── .env.example            # Environment variable template
├── .gitignore              # Ignores credentials, venv, and large datasets
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation & setup guide
```

### 🔍 Key Implementation Stages in `app.py`:

| Stage | Implementation Details | Description |
| :--- | :--- | :--- |
| **Stage 1: Pydantic Schema** | `ClarificationOption` & `IntentAnalysis` | Validates structured JSON schema from LLM |
| **Stage 2: Ambiguity Detection** | `analyze_intent(question)` | Uses Groq JSON mode (`response_format={"type": "json_object"}`) |
| **Stage 3: Interactive Clarification** | `st.button(opt.label)` | Prompts user with options; combines intent upon click |
| **Stage 4: SQL Generation** | `client.chat.completions.create(...)` | Generates raw PostgreSQL with schema context |
| **Stage 5: Database Execution** | `psycopg2.connect(...)` & `cur.fetchall()` | Executes SQL and loads results into `pandas.DataFrame` |
| **Stage 6: Output & Charts** | `st.dataframe(...)` & `st.bar_chart(...)` | Renders structured data table and interactive bar chart |

---

## 🗄️ Database Schema Context

The application queries the PostgreSQL table **`digital_store_sales`** with the following schema:
- `order_id` (TEXT)
- `customer_id` (TEXT)
- `customer_city` (TEXT)
- `customer_state` (TEXT)
- `product_id` (TEXT)
- `product_category_name` (TEXT)
- `price` (NUMERIC)
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
```

---

## 💻 How to Run

### 1. Launch the Streamlit Web Dashboard
```bash
streamlit run app.py
```
*Opens automatically in your browser at `http://localhost:8501`.*
- Enter an ambiguous query like `"Show me the top 5 customers"` to see the Clarification Engine present multiple-choice metric buttons.
- Select an option to resolve the query, execute the SQL, and view structured tables and charts.

### 2. Run Direct CLI Text-to-SQL Query
```bash
python generate_sql.py
```

### 3. Run the CLI Clarification Engine
```bash
python clarification_engine.py
```

### 4. Verify PostgreSQL Database Connection
```bash
python test_connection.py
```
