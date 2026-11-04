"""Evaluation harness: adaptive DiagnosticAgent vs FixedCheckBaseline.

Runs BOTH methods on the SAME labelled synthetic cases inside a fresh temporary
SQLite DB, so no learning state or persisted traces leak between runs and the
user's real database is never touched by an evaluation run.

Metric definitions (also written into the report):
  accuracy            : primary_category == ground_truth, over all test cases.
                        For cases whose true label is 'inconclusive', a
                        prediction counts as correct if the classification is
                        inconclusive/requires_further_investigation AND no
                        primary category was asserted.
  macro_f1            : unweighted mean of per-category F1 over categories that
                        appear in the ground truth (predicted 'None' excluded).
  abstention_correct  : % of truly-inconclusive cases returned as
                        inconclusive / requires_further_investigation.
  false_confident     : % of truly-inconclusive cases answered with
                        'confirmed' or 'probable' + a primary category.
  avg_checks          : mean number of executed tool steps per case
                        (not_applicable skips are not counted as checks).
  unnecessary_checks  : checks executed AFTER evidence was already sufficient
                        for the final classification (agent: steps after the
                        step where should_stop() first became true; baseline:
                        every step after confidence threshold would have been
                        reached). Averaged per case.
  traceability        : share of diagnoses whose supporting-evidence ids all
                        resolve to stored evidence rows (both methods persist
                        full artefacts during eval).
  conflict_detection  : among cases containing a planted conflicting-evidence
                        template, share where >=1 'conflicting' evidence item
                        was recorded.

A fixed-seed train/test split is used when a learning experiment is requested;
plain method comparison uses the whole held-out set (no training happens in it).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import models
from app.agent.agent import DiagnosticAgent
from app.agent.baseline import FixedCheckBaseline
from app.core import db as dbmod
from app.data.seed_rules import seed_rules_if_empty
from app.data.synthetic_generator import SyntheticDataset
from app.services.intake import build_complaint
from app.evaluation.metrics import classification_metrics, error_analysis, assertion_calibration
from app.evaluation.dataset_audit import audit_dataset

ABSTAIN = ("inconclusive", "requires_further_investigation")
REPORT_DIR = os.environ.get('EV_REPORT_DIR') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports")


def _fresh_conn(path: str) -> sqlite3.Connection:
    conn = dbmod.connect(path)
    dbmod.init_db(conn)
    dbmod.sync_config_tables(conn)
    seed_rules_if_empty(conn)
    return conn


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _score(results: List[Dict[str, Any]], labels: List[str]) -> Dict[str, Any]:
    n = len(results)
    if n == 0:
        return {}
    correct = 0
    abstain_ok = abstain_total = false_conf = 0
    checks_sum = unnec_sum = 0
    trace_ok = trace_total = 0
    conflict_ok = conflict_total = 0
    per_cat: Dict[str, Dict[str, int]] = {c: {"total": 0, "correct": 0}
                                          for c in labels}
    for r in results:
        gt = r["ground_truth"]
        pred = r["primary_category"]
        cls = r["classification"]
        ok = False  # reset every iteration (was stale for inconclusive cases)
        if gt == "inconclusive":
            abstain_total += 1
            if cls in ABSTAIN and pred is None:
                abstain_ok += 1
                correct += 1
            elif cls in ("confirmed", "probable") and pred is not None:
                false_conf += 1
        else:
            ok = (pred == gt)
            if ok:
                correct += 1
        per_cat.setdefault(gt, {"total": 0, "correct": 0})
        per_cat[gt]["total"] += 1
        if ok or (gt == "inconclusive" and cls in ABSTAIN and pred is None):
            per_cat[gt]["correct"] += 1
        checks_sum += r["checks_run"]
        unnec_sum += r.get("unnecessary_checks", 0)
        trace_total += 1
        if r.get("traceable", False):
            trace_ok += 1
        if r.get("had_planted_conflict"):
            conflict_total += 1
            if r.get("found_conflict"):
                conflict_ok += 1
    return {
        "n_cases": n,
        "accuracy_pct": round(100.0 * correct / n, 2),
        "abstention_correct_pct": (round(100.0 * abstain_ok / abstain_total, 2)
                                   if abstain_total else None),
        "truly_inconclusive_cases": abstain_total,
        "false_confident_pct": (round(100.0 * false_conf / abstain_total, 2)
                                if abstain_total else None),
        "avg_checks_per_case": round(checks_sum / n, 2),
        "avg_unnecessary_checks": round(unnec_sum / n, 2),
        "traceability_pct": round(100.0 * trace_ok / trace_total, 2),
        "conflict_detection_pct": (round(100.0 * conflict_ok / conflict_total, 2)
                                   if conflict_total else None),
        "planted_conflict_cases": conflict_total,
        "calibration": _calibration(results),
        "per_category_accuracy": {
            c: round(100.0 * v["correct"] / v["total"], 1) if v["total"] else None
            for c, v in per_cat.items()},
        **classification_metrics(results, labels),
        "error_analysis": error_analysis(results),
        "assertion_calibration": assertion_calibration(results),
        "heuristic_assertion_calibration": assertion_calibration(results, 'evidence_strength'),
    }


CAL_BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]


def _calibration(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Is the confidence score meaningful? Over cases with a true root cause, compare
    the confidence with how often the leading hypothesis was actually right.
    ECE = sum_b (n_b/N) * |accuracy_b - mean_confidence_b| (lower is better).
    """
    rows = [r for r in results if r["ground_truth"] != "inconclusive"]
    n = len(rows)
    if not n:
        return {}
    bins, ece = [], 0.0
    for lo, hi in CAL_BINS:
        b = [r for r in rows if lo <= r["evidence_strength"] < hi]
        if not b:
            bins.append({"range": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": 0,
                         "mean_confidence": None, "accuracy_pct": None})
            continue
        conf = sum(r["evidence_strength"] for r in b) / len(b)
        acc = sum(1 for r in b if r["leading_hypothesis"] == r["ground_truth"]) / len(b)
        ece += len(b) / n * abs(acc - conf)
        bins.append({"range": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(b),
                     "mean_confidence": round(conf, 3),
                     "accuracy_pct": round(100 * acc, 1)})
    right = [r["evidence_strength"] for r in rows
             if r["leading_hypothesis"] == r["ground_truth"]]
    wrong = [r["evidence_strength"] for r in rows
             if r["leading_hypothesis"] != r["ground_truth"]]
    return {
        "n_cases": n,
        "ece": round(ece, 4),
        "mean_confidence_when_correct": round(sum(right) / len(right), 3) if right else None,
        "mean_confidence_when_wrong": round(sum(wrong) / len(wrong), 3) if wrong else None,
        "bins": bins,
    }


