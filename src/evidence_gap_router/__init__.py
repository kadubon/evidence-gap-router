"""Route work by missing evidence, not by agent count."""

from ._version import __version__
from .jsonio import MAX_JSON_BYTES, dump_json, load_json, read_json
from .models import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckResult,
    Contradiction,
    Coverage,
    Decision,
    Evidence,
    Exclusion,
    Obligation,
    PlanInput,
    Policy,
    Residual,
    Resources,
    Result,
    State,
    Supersession,
)
from .router import observe, plan, start

__all__ = [
    "MAX_JSON_BYTES",
    "ActionCandidate",
    "Attempt",
    "Budget",
    "CheckResult",
    "Contradiction",
    "Coverage",
    "Decision",
    "Evidence",
    "Exclusion",
    "Obligation",
    "PlanInput",
    "Policy",
    "Residual",
    "Resources",
    "Result",
    "State",
    "Supersession",
    "__version__",
    "dump_json",
    "load_json",
    "observe",
    "plan",
    "read_json",
    "start",
]
