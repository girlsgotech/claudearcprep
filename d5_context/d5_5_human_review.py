# =====================================================================
# HOW TO RUN THIS FILE (VS Code)
#   1. Open the PROJECT ROOT folder (claude-architect-prep) in VS Code.
#   2. Open a terminal (Ctrl+`) and activate the virtual environment:
#        Linux/macOS : source .venv/bin/activate
#        Windows     : .venv\Scripts\Activate.ps1
#   3. From the project root (NOT from inside d5_context), run:
#        python -m d5_context.d5_5_human_review
#   4. Requirements: Python 3.10+, standard library only, no API key.
#      d5_context/ must contain an (empty) __init__.py file.
#   5. Save the file first (Ctrl+S). A dot on the tab means unsaved.
# =====================================================================
"""
Task 5.5  Design human review workflows and confidence calibration
Scenario  6 (Structured Data Extraction)
RUNS: mock (labeled data is hand-built so the numbers are exact; no API call needed)

What this file shows
  1. Aggregate accuracy (97%) hides a weak document type / field.
  2. Field-level confidence must be CALIBRATED on a labeled validation set to pick a threshold.
  3. Check every segment before automating high-confidence extractions.
  4. Stratified random sampling of auto-approved extractions (measure error rate, spot new patterns).
  5. Route low confidence, conflicting sources and unvalidated segments to a limited reviewer queue.
"""
import random

# ------------------------------------------------- 1. AGGREGATE vs SEGMENTS
# (document type, field) -> (items checked, items correct) from a labeled evaluation.
SEGMENTS = {
    ("invoice", "vendor"): (300, 298), ("invoice", "date"): (300, 297), ("invoice", "total"): (300, 296),
    ("receipt", "vendor"): (200, 198), ("receipt", "date"): (200, 197), ("receipt", "total"): (200, 197),
    ("handwritten", "vendor"): (50, 46), ("handwritten", "date"): (50, 38), ("handwritten", "total"): (50, 30),
}


def pct(correct, total):
    return f"{100 * correct / total:.1f}%"


def by_doc_type():
    out = {}
    for (doc, _field), (n, ok) in SEGMENTS.items():
        t, c = out.get(doc, (0, 0))
        out[doc] = (t + n, c + ok)
    return out


# ------------------------------------------------- 2. CALIBRATION
# Labeled validation set, bucketed by the model's STATED field-level confidence:
# (stated confidence, items, items actually correct)
VALIDATION = [(0.95, 400, 396), (0.90, 300, 291), (0.80, 200, 184), (0.70, 100, 80), (0.60, 50, 30)]
TARGET = 0.98       # accuracy we need from auto-accepted extractions


def cumulative(threshold):
    items = [(n, ok) for conf, n, ok in VALIDATION if conf >= threshold]
    n, ok = sum(i[0] for i in items), sum(i[1] for i in items)
    return n, ok


def calibrate(target):
    # EXAM: choose the lowest threshold whose MEASURED accuracy on labeled data meets the target.
    best = None
    for conf, _n, _ok in sorted(VALIDATION):
        n, ok = cumulative(conf)
        if ok / n >= target:
            best = conf
            break
    return best


# ------------------------------------------------- 3. SEGMENT CHECK BEFORE AUTOMATING
# Accuracy of HIGH-confidence (>= threshold) extractions, per document type: (items, correct)
SEGMENT_FLOOR = 0.97     # every segment must reach this before it is automated
HIGH_CONF_BY_TYPE = {"invoice": (500, 495), "receipt": (300, 294), "handwritten": (20, 17)}

# ------------------------------------------------- 4. STRATIFIED SAMPLING
AUTO_APPROVED = {"invoice": 5000, "receipt": 3000, "handwritten": 200}     # population sizes
SAMPLE_ERRORS = {"invoice": 0, "receipt": 1, "handwritten": 5}             # scripted review outcome (of 30 each)
ERROR_PATTERNS = {"receipt": {"format_mismatch": 1}, "handwritten": {"digit_misread": 4, "missing_field": 1}}
KNOWN_PATTERNS = {"format_mismatch", "missing_field"}
TOLERANCE = 0.05


def stratified_sample(population, per_stratum, seed=7):
    rng = random.Random(seed)
    return {s: rng.sample(range(size), min(per_stratum, size)) for s, size in population.items()}


# ------------------------------------------------- 5. ROUTING
THRESHOLD = 0.90                           # from calibrate(TARGET)
VALIDATED_TYPES = {"invoice", "receipt"}   # segments that passed the check in section 3
REVIEW_CAPACITY = 3                        # reviewer slots available today

EXTRACTIONS = [  # id, doc type, field, model confidence, conflict_detected (contradictory source)
    ("e1", "invoice", "total", 0.98, False), ("e2", "invoice", "date", 0.93, False),
    ("e3", "receipt", "total", 0.88, False), ("e4", "handwritten", "total", 0.95, False),
    ("e5", "invoice", "vendor", 0.62, False), ("e6", "receipt", "date", 0.91, True),
    ("e7", "handwritten", "date", 0.55, False), ("e8", "invoice", "date", 0.99, False),
    ("e9", "invoice", "total", 0.97, False), ("e10", "receipt", "vendor", 0.96, False),
]