def run_method(conn: sqlite3.Connection, method: str, dataset: SyntheticDataset,
               items: Optional[List[Dict[str, Any]]] = None,
               ) -> tuple[List[Dict[str, Any]], float]:
    results: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    agent = DiagnosticAgent(conn) if method == "adaptive" else FixedCheckBaseline(conn)
    for item in (items if items is not None else dataset.complaints()):
        complaint = build_complaint(dict(item["payload"]))
        run = agent.run(complaint)
        diag = run.diagnosis
        executed_steps = [s for s in run.trace
                          if s.result.get("status") != "not_applicable"]
        # Persist the actual run for BOTH methods, then validate real foreign links.
        from app.services.diagnosis import diagnose_and_persist
        out = diagnose_and_persist(conn, complaint, agent_run=run)
        stored = conn.execute('SELECT supporting_evidence_ids_json FROM diagnoses WHERE id=?', (out['diagnosis_id'],)).fetchone()
        ids = json.loads(stored['supporting_evidence_ids_json'])
        actual = {r['id'] for r in conn.execute('SELECT id FROM case_evidence WHERE case_id=?', (out['case_id'],))}
        traceable = set(ids) <= actual and (not diag.primary_category or bool(ids))
        found_conflict = any(e.kind == "conflicting" for e in run.state.evidence)
        # unnecessary checks: for adaptive, steps after the loop would already
        # have stopped (only possible for max_steps-exhausted runs); for the
        # baseline, every executed step beyond the point where the adaptive
        # stop condition first held on the same trace prefix.
        unnec = _count_unnecessary(conn, run, method)
        results.append({
            "scenario_id": item["scenario_id"],
            "ground_truth": item["ground_truth"],
            "secondary": item["secondary"],
            "classification": diag.classification,
            "primary_category": diag.primary_category,
            "leading_hypothesis": diag.primary_category or diag.leading_hypothesis,
            "contributing": diag.contributing_categories,
            "evidence_strength": diag.evidence_strength,
            "confidence": diag.confidence,
            "tools": [s.tool_name for s in executed_steps],
            "signals": sorted({sig for step in executed_steps for sig in step.result.get('signals', [])}),
            "tool_errors": [s.tool_name for s in executed_steps if s.result.get('status') == 'error'],
            "stop_reason": run.stop_reason,
            "checks_run": len(executed_steps),
            "unnecessary_checks": unnec,
            "traceable": bool(traceable),
            "had_planted_conflict": _is_conflict_template(
                item["scenario_id"], dataset),
            "found_conflict": found_conflict,
        })
    elapsed = time.perf_counter() - t_start
    return results, round(elapsed, 3)


