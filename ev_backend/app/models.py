"""Internal dataclasses shared by the agent, services and evaluation.

These are plain in-memory structures; persistence lives in the services layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    """One evidence item collected for a case."""
    kind: str                      # matching | conflicting | missing | neutral
    description: str
    source_table: Optional[str] = None
    source_ref: Optional[str] = None
    supports_category: Optional[str] = None   # category id (for matching/neutral)
    contradicts_category: Optional[str] = None  # category id (for conflicting)
    weight: float = 0.5
    tool_name: str = ""
    evidence_id: Optional[int] = None          # filled after persistence
    signal_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "source_table": self.source_table,
            "source_ref": self.source_ref,
            "supports_category": self.supports_category,
            "contradicts_category": self.contradicts_category,
            "weight": round(self.weight, 4),
            "tool_name": self.tool_name,
            "evidence_id": self.evidence_id,
            "signal_key": self.signal_key,
        }


@dataclass
class CheckResult:
    """What a diagnostic tool returns. Tools NEVER raise into the agent loop."""
    tool_name: str
    status: str                    # ok | no_data | error | not_applicable
    summary: str
    findings: Dict[str, Any] = field(default_factory=dict)
    evidence_items: List[Evidence] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)  # signal_keys observed

    def __post_init__(self):
        # Tools commonly emit one observation per signal, in the same order.
        # Record that association even when the signal has no rule yet, so the
        # reviewer learning loop can propose a new rule from distinct cases.
        if len(self.signals) == len(self.evidence_items):
            for signal, evidence in zip(self.signals, self.evidence_items):
                if evidence.kind == 'matching' and evidence.signal_key is None:
                    evidence.signal_key = signal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "summary": self.summary,
            "findings": self.findings,
            "signals": self.signals,
            "evidence_items": [e.to_dict() for e in self.evidence_items],
        }


@dataclass
class Complaint:
    app_id: str
    text_redacted: str
    complaint_ts: Optional[str] = None
    reported_error: Optional[str] = None
    reported_payment_status: Optional[str] = None
    session_ref: Optional[str] = None
    station_id: Optional[str] = None
    user_ref: Optional[str] = None
    data_origin: str = "manual_test"
    ground_truth_category: Optional[str] = None  # ONLY labelled synthetic/test
    scenario_id: Optional[str] = None


@dataclass
class CaseState:
    """The agent's explicit working state during one diagnosis run."""
    complaint: Complaint
    applicable_categories: List[str]
    beliefs: Dict[str, float] = field(default_factory=dict)      # category -> score
    evidence: List[Evidence] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)          # tool names
    run_signatures: set = field(default_factory=set)             # tool+inputs already run
    step_count: int = 0
    stop_status: Optional[str] = None                            # stop reason when done
    matched_session: Optional[Dict[str, Any]] = None
    top_category_before_last_step: Optional[str] = None
    pending_conflict: bool = False
    info_gaps: List[str] = field(default_factory=list)           # required-info list
    hinted_categories: List[str] = field(default_factory=list)   # seeded from complaint keywords

    def top_category(self) -> Optional[str]:
        if not self.beliefs:
            return None
        supported = {e.supports_category for e in self.evidence if e.kind == 'matching' and e.supports_category}
        candidates = [(c, v) for c, v in self.beliefs.items() if not supported or c in supported]
        if not candidates:
            return None
        # Complaint relevance breaks close races between an observed symptom and
        # a separate observed issue, e.g. a failed session and its overdue refund.
        best = max(candidates, key=lambda kv: (round(kv[1] + (.2 if kv[0] in self.hinted_categories else 0), 8),
                                               kv[0] in self.hinted_categories, kv[1], kv[0]))
        return best[0] if best[1] > 0 else None

    def belief_snapshot(self) -> Dict[str, float]:
        return {k: round(v, 4) for k, v in sorted(
            self.beliefs.items(), key=lambda kv: -kv[1]) if v > 0.001}


@dataclass
class DiagnosisResult:
    classification: str            # confirmed|probable|inconclusive|requires_further_investigation
    primary_category: Optional[str]
    contributing_categories: List[str]
    evidence_strength: float
    evidence_strength_label: str
    supporting_evidence_ids: List[int]
    unresolved_questions: List[str]
    stop_reason: str
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    leading_hypothesis: Optional[str] = None   # best guess when the agent abstains
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification,
            "primary_category": self.primary_category,
            "leading_hypothesis": self.leading_hypothesis,
            "contributing_categories": self.contributing_categories,
            "evidence_strength": round(self.evidence_strength, 3),
            "confidence": self.confidence,
            "evidence_strength_label": self.evidence_strength_label,
            "supporting_evidence_ids": self.supporting_evidence_ids,
            "unresolved_questions": self.unresolved_questions,
            "stop_reason": self.stop_reason,
            "recommendations": self.recommendations,
        }