def route(item):
    _id, doc, _field, conf, conflict = item
    if conflict:
        return "human", "conflicting source"          # EXAM: ambiguous/contradictory -> human
    if doc not in VALIDATED_TYPES:
        return "human", "segment not validated"       # EXAM: high confidence alone is not enough
    if conf < THRESHOLD:
        return "human", "low confidence"
    return "auto", "confident, validated segment"


def main():
    print("== 1. Aggregate accuracy hides weak segments ==")
    total_n = sum(n for n, _ in SEGMENTS.values())
    total_ok = sum(ok for _, ok in SEGMENTS.values())
    print(f"overall accuracy: {pct(total_ok, total_n)} ({total_ok}/{total_n}) -> looks ready to automate")
    print("by document type: " + ", ".join(f"{d} {pct(c, t)}" for d, (t, c) in by_doc_type().items()))
    (doc, field), (n, ok) = min(SEGMENTS.items(), key=lambda kv: kv[1][1] / kv[1][0])
    print(f"weakest segment: {doc}/{field} {pct(ok, n)} ({ok}/{n}), hidden by the overall number")

    print("\n== 2. Calibrate field-level confidence on a labeled validation set ==")
    print("stated conf | items | actual accuracy | accuracy if auto-accept >= conf")
    for conf, n, ok in VALIDATION:
        cn, cok = cumulative(conf)
        print(f"{conf:>11.2f} | {n:>5} | {pct(ok, n):>15} | {pct(cok, cn):>7} ({cn} items)")
    t = calibrate(TARGET)
    cn, cok = cumulative(t)
    print(f"RIGHT: target {TARGET:.0%} -> threshold {t:.2f}; automates {cn} of 1050 ({pct(cn, 1050)}), "
          f"measured accuracy {pct(cok, cn)}")
    wn, wok = cumulative(0.60)
    print(f"WRONG: trust every score (threshold 0.60) -> accuracy {pct(wok, wn)}, misses the {TARGET:.0%} target")

    print("\n== 3. Check every segment before automating ==")
    tot = sum(v[0] for v in HIGH_CONF_BY_TYPE.values())
    good = sum(v[1] for v in HIGH_CONF_BY_TYPE.values())
    for d, (n, ok) in HIGH_CONF_BY_TYPE.items():
        verdict = "ok to automate" if ok / n >= SEGMENT_FLOOR else "KEEP HUMAN REVIEW"
        print(f"{d:<12} high-confidence accuracy {pct(ok, n):>6} ({ok}/{n}) -> {verdict}")
    print(f"overall high-confidence accuracy {pct(good, tot)} passes {TARGET:.0%}, "
          "but handwritten fails: the aggregate would hide it")

    print("\n== 4. Stratified random sampling of auto-approved extractions ==")
    N = sum(AUTO_APPROVED.values())
    print("population: " + ", ".join(f"{k} {v}" for k, v in AUTO_APPROVED.items()) + f" (N={N})")
    exp = 100 * AUTO_APPROVED["handwritten"] / N
    miss = (1 - AUTO_APPROVED["handwritten"] / N) ** 100
    print(f"WRONG simple random sample of 100: ~{exp:.1f} handwritten items expected, "
          f"~{miss:.1%} chance of none at all")
    sample = stratified_sample(AUTO_APPROVED, 30)
    print("RIGHT stratified sample: " + ", ".join(f"{k} {len(v)}" for k, v in sample.items()))
    for stratum, errs in SAMPLE_ERRORS.items():
        rate = errs / len(sample[stratum])
        flag = "  <- above tolerance, investigate" if rate > TOLERANCE else ""
        print(f"{stratum:<12} error rate {rate:>5.1%} ({errs}/{len(sample[stratum])}){flag}")
    novel = sorted({p for pats in ERROR_PATTERNS.values() for p in pats} - KNOWN_PATTERNS)
    print(f"novel error pattern(s) found by sampling: {novel}")

    print("\n== 5. Route to human review, prioritize limited capacity ==")
    queue = []
    for item in EXTRACTIONS:
        dest, reason = route(item)
        print(f"{item[0]:<4}{item[1]:<12}{item[2]:<7} conf {item[3]:.2f} -> {dest:<5} ({reason})")
        if dest == "human":
            queue.append(item)
    auto = len(EXTRACTIONS) - len(queue)
    print(f"auto-approved {auto} of {len(EXTRACTIONS)}, {len(queue)} need a human, capacity today {REVIEW_CAPACITY}")
    queue.sort(key=lambda i: (not i[4], i[3]))      # conflicts first, then lowest confidence
    print("review today: " + ", ".join(i[0] for i in queue[:REVIEW_CAPACITY]) +
          " | deferred: " + ", ".join(i[0] for i in queue[REVIEW_CAPACITY:]))


if __name__ == "__main__":
    main()