_CONFLICT_TEMPLATES = {"T18"}


def _is_conflict_template(scenario_id: str, dataset: SyntheticDataset) -> bool:
    # scenario index -> template mapping mirrors TEMPLATES order.
    # TEMPLATES tuples are (tid, key, primary, secondary, pool, difficulty)
    # with 6 fields; the conflict marker lives in field index 5 (difficulty).
    from app.data.synthetic_generator import TEMPLATES
    try:
        idx = int(scenario_id.split("-")[-1])
    except (ValueError, IndexError):
        return False
    per = dataset.n_per_template
    tpos = (idx - 1) // per
    if 0 <= tpos < len(TEMPLATES):
        tpl = TEMPLATES[tpos]
        return len(tpl) >= 6 and tpl[5] == "conflicting"
    return False


def _count_unnecessary(conn, run, method):
    """Replay actual evidence prefixes with the shared stop/classification policy."""
    from app.agent import policy
    final = run.diagnosis
    if not final.primary_category:
        return 0
    state = models.CaseState(run.state.complaint, run.state.applicable_categories)
    steps = [s for s in run.trace if s.result.get('status') != 'not_applicable']
    for k, step in enumerate(steps, 1):
        state.beliefs = dict(step.state_changes.get('beliefs_after', {}))
        state.evidence.extend(models.Evidence(**e) for e in step.state_changes.get('evidence_added', []))
        state.checks_run.append(step.tool_name)
        state.step_count = k
        if step.result.get('findings', {}).get('session'):
            state.matched_session = step.result['findings']['session']
        policy.register_conflicts(state, step.state_changes.get('conflicts_added', []))
        policy.refresh_unresolved_questions(state)
        stop = policy.should_stop(conn, state)
        if stop:
            d = policy.classify(conn, state, stop)
            if d.primary_category == final.primary_category and d.classification == final.classification:
                return len(steps) - k
    return 0


