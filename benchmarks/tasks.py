"""Plain finite world specifications; generation is independent of router status."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

PROTOCOL = Path(__file__).with_name("protocol.json")


def manifest() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def digest(raw: str | bytes) -> str:
    return hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()


@dataclass(frozen=True)
class Task:
    id: str
    family: str
    seed: int
    index: int
    value: int
    threshold: int
    mode: int
    sources: int
    checkers: int
    actions: int
    verifications: int
    budget_class: str
    solvable: bool
    raw_world_valid: bool
    minimum_continuation_actions: int

    def document(self) -> dict:
        return asdict(self)


def generate(phase: str, *, limit: int | None = None) -> tuple[Task, ...]:
    protocol = manifest()
    if phase not in {"development", "holdout", "regression"}:
        raise ValueError("phase must be development, holdout or regression")
    count = protocol[f"{phase}_tasks_per_family"]
    if limit is not None:
        if limit < 1 or limit > count:
            raise ValueError("limit must be positive and at most the frozen task count")
        count = limit
    seed = protocol[f"{phase}_seed"]
    tasks = []
    for family_number, family in enumerate(protocol["families"], 1):
        rng = random.Random(seed + 1009 * family_number)
        for index in range(count):
            threshold = rng.randrange(1, 5000) + index * 17
            value = threshold + rng.randrange(1, 1000)
            mode = index % 6
            sources = 2 + index % 2 if family == "F1" else 1 + index % 3
            checkers = 1 + index % 3 if family == "F3" else 1
            tight = index % 5 == 0
            actions, verifications = 12, 6
            solvable = True
            raw_valid, minimum_calls = True, 0
            if family == "F1":
                actions, verifications = (2 if tight else 8), sources
                minimum_calls = 2 * (sources - 1)
                solvable = actions >= minimum_calls and mode not in {3, 4}
                raw_valid = mode != 4
                if mode == 4:
                    value = threshold - 1
            elif family == "F2":
                actions, verifications = (2 if tight else 10), 4
                minimum_calls = 5 if mode % 3 == 2 else 3
                solvable = not tight
            elif family == "F3":
                actions, verifications = (1 if tight else 6), checkers
                minimum_calls = 1 if mode == 2 else max(1, checkers - 1)
                solvable = mode != 3 and actions >= minimum_calls
            elif family == "F4":
                actions, verifications = (1 if tight else 10), 4
                minimum_calls = (2, 2, 1, 3, 3, 1)[mode]
                solvable = actions >= minimum_calls and mode != 4
                raw_valid = mode != 4
            elif family == "F5":
                actions, verifications = (0 if tight else 5), 3
                minimum_calls = 2 if mode == 2 else 1
                solvable = not tight and mode not in {3, 4}
            elif family == "F6":
                if mode == 5:
                    sources = 1
                actions, verifications = (1 if tight else 2 * sources), sources
                minimum_calls = 2 * (sources - (1 if mode == 5 else 0))
                solvable = actions >= minimum_calls and mode != 4
                raw_valid = mode != 4
                if mode == 4:
                    value = threshold - 1
            elif family == "F7":
                actions, verifications = 2 + index % 3, 1
                minimum_calls = -1  # No attainable authorized successful callback schedule.
                solvable = False
            elif family == "F8":
                actions, verifications = 4, 2
                solvable = mode in {0, 1, 2, 5}
                raw_valid, minimum_calls = solvable, 4
            tasks.append(
                Task(
                    f"{'holdout' if phase == 'regression' else phase}-{family}-{index:02d}",
                    family,
                    seed,
                    index,
                    value,
                    threshold,
                    mode,
                    sources,
                    checkers,
                    actions,
                    verifications,
                    "tight" if tight else "adequate",
                    solvable,
                    raw_valid,
                    minimum_calls,
                )
            )
    return tuple(tasks)


def raw_number(value: int | None, threshold: int, *, role: str = "number") -> str:
    return json.dumps({"role": role, "value": value, "minimum": threshold}, sort_keys=True)
