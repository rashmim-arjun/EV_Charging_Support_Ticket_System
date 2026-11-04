"""Shared public observation schema and bounded simulator configuration."""
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComponentType(str, Enum):
    app = 'app'
    csms = 'csms'
    charger = 'charger'
    connector = 'connector'
    vehicle = 'vehicle'
    bms = 'bms'
    payment = 'payment'
    network = 'network'


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str
    session_id: str
    trace_id: str
    correlation_id: str
    message_id: str | None = None
    attempt_id: str | None = None
    parent_event_id: str | None = None
    component_id: str
    component_type: ComponentType
    timestamp: datetime
    sequence: int = Field(ge=0)
    event_type: str
    severity: Literal['debug', 'info', 'warning', 'error', 'critical'] = 'info'
    status: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator('timestamp')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Event timestamps must include a timezone')
        return value


class Injection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['delay', 'drop', 'duplicate', 'stale', 'timeout', 'retry']
    operation: str
    delay_ms: int = Field(default=6000, ge=1, le=120000)
    copies: int = Field(default=1, ge=1, le=3)

    @model_validator(mode='after')
    def valid_target(self):
        if self.kind == 'stale' and self.operation != 'StatusNotification':
            raise ValueError('Stale status injection targets StatusNotification')
        return self


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = Field(default=42, ge=0, le=2147483647)
    per_template: int = Field(default=2, ge=1, le=20)
    split: Literal['train', 'validation', 'test', 'all'] = 'test'
    scenarios: list[str] | None = Field(default=None, min_length=1, max_length=12)
    injections: list[Injection] = Field(default_factory=list, max_length=5)


class CommunicationEvaluationRequest(BaseModel):
    seed: int = Field(default=42, ge=0, le=2147483647)
    per_template: int = Field(default=4, ge=1, le=15)


class GenerationResult(BaseModel):
    run_id: str
    inserted: int
    total: int
    session_ids: list[str]
    warnings: list[dict[str, Any]]
    data_origin: Literal['simulated']


class SessionSummary(BaseModel):
    session_id: str
    run_id: str
    trace_id: str
    app_id: str
    started_at: datetime
    ended_at: datetime
    status: str
    components: dict[str, str]
    event_count: int | None = None


class SessionPage(BaseModel):
    items: list[SessionSummary]
    total: int
    page: int
    page_size: int


class SessionDetail(BaseModel):
    session: SessionSummary
    events: list[Event]
    flows: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    components: list[dict[str, Any]]
    correlations: dict[str, list[str]]
    observed_components: int
    scope: str
    diagnosis: dict[str, Any] | None = None
