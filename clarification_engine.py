import os
import json
import psycopg2
import sqlglot
from sqlglot import exp
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import List, Optional

load_dotenv()
client = Groq(api_key=os.getenv("LLM_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

def call_groq(**kwargs):
    for model in [MODEL_NAME, "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            return client.chat.completions.create(model=model, **kwargs)
        except Exception:
            continue
    raise RuntimeError("Unable to complete request with available Groq models.")

class ClarificationOption(BaseModel):
    label: str
    description: str
    sql: str

class IntentResult(BaseModel):
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
    "- Row limits: Only include LIMIT if explicitly requested by user (e.g. 'top 5') or defaulted as above (TOP 10)."
)

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

def analyze_intent(question: str) -> IntentResult:
    prompt = f"""
    Analyze if this e-commerce analytics question is ambiguous or unanswerable for table digital_store_sales.
    {SCHEMA}
    {METRIC_RULES}

    Classify into:
    1. Unanswerable: requires non-schema columns (age, profit, discount, rating).
    2. Ambiguous: metric, time range, or entity ambiguity. Return real clarification question and 2-4 options with label, description, sql.
    3. Clear: specific metric and dimensions.

    Question: "{question}"

    Return JSON:
    {{
      "is_ambiguous": true/false,
      "is_unanswerable": true/false,
      "unanswerable_message": "string or null",
      "question": "clarification question or null",
      "options": [
        {{"label": "short label", "description": "one sentence description", "sql": "valid SELECT SQL"}}
      ]
    }}
    """
    response = call_groq(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0
    )
    data = json.loads(response.choices[0].message.content)
    res = IntentResult(**data)
    if res.is_ambiguous and res.options:
        valid_opts = []
        for opt in res.options:
            is_valid, _, safe_sql = validate_query(opt.sql)
            if is_valid:
                opt.sql = safe_sql
                valid_opts.append(opt)
        res.options = valid_opts
    return res

def execute_sql(sql: str):
    is_valid, rej, safe_sql = validate_query(sql)
    if not is_valid:
        print(f"Validation failed: {rej}")
        return
    print(f"\n[Executing SQL]\n{safe_sql}\n")
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "digital_store"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = 10000;")
    cursor.execute(safe_sql)
    print("[Results - Structured Output]")
    for row in cursor.fetchall()[:10]:
        print(row)
    cursor.close()
    conn.close()

def generate_and_execute(question: str):
    prompt = f"Return ONLY raw SQL without markdown. {SCHEMA}\n{METRIC_RULES}\nQuestion: {question}"
    response = call_groq(messages=[{"role": "user", "content": prompt}], temperature=0.0)
    sql = response.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    execute_sql(sql)

def ask_question(question: str):
    print(f"\nUser Query: {question}")
    intent = analyze_intent(question)
    if intent.is_unanswerable:
        print(intent.unanswerable_message or "That information isn't in the dataset.")
    elif intent.is_ambiguous and len(intent.options) >= 2:
        print(f"\nClarification Needed: {intent.question}")
        for i, opt in enumerate(intent.options, 1):
            print(f"  [{i}] {opt.label} ({opt.description})")
        choice = input("\nChoose an option number (e.g. 1): ").strip()
        idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(intent.options) else 0
        selected = intent.options[idx]
        print(f"\n-> Selected: {selected.label}")
        # Execute chosen option's SQL as-is without second LLM prompt
        execute_sql(selected.sql)
    else:
        print("Intent is clear. Generating SQL directly...")
        generate_and_execute(question)

if __name__ == "__main__":
    ask_question("Show me the top 5 customers")
