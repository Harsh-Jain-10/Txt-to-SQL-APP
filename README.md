# ⚡ Text-to-SQL Analytics Application & Dashboard

A beginner-friendly, production-ready Python and Streamlit application that converts natural language business queries into valid PostgreSQL queries using Groq LLM inference, executes them against an e-commerce database, and outputs structured data tables and interactive charts.

---

## 🌟 Key Features

- **Interactive Streamlit Web Dashboard (`app.py`)**:
  - Clean, wide-layout user interface with instant natural language query input.
  - Expandable viewer to inspect the generated raw SQL statement.
  - **Structured Tabular Output**: Converts raw SQL tuples into an interactive `pandas.DataFrame` rendered with `st.dataframe`.
  - **Auto-Visualization**: Automatically plots interactive bar charts (`st.bar_chart`) when 2-column categorical/metric data is returned.
- **Direct CLI Text-to-SQL (`generate_sql.py`)**:
  - Concise (< 50 lines), beginner-friendly script for fast query generation and execution.
- **Ambiguity Detection & Clarification Engine (`clarification_engine.py`)**:
  - Uses Pydantic schemas and Groq JSON mode to detect vague phrasing (e.g., "top customers").
  - Prompts users with multiple-choice definitions before query execution.
- **Resilient Model Fallback**:
  - Prioritizes `llama-3.3-70b-versatile` / `llama-3.1-8b-instant`, with graceful fallback to active production models (`openai/gpt-oss-120b`) to prevent 404/rate-limit aborts.

---

## 📂 Project Structure & Code Line Breakdown

```text
├── app.py                  # Streamlit web dashboard with tables & charts
├── generate_sql.py         # Concise (< 50 lines) CLI Text-to-SQL script
├── clarification_engine.py # Interactive ambiguity disambiguation engine
├── test_connection.py      # Script to verify PostgreSQL connectivity
├── .env.example            # Environment variable template
├── .gitignore              # Ignores credentials, venv, and large datasets
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation & setup guide
```

### 🔍 Key Implementation Lines in `app.py`:

| Feature | Key Code Lines in `app.py` | Description |
| :--- | :--- | :--- |
| **LLM Query Generation** | `client.chat.completions.create(...)` | Sends schema prompt to Groq and extracts raw SQL |
| **PostgreSQL Execution** | `conn = psycopg2.connect(...)` & `cur.execute(sql)` | Executes generated SQL query on PostgreSQL |
| **Structured Tabular Output** | `df = pd.DataFrame(rows, columns=columns)` | Maps raw database tuples to structured table |
| **Interactive Data Table** | `st.dataframe(df, use_container_width=True)` | Renders clean, scrollable, interactive table in the UI |
| **Summary Metrics** | `st.metric(label="Total Rows Returned", value=len(df))` | Shows high-impact row count card |
| **Chart Visualization** | `st.bar_chart(chart_df.set_index(chart_df.columns[0]))` | Plots interactive bar chart for 2-column results |
| **Error Handling** | `st.error(f"Error executing query: {e}")` | Catches exceptions and displays clean UI alerts |

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

### 1. Launch the Streamlit Web Dashboard (Recommended)
```bash
streamlit run app.py
```
*Opens automatically in your browser at `http://localhost:8501`.*

### 2. Run Direct CLI Text-to-SQL Query
```bash
python generate_sql.py
```

### 3. Run the Interactive Ambiguity Clarification Engine
```bash
python clarification_engine.py
```

### 4. Verify PostgreSQL Database Connection
```bash
python test_connection.py
```

---

## 📦 Requirements

- `streamlit`
- `pandas`
- `psycopg2-binary`
- `groq`
- `python-dotenv`
- `pydantic`