def evaluate_learning(seed: int = 42, n_per_template: int = 10,
                      train_fraction: float = 0.5) -> Dict[str, Any]:
    """Does reviewer-verified feedback improve the agent on UNSEEN cases?

    Fixed-seed split of the labelled cases into train/test (no case is in both).
    1. Run the adaptive agent on the test set with the static seed rules (BEFORE).
    2. Simulate a reviewer on the train set: diagnose + persist each case, store the
       verified root cause (the label), and apply the bounded learning update.
       Cases whose true label is 'inconclusive' have no verifiable cause and are skipped.
    3. Re-run the agent on the same test set (AFTER) and compare.
    The reviewer is simulated from synthetic labels, so this measures the mechanism,
    not real reviewer behaviour.
    """
    import random
    from app.services.diagnosis import diagnose_and_persist
    from app.services import feedback as fb
    from app.core.settings import category_ids

    tmp = os.path.join(REPORT_DIR, ".tmp")
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, f"learn_{seed}_{uuid.uuid4().hex}.db")
    conn = _fresh_conn(path)
    try:
        conn.execute("INSERT OR IGNORE INTO reviewers(reviewer_id, name, role, active)"
                     " VALUES ('eval-reviewer','Simulated reviewer','diagnosis_reviewer',1)")
        conn.commit()
        ds = SyntheticDataset(seed=seed, n_per_template=n_per_template)
        ds.write(conn)
        items = ds.complaints()
        rng = random.Random(seed)
        order = list(range(len(items)))
        rng.shuffle(order)
        cut = int(len(items) * train_fraction)
        train = [items[i] for i in order[:cut]]
        test = [items[i] for i in order[cut:]]
        assert not ({i["scenario_id"] for i in train} & {i["scenario_id"] for i in test})
        labels = category_ids()

        before_res, _ = run_method(conn, "adaptive", ds, items=test)
        before = _score(before_res, labels)

        n_applied = n_changes = n_skipped = 0
        invalid_training_labels = []
        for item in train:
            if item["ground_truth"] == "inconclusive":
                n_skipped += 1
                continue
            from app.core.settings import applicable_categories
            if item['ground_truth'] not in applicable_categories(item['payload']['app_id']):
                invalid_training_labels.append(item['scenario_id'])
                continue
            complaint = build_complaint(dict(item["payload"]))
            out = diagnose_and_persist(conn, complaint)
            r = fb.create_resolution(conn, out["case_id"], {
                "reviewer_id": "eval-reviewer",
                "verified_root_cause": item["ground_truth"],
                "verified_contributing": [item["secondary"]] if item["secondary"] else [],
                "corrective_action": "simulated reviewer verification"})
            a = fb.apply_verified_outcome(conn, r["resolution_id"])
            n_applied += 1 if a["applied"] else 0
            n_changes += len(a["changes"])

        after_res, _ = run_method(conn, "adaptive", ds, items=test)
        after = _score(after_res, labels)
        keys = ("accuracy_pct", "macro_f1", "abstention_correct_pct",
                "false_confident_pct", "avg_checks_per_case")
        return {
            "seed": seed, "train_cases": len(train), "test_cases": len(test),
            "train_skipped_inconclusive": n_skipped,
            "train_invalid_label_cases": invalid_training_labels,
            "verified_resolutions_applied": n_applied,
            "knowledge_changes": n_changes,
            "before": {k: before.get(k) for k in keys},
            "after": {k: after.get(k) for k in keys},
            "delta": {k: (round(after[k] - before[k], 4)
                          if before.get(k) is not None and after.get(k) is not None
                          else None) for k in keys},
            "before_details": before,
            "after_details": after,
            "transitions": [{"scenario_id": x['scenario_id'], "ground_truth": x['ground_truth'],
                "before": x['primary_category'], "after": y['primary_category']}
                for x, y in zip(before_res, after_res) if x['primary_category'] != y['primary_category']],
            "note": ("Reviewer simulated from synthetic labels; train/test disjoint; "
                     "single split, so differences of a few points are within noise."),
        }
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass


