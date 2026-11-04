"""Evaluation metrics, calibration and the reviewer-feedback learning experiment."""
from app.evaluation import evaluation as ev


def _res(gt, pred, cls, strength=0.5, planted=False, found=False):
    return {"ground_truth": gt, "primary_category": pred, "classification": cls,
            "leading_hypothesis": pred, "evidence_strength": strength,
            "checks_run": 3, "unnecessary_checks": 0, "traceable": True,
            "had_planted_conflict": planted, "found_conflict": found}


def test_score_inconclusive_does_not_inherit_stale_ok():
    """Regression: `ok` leaked from the previous case into inconclusive cases."""
    labels = ["a", "b"]
    results = [_res("a", "a", "probable"),                 # correct -> ok=True
               _res("inconclusive", "b", "probable")]      # false-confident, must be wrong
    m = ev._score(results, labels)
    assert m["per_category_accuracy"]["inconclusive"] == 0.0
    assert m["false_confident_pct"] == 100.0
    assert m["accuracy_pct"] == 50.0


def test_score_abstention_and_conflict_metrics():
    labels = ["a"]
    results = [_res("inconclusive", None, "inconclusive"),
               _res("a", "a", "probable", planted=True, found=True),
               _res("a", "a", "probable", planted=True, found=False)]
    m = ev._score(results, labels)
    assert m["abstention_correct_pct"] == 100.0
    assert m["conflict_detection_pct"] == 50.0


def test_calibration_buckets():
    results = [_res("a", "a", "probable", 0.9), _res("a", "b", "probable", 0.1),
               _res("a", "a", "probable", 0.9)]
    cal = ev._calibration(results)
    assert cal["n_cases"] == 3
    assert 0 <= cal["ece"] <= 1
    assert cal["mean_confidence_when_correct"] > cal["mean_confidence_when_wrong"]


def test_evaluate_smoke_and_planted_conflicts_detected():
    rep = ev.evaluate(seed=7, n_per_template=2)
    a, b = rep["metrics"]["adaptive_agent"], rep["metrics"]["fixed_baseline"]
    assert a["n_cases"] == b["n_cases"] == 50
    assert a["planted_conflict_cases"] == 2
    assert a["conflict_detection_pct"] == 100.0
    assert a["calibration"]["bins"]
    assert a["avg_checks_per_case"] < b["avg_checks_per_case"]


def test_learning_experiment_is_disjoint_and_runs():
    le = ev.evaluate_learning(seed=7, n_per_template=4)
    assert le["train_cases"] + le["test_cases"] == 100
    assert le["verified_resolutions_applied"] > 0
    assert le["knowledge_changes"] > 0
    assert set(le["before"]) == set(le["after"]) == set(le["delta"])
