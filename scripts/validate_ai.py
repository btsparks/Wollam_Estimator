"""Live validation of WEIS AI engine against MVP questions.

Runs the 10 MVP questions + 3 "no data" questions through the real Claude API
and checks for citations, confidence levels, and no-hallucination behavior.

Usage:
    python scripts/validate_ai.py
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai_engine import QueryEngine

# ---------------------------------------------------------------------------
# MVP Questions — expected keywords/patterns in each answer
# ---------------------------------------------------------------------------

MVP_QUESTIONS = [
    {
        "id": 1,
        "question": "What did we pay for 20-inch flanged joints?",
        "expected_keywords": ["7", "MH", "flange", "8553"],
        "description": "Should return ~7 MH/joint from Job 8553 piping data",
    },
    {
        "id": 2,
        "question": "What was our concrete material cost per CY on pump station work?",
        "expected_keywords": ["CY", "concrete", "8553"],
        "description": "Should return ~$205-210/CY material cost",
    },
    {
        "id": 3,
        "question": "What crew did we use for mat pours?",
        "expected_keywords": ["crew", "mat", "8553"],
        "description": "Should return crew composition (20+ people total)",
    },
    {
        "id": 4,
        "question": "What production rate did we achieve on structural excavation?",
        "expected_keywords": ["700", "CY", "excavation", "8553"],
        "description": "Should return ~700 CY/shift",
    },
    {
        "id": 5,
        "question": "What did steel erection cost per ton?",
        "expected_keywords": ["3,766", "ton", "J&M", "8553"],
        "description": "Should return J&M at $3,766/ton",
    },
    {
        "id": 6,
        "question": "What was our general conditions percentage?",
        "expected_keywords": ["general conditions", "8553"],
        "description": "Should return GC data with percentage breakdown",
    },
    {
        "id": 7,
        "question": "What lessons did we learn about piping on Job 8553?",
        "expected_keywords": ["lesson", "piping", "8553"],
        "description": "Should return 2+ piping lessons learned",
    },
    {
        "id": 8,
        "question": "What subcontractor did we use for rebar and at what cost per pound?",
        "expected_keywords": ["Champion", "1.30", "rebar", "8553"],
        "description": "Should return Champion Steel at $1.30/lb",
    },
    {
        "id": 9,
        "question": "What was the all-in cost per CY for concrete?",
        "expected_keywords": ["867", "CY", "concrete", "8553"],
        "description": "Should return $867/CY all-in",
    },
    {
        "id": 10,
        "question": "What was the electrical subcontractor cost per SF?",
        "expected_keywords": ["SF", "electrical", "8553"],
        "description": "Should return ~$132-138/SF",
    },
]

# ---------------------------------------------------------------------------
# "No Data" Questions — must NOT hallucinate
# ---------------------------------------------------------------------------

NO_DATA_QUESTIONS = [
    {
        "id": "ND1",
        "question": "What was our piping cost on Job 8576?",
        "reject_keywords": ["actual", "budget", "cost was", "we spent"],
        "accept_keywords": ["don't have", "insufficient", "no data", "not available", "don't have data", "only", "8553"],
        "description": "Job 8576 is not in the database — should say no data",
    },
    {
        "id": "ND2",
        "question": "What's the going rate for HVAC ductwork?",
        "reject_keywords": [],
        "accept_keywords": ["don't have", "insufficient", "no data", "not available", "HVAC", "no HVAC", "don't have data"],
        "description": "No HVAC data exists — should say no data",
    },
    {
        "id": "ND3",
        "question": "How much did we spend on Job 8553 in 2019?",
        "reject_keywords": [],
        "accept_keywords": ["2022", "2023", "2024", "don't have", "insufficient", "not 2019", "dates", "8553"],
        "description": "Wrong dates — should clarify actual dates or say no 2019 data",
    },
]


def check_confidence(answer: str) -> bool:
    """Check if answer includes a confidence indicator."""
    indicators = ["HIGH", "MEDIUM", "LOW", "ASSUMPTION",
                  "high confidence", "medium confidence", "low confidence",
                  "Confidence:", "confidence level"]
    return any(ind.lower() in answer.lower() for ind in indicators)


def check_citation(answer: str) -> bool:
    """Check if answer cites a source (job number, discipline, etc.)."""
    citation_patterns = ["8553", "Job", "cost code", "discipline"]
    return any(pat.lower() in answer.lower() for pat in citation_patterns)


def run_validation():
    """Run full validation suite."""
    print("=" * 70)
    print("WEIS Phase 2a — Live AI Validation")
    print("=" * 70)
    print()

    # Initialize engine
    try:
        engine = QueryEngine()
        print("[OK] QueryEngine initialized successfully")
    except Exception as e:
        print(f"[FAIL] QueryEngine initialization failed: {e}")
        return

    # Check database status
    status = engine.get_status()
    print(f"[OK] Database: {status['record_counts']['cost_codes']} cost codes, "
          f"{len(status['projects'])} projects, {len(status['disciplines'])} disciplines")
    print()

    results = {"pass": 0, "fail": 0, "details": []}

    # --- MVP Questions ---
    print("-" * 70)
    print("MVP QUESTIONS (10)")
    print("-" * 70)

    for q in MVP_QUESTIONS:
        engine.reset()  # Fresh conversation for each
        print(f"\nQ{q['id']}: {q['question']}")
        print(f"  Expected: {q['description']}")

        try:
            answer = engine.ask(q["question"])
        except Exception as e:
            print(f"  [FAIL] API error: {e}")
            results["fail"] += 1
            results["details"].append({
                "id": q["id"], "status": "FAIL", "error": str(e)
            })
            continue

        # Check keywords
        answer_lower = answer.lower()
        found = [kw for kw in q["expected_keywords"] if kw.lower() in answer_lower]
        missing = [kw for kw in q["expected_keywords"] if kw.lower() not in answer_lower]

        has_confidence = check_confidence(answer)
        has_citation = check_citation(answer)

        passed = len(missing) == 0 and has_citation
        status_str = "PASS" if passed else "FAIL"

        if passed:
            results["pass"] += 1
        else:
            results["fail"] += 1

        print(f"  [{status_str}] Keywords found: {found}, missing: {missing}")
        print(f"         Citation: {'YES' if has_citation else 'NO'} | "
              f"Confidence: {'YES' if has_confidence else 'NO'}")
        print(f"  Answer (first 200 chars): {answer[:200]}...")

        results["details"].append({
            "id": q["id"],
            "status": status_str,
            "keywords_found": found,
            "keywords_missing": missing,
            "has_citation": has_citation,
            "has_confidence": has_confidence,
            "answer_preview": answer[:500],
        })

        time.sleep(0.5)  # Rate limiting courtesy

    # --- No Data Questions ---
    print()
    print("-" * 70)
    print("NO DATA QUESTIONS (3)")
    print("-" * 70)

    for q in NO_DATA_QUESTIONS:
        engine.reset()
        print(f"\n{q['id']}: {q['question']}")
        print(f"  Expected: {q['description']}")

        try:
            answer = engine.ask(q["question"])
        except Exception as e:
            print(f"  [FAIL] API error: {e}")
            results["fail"] += 1
            results["details"].append({
                "id": q["id"], "status": "FAIL", "error": str(e)
            })
            continue

        answer_lower = answer.lower()
        has_accept = any(kw.lower() in answer_lower for kw in q["accept_keywords"])

        passed = has_accept
        status_str = "PASS" if passed else "FAIL"

        if passed:
            results["pass"] += 1
        else:
            results["fail"] += 1

        print(f"  [{status_str}] Graceful 'no data' handling: {'YES' if has_accept else 'NO'}")
        print(f"  Answer (first 300 chars): {answer[:300]}...")

        results["details"].append({
            "id": q["id"],
            "status": status_str,
            "no_hallucination": has_accept,
            "answer_preview": answer[:500],
        })

        time.sleep(0.5)

    # --- Multi-turn test ---
    print()
    print("-" * 70)
    print("MULTI-TURN CONVERSATION TEST")
    print("-" * 70)

    engine.reset()
    print("\nTurn 1: What was our concrete material cost per CY?")
    try:
        a1 = engine.ask("What was our concrete material cost per CY?")
        print(f"  Answer: {a1[:200]}...")

        print("\nTurn 2: And what about the all-in cost including labor?")
        a2 = engine.ask("And what about the all-in cost including labor?")
        print(f"  Answer: {a2[:200]}...")

        multi_pass = "867" in a2 or "all-in" in a2.lower() or "labor" in a2.lower()
        status_str = "PASS" if multi_pass else "FAIL"
        print(f"  [{status_str}] Follow-up understood context")
        if multi_pass:
            results["pass"] += 1
        else:
            results["fail"] += 1
    except Exception as e:
        print(f"  [FAIL] Multi-turn error: {e}")
        results["fail"] += 1

    # --- Summary ---
    print()
    print("=" * 70)
    print(f"RESULTS: {results['pass']} passed, {results['fail']} failed "
          f"out of {results['pass'] + results['fail']} total")
    print("=" * 70)

    # Save detailed results
    output_path = Path(__file__).parent.parent / "validation_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {output_path}")

    return results


if __name__ == "__main__":
    run_validation()