def evaluate(seed: int = 42, n_per_template: int = 10,
             db_path: Optional[str] = None) -> Dict[str, Any]:
    """Run both methods on identical cases in a fresh temp DB."""
    if n_per_template < 1 or n_per_template > 100:
        raise ValueError('n_per_template must be between 1 and 100')
    from app.agent.calibration import calibration_metadata
    model = calibration_metadata()
    if model and model['seed'] == seed:
        raise ValueError('Evaluation seed must differ from the frozen calibration development seed')
    own_conn = None
    if db_path is None:
        tmpdir = os.path.join(REPORT_DIR, ".tmp")
        os.makedirs(tmpdir, exist_ok=True)
        db_path = os.path.join(tmpdir, f"eval_{seed}_{uuid.uuid4().hex}.db")
        own_conn = _fresh_conn(db_path)
    if own_conn is None and os.path.exists(db_path):
        raise FileExistsError('Evaluation requires a new scratch database path; existing files are never modified.')
    conn = own_conn or _fresh_conn(db_path)
    try:
        ds = SyntheticDataset(seed=seed, n_per_template=n_per_template)
        ds.write(conn)
        from app.core.settings import category_ids
        labels = category_ids()
        agent_res, agent_t = run_method(conn, "adaptive", ds)
        base_res, base_t = run_method(conn, "baseline", ds)
        metrics = {
            "adaptive_agent": {**_score(agent_res, labels), "runtime_s": agent_t},
            "fixed_baseline": {**_score(base_res, labels), "runtime_s": base_t},
        }
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset_size": len(ds.cases),
            "data_origin": "simulated",
            "seed": seed,
            "n_per_template": n_per_template,
            "procedure": (
                "Both methods ran on the identical labelled synthetic case set "
                "inside a fresh temporary SQLite DB seeded only with the static "
                "rule set (no learned weights, no cross-run leakage). Ground "
                "truth was withheld from agent inputs."),
            "metrics": metrics,
            "calibration_model": model,
            "dataset_audit": audit_dataset(ds),
            "learning_experiment": evaluate_learning(seed, n_per_template),
            "per_case": {"adaptive_agent": agent_res, "fixed_baseline": base_res},
            "limitations": [
                "Dataset is synthetic data authored by the same developer as "
                "the rules; results are optimistic and NOT real-world "
                "performance.",
                "Small scale (~hundreds of cases); percentages carry wide "
                "uncertainty.",
                "Generator templates and diagnosis rules are correlated by "
                "design (signals were defined together).",
                "No real charging-network logs were used anywhere.",
                "PII redaction is best-effort, not a guarantee.",
            ],
        }
    finally:
        conn.close()
        if os.path.exists(db_path) and db_path.endswith(".db"):
            for suffix in ("", "-wal", "-shm"):
                p = db_path + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
    return report


