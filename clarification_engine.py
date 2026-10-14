import os
import json
import psycopg2
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import List, Optional

# Load environment credentials and configure Groq client
load_dotenv()
client = Groq(api_key=os.getenv("LLM_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# Helper function to call Groq with model fallback
def call_groq(**kwargs):
    for model in [MODEL_NAME, "llama-3.1-8b-instant", "openai/gpt-oss-120b"]:
        try:
            return client.chat.completions.create(model=model, **kwargs)
        except Exception:
            continue
    raise RuntimeError("Unable to complete request with available Groq models.")

# 1. Pydantic schema for structured intent analysis
class ClarificationOption(BaseModel):
    option_id: int
    label: str
    description: str

class IntentResult(BaseModel):
    is_ambiguous: bool
    clarification_question: Optional[str] = None
    options: List[ClarificationOption] = Field(default_factory=list)

# 2. Analyze ambiguity in the question using Groq JSON mode
def analyze_intent(question: str) -> IntentResult:
    prompt = f"""
    Analyze if this e-commerce analytics question is ambiguous.
    Words like 'top', 'best', 'active', or 'valuable' can mean different metrics (e.g. highest spending vs most orders vs total quantity).
    
    Question: "{question}"
    
    Return a strictly valid JSON object matching this schema:
    {{
      "is_ambiguous": true/false,
      "clarification_question": "string or null",
      "options": [
        {{"option_id": 1, "label": "Short label", "description": "Metric definition"}}
      ]
    }}
    """
    
    # Request JSON response from Groq
    response = call_groq(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0
    )
    
    data = json.loads(response.choices[0].message.content)
    return IntentResult(**data)

# 3. Generate and run SQL once intent is clear
def execute_query(final_prompt: str):
    schema = "Table: digital_store_sales. Columns: customer_id, customer_city, price, payment_value, order_id, order_purchase_timestamp"
    
    # Generate raw SQL from the disambiguated prompt
    response = call_groq(
        messages=[
            {"role": "system", "content": f"Return ONLY raw PostgreSQL code. No markdown. Schema:\n{schema}"},
            {"role": "user", "content": f"{final_prompt}. Always add LIMIT 5 unless specified."}
        ],
        temperature=0.0
    )
    sql = response.choices[0].message.content.strip().replace("```sql", "").replace("```", "")
    print(f"\n[Generated SQL]\n{sql}\n")
    
    # Connect to PostgreSQL, execute the query, and display structured row output
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "digital_store"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    cursor = conn.cursor()
    cursor.execute(sql)
    print("[Results - Structured Output]")
    for row in cursor.fetchall():
        print(row)
    cursor.close()
    conn.close()

# 4. Interactive disambiguation loop
def ask_question(question: str):
    print(f"\nUser Query: {question}")
    intent = analyze_intent(question)
    
    # If the user prompt is ambiguous, present multiple-choice clarification options
    if intent.is_ambiguous:
        print(f"\nClarification Needed: {intent.clarification_question}")
        for opt in intent.options:
            print(f"  [{opt.option_id}] {opt.label} ({opt.description})")
            
        choice = input("\nChoose an option number (e.g. 1): ").strip()
        selected = next((o for o in intent.options if str(o.option_id) == choice), intent.options[0])
        resolved_question = f"{question} (defined as: {selected.label} - {selected.description})"
        print(f"\n-> Resolved request: {resolved_question}")
        execute_query(resolved_question)
    else:
        # Prompt is already clear: execute SQL directly
        print("Intent is clear. Generating SQL directly...")
        execute_query(question)

if __name__ == "__main__":
    # Test ambiguous prompt
    ask_question("Show me the top 5 customers")
