import os, sys, time, csv, psycopg2
from dotenv import load_dotenv

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import analyze_intent, generate_sql, validate_query, get_db_connection

load_dotenv()

def normalize_rows(rows):
    # Round floats / Decimals for numeric comparison
    norm = []
    for row in rows:
        norm_row = []
        for val in row:
            if hasattr(val, "as_tuple"): # Decimal
                norm_row.append(round(float(val), 2))
            elif isinstance(val, float):
                norm_row.append(round(val, 2))
            else:
                norm_row.append(val)
        norm.append(tuple(norm_row))
    return norm

def main():
    csv_path = os.path.join(os.path.dirname(__file__), "eval_questions.csv")
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        questions = list(reader)

    conn = get_db_connection()
    cur = conn.cursor()

    total_clear = 0
    clear_accurate = 0
    total_ambiguous = 0
    true_ambiguous = 0
    total_flagged_ambiguous = 0
    total_unanswerable = 0
    unanswerable_refused = 0
    total_injection = 0
    injection_blocked = 0

    print(f"Running evaluation on {len(questions)} test questions...")

    for row in questions:
        q = row["question"].strip()
        cat = row["category"].strip()
        gold_sql = row.get("gold_sql", "").strip()

        if cat == "injection":
            total_injection += 1
            # Step 1: Direct validation check
            is_valid, rej, _ = validate_query(q)
            if not is_valid:
                injection_blocked += 1
            else:
                # Step 2: Try pipeline
                intent = analyze_intent(q)
                if intent.is_unanswerable or not intent.is_ambiguous:
                    raw_sql = generate_sql(q)
                    is_safe, _, _ = validate_query(raw_sql)
                    if not is_safe:
                        injection_blocked += 1
                else:
                    injection_blocked += 1

        elif cat == "unanswerable":
            total_unanswerable += 1
            intent = analyze_intent(q)
            if intent.is_unanswerable:
                unanswerable_refused += 1

        elif cat == "ambiguous":
            total_ambiguous += 1
            intent = analyze_intent(q)
            if intent.is_ambiguous and len(intent.options) >= 2:
                true_ambiguous += 1
                total_flagged_ambiguous += 1

        elif cat == "clear":
            total_clear += 1
            intent = analyze_intent(q)
            if intent.is_ambiguous:
                total_flagged_ambiguous += 1
            elif not intent.is_unanswerable:
                raw_sql = generate_sql(q)
                is_valid, _, safe_sql = validate_query(raw_sql)
                if is_valid:
                    try:
                        cur.execute(safe_sql)
                        actual_res = normalize_rows(cur.fetchall())
                        cur.execute(gold_sql)
                        gold_res = normalize_rows(cur.fetchall())
                        if actual_res == gold_res or set(actual_res) == set(gold_res):
                            clear_accurate += 1
                        else:
                            print(f"Mismatch for: {q}\nActual SQL: {safe_sql}\nGold SQL: {gold_sql}", flush=True)
                    except Exception as e:
                        print(f"Error executing clear query '{q}': {e}", flush=True)

    cur.close()
    conn.close()

    acc_clear = (clear_accurate / total_clear * 100) if total_clear else 0.0
    prec_amb = (true_ambiguous / total_flagged_ambiguous * 100) if total_flagged_ambiguous else 0.0
    rec_amb = (true_ambiguous / total_ambiguous * 100) if total_ambiguous else 0.0
    ref_unans = (unanswerable_refused / total_unanswerable * 100) if total_unanswerable else 0.0
    blk_inj = (injection_blocked / total_injection * 100) if total_injection else 0.0

    print("\n" + "=" * 65)
    print("5-LINE EVALUATION SUMMARY TABLE")
    print("=" * 65)
    print(f"Execution Accuracy (Clear Questions)  : {acc_clear:5.1f}%  ({clear_accurate}/{total_clear})")
    print(f"Clarification Precision               : {prec_amb:5.1f}%  ({true_ambiguous}/{total_flagged_ambiguous})")
    print(f"Clarification Recall                  : {rec_amb:5.1f}%  ({true_ambiguous}/{total_ambiguous})")
    print(f"Unanswerable-Refusal Rate             : {ref_unans:5.1f}%  ({unanswerable_refused}/{total_unanswerable})")
    print(f"Injection Block Rate                  : {blk_inj:5.1f}%  ({injection_blocked}/{total_injection})")
    print("=" * 65)

if __name__ == "__main__":
    main()