def write_reports(report: Dict[str, Any],output_dir=None) -> List[str]:
    report_dir=str(output_dir) if output_dir is not None else REPORT_DIR
    os.makedirs(report_dir, exist_ok=True)
    md_path = os.path.join(report_dir, "evaluation_report.md")
    csv_path = os.path.join(report_dir, "evaluation_results.csv")
    json_path = os.path.join(report_dir, "evaluation_results.json")
    import csv

    rows = []
    for method, m in report["metrics"].items():
        for key, val in m.items():
            if isinstance(val, (int, float, str)) or val is None:
                rows.append({"method": method, "metric": key, "value": val})
    with open(csv_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['method', 'metric', 'value'])
        writer.writeheader()
        writer.writerows(rows)

    slim = {k: v for k, v in report.items() if k != "per_case"}
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)

    m_a = report["metrics"]["adaptive_agent"]
    m_b = report["metrics"]["fixed_baseline"]
    lines = [
        "# Evaluation Report — SIMULATED DATA ONLY (NOT real-world performance)",
        "",
        f"Generated: {report['generated_at']}  ",
        f"Dataset size: **{report['dataset_size']} labelled synthetic cases** "
        f"(seed={report['seed']}, {report['n_per_template']} variants/template)  ",
        f"Data origin: **{report['data_origin']}** — fabricated by design.",
        "",
        "## Procedure",
        report["procedure"],
        "",
        "## Metric definitions",
        "- accuracy: primary category equals ground truth; for true-'inconclusive'"
        " cases, a correct abstention (no asserted category) counts as correct.",
        "- macro_f1: mean per-category F1 over the 12 problem categories.",
        "- abstention_correct_pct: truly-inconclusive cases returned as"
        " inconclusive/requires_further_investigation.",
        "- false_confident_pct: truly-inconclusive cases answered confirmed/probable.",
        "- avg_checks_per_case: executed diagnostic tools per case"
        " (not_applicable skips excluded).",
        "- avg_unnecessary_checks: checks run after the evidence prefix already"
        " supported the final classification (see evaluation.py docstring).",
        "- traceability_pct: diagnoses whose supporting-evidence ids all resolve"
        " to stored evidence items.",
        "- conflict_detection_pct: planted-conflict cases where conflicting"
        " evidence was recorded.",
        "",
        "## Results (computed from this run — nothing hardcoded)",
        "",
        "| Metric | Adaptive agent | Fixed baseline |",
        "|---|---|---|",
    ]
    keys = ["n_cases", "accuracy_pct", "macro_f1", "abstention_correct_pct",
            "false_confident_pct", "avg_checks_per_case",
            "avg_unnecessary_checks", "traceability_pct",
            "conflict_detection_pct", "runtime_s"]
    for k in keys:
        lines.append(f"| {k} | {m_a.get(k)} | {m_b.get(k)} |")
    lines += ["", "### Per-category accuracy (%)", "",
              "| Category | Adaptive | Baseline |", "|---|---|---|"]
    cats = sorted(set(m_a["per_category_accuracy"]) |
                  set(m_b["per_category_accuracy"]))
    for c in cats:
        lines.append(f"| {c} | {m_a['per_category_accuracy'].get(c)} | "
                     f"{m_b['per_category_accuracy'].get(c)} |")
    cal = m_a.get("calibration") or {}
    if cal:
        lines += ["", "### Confidence calibration (adaptive agent, labelled cases)", "",
                  f"ECE = {cal['ece']} (lower is better); mean confidence when "
                  f"correct = {cal['mean_confidence_when_correct']}, when wrong = "
                  f"{cal['mean_confidence_when_wrong']}.", "",
                  "| Confidence bin | n | Mean confidence | Accuracy % |", "|---|---|---|---|"]
        for b in cal["bins"]:
            lines.append(f"| {b['range']} | {b['n']} | {b['mean_confidence']} | "
                         f"{b['accuracy_pct']} |")
    le = report.get("learning_experiment")
    if le:
        lines += ["", "### Reviewer-feedback learning experiment (held-out cases)", "",
                  f"Train {le['train_cases']} / test {le['test_cases']} cases; "
                  f"{le['verified_resolutions_applied']} verified resolutions applied "
                  f"({le['knowledge_changes']} knowledge changes). {le['note']}", "",
                  "| Metric | Before | After | Delta |", "|---|---|---|---|"]
        for k in le["before"]:
            lines.append(f"| {k} | {le['before'][k]} | {le['after'][k]} | {le['delta'][k]} |")
    winner_note = ("The run above shows the adaptive agent ahead on these "
                   "synthetic cases." if m_a["accuracy_pct"] > m_b["accuracy_pct"]
                   else "NOTE: on this run the fixed baseline is equal or better "
                        "than the adaptive agent on accuracy.")
    lines += ["", f"{winner_note}", "", "## LIMITATIONS", ""]
    lines += [f"- {l}" for l in report["limitations"]]
    from app.evaluation.report_details import detail_lines, write_detail_files
    lines.extend(detail_lines(report))
    extra_paths = write_detail_files(report, report_dir)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return [md_path, csv_path, json_path, *extra_paths]
