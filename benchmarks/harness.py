"""CPU-only matched experiments using public SDK transitions and finite recipes."""

from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import random
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
import zipfile
from decimal import Decimal
from importlib import metadata
from pathlib import Path

from benchmarks.tasks import PROTOCOL, Task, digest, generate, manifest, raw_number


def environment() -> dict:
    import evidence_gap_router as sdk

    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "package": sdk.__version__,
        "package_import": str(Path(sdk.__file__).resolve()),
        "pydantic": metadata.version("pydantic"),
        "pydantic_core": metadata.version("pydantic_core"),
        "runtime_dependencies": {
            name: metadata.version(name)
            for name in (
                "pydantic",
                "pydantic_core",
                "annotated-types",
                "typing-extensions",
                "typing-inspection",
            )
        },
    }


def code_hash() -> str:
    return digest(
        b"".join(
            p.name.encode() + p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py"))
        )
    )


def package_files(wheel: Path) -> dict[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        return {
            name.removeprefix("evidence_gap_router/"): digest(archive.read(name))
            for name in sorted(archive.namelist())
            if name.startswith("evidence_gap_router/") and not name.endswith("/")
        }


def package_fingerprint(wheel: Path) -> str:
    return digest(json.dumps(package_files(wheel), sort_keys=True, separators=(",", ":")))


def verify_installed_bytes(wheel: Path) -> str:
    import evidence_gap_router as sdk

    directory = Path(sdk.__file__).resolve().parent
    actual = {
        p.relative_to(directory).as_posix(): digest(p.read_bytes())
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    expected = package_files(wheel)
    if not expected or actual != expected:
        raise ValueError("Installed package files do not match the declared wheel bytes")
    return package_fingerprint(wheel)


def freeze(path: Path, commit: str, wheel: Path, old_wheel: Path) -> None:
    if path.exists():
        raise ValueError("Freeze record already exists; do not replace preregistration")
    if digest(old_wheel.read_bytes()) != manifest()["baseline_wheel_sha256"]:
        raise ValueError("Wrong published v0.2.0 baseline bytes")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Implementation commit must be a full lowercase Git SHA")
    measured = environment()
    if measured["package"] != "0.2.1" or "site-packages" not in measured["package_import"]:
        raise ValueError("Freeze must use an ordinary installed candidate wheel")
    installed_fingerprint = verify_installed_bytes(wheel)
    record = {
        "protocol": manifest()["protocol"],
        "implementation_commit": commit,
        "manifest_sha256": digest(PROTOCOL.read_bytes()),
        "harness_sha256": code_hash(),
        "candidate_wheel": str(wheel.resolve()),
        "wheel_sha256": digest(wheel.read_bytes()),
        "baseline_wheel": str(old_wheel.resolve()),
        "baseline_wheel_sha256": digest(old_wheel.read_bytes()),
        "candidate_package_sha256": installed_fingerprint,
        "baseline_package_sha256": package_fingerprint(old_wheel),
        "package_fingerprint_definition": (
            "SHA256 of canonical sorted package-relative filename -> SHA256(bytes) JSON; "
            "UTF-8, separators=(',',':'), excludes generated __pycache__."
        ),
        "environment": measured,
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def validate_freeze(path: Path, *, phase: str) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if (
        record["manifest_sha256"] != digest(PROTOCOL.read_bytes())
        or record["harness_sha256"] != code_hash()
    ):
        raise ValueError("Protocol or implementation changed after freeze")
    if digest(Path(record["candidate_wheel"]).read_bytes()) != record["wheel_sha256"]:
        raise ValueError("Candidate wheel changed")
    if digest(Path(record["baseline_wheel"]).read_bytes()) != record["baseline_wheel_sha256"]:
        raise ValueError("Baseline wheel changed")
    if phase == "holdout":
        import evidence_gap_router as sdk

        if Path(sdk.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1] / "src"):
            raise ValueError("Holdout must use an ordinary installed wheel outside source")
        if sdk.__version__ not in {"0.2.0", "0.2.1"}:
            raise ValueError("Unexpected measured version")
        current = environment()
        if "site-packages" not in current["package_import"]:
            raise ValueError("Holdout must import an ordinary installed wheel")
        for key in ("python", "os", "machine", "pydantic", "pydantic_core", "runtime_dependencies"):
            if current[key] != record["environment"][key]:
                raise ValueError(f"Unmatched measured environment: {key}")
        baseline = current["package"] == "0.2.0"
        wheel = Path(record["baseline_wheel" if baseline else "candidate_wheel"])
        fingerprint = verify_installed_bytes(wheel)
        key = "baseline_package_sha256" if baseline else "candidate_package_sha256"
        if fingerprint != record[key]:
            raise ValueError("Measured package content changed since freeze")
    return record


class World:
    """Finite host recipe. Its factory sees observed state, never oracle labels."""

    def __init__(self, task: Task, variant: str):
        import evidence_gap_router as s

        self.s, self.task, self.variant = s, task, variant
        self.scope = "cpu-model-free"
        self.material: dict[str, dict] = {}
        self.trace: list[dict] = []
        self.initial_trace: list[dict] = []
        self.host_updates: list[dict] = []
        self.callback_wall = 0.0
        self.callback_cpu = 0.0
        self.initial_callback_wall = 0.0
        self.initial_callback_cpu = 0.0
        self.invalidated: set[tuple[str, str]] = set()
        self.negative_ids: set[str] = set()
        self.alias_wrong = False
        self.file_bytes: tuple[bytes, bytes] | None = None
        self.directory = tempfile.TemporaryDirectory(prefix="egr-benchmark-")
        self.minimum = task.threshold
        required = (
            tuple(f"checker-{i}" for i in range(task.checkers))
            if task.family == "F3" and task.mode != 2
            else ()
        )
        groups = task.sources if task.family == "F1" else 1
        obligation = s.Obligation(
            id="task",
            scope=self.scope,
            description="Inspect numeric material",
            acceptance=json.dumps({"minimum": self.minimum}),
            required_verifiers=required,
            min_provenance_groups=groups,
        )
        obligations = [obligation]
        if task.family in {"F2", "F4", "F8"}:
            obligations.append(
                s.Obligation(
                    id="rules",
                    scope=self.scope,
                    description="Inspect rules",
                    acceptance=json.dumps({"minimum": 0}),
                    required=task.family != "F2" or task.mode % 2 == 0,
                )
            )
        self.state = s.State(obligations=tuple(obligations))
        permissions = tuple(
            s.CheckerPermission(
                checker_id=identifier,
                purposes=("content", "check_resolution", "contradiction_resolution"),
            )
            for identifier in ("main", "audit", "self", "checker-0", "checker-1", "checker-2")
        )
        self.policy = s.Policy(
            trusted_verifiers=tuple(p.checker_id for p in permissions),
            handlers=(
                s.HandlerRegistration(handler_id="read", roles=("investigate", "diversify")),
                s.HandlerRegistration(handler_id="check", roles=("verify",), checkers=permissions),
            ),
            available_handlers=("read", "check"),
            max_pending_verifications=(1, 2, 4)[task.index % 3] if task.family == "F3" else 20,
        )
        self.budget = s.Budget(
            limits=s.Resources(actions=task.actions, verifications=task.verifications)
        )
        self.add("e0", task.value, "task", "origin-0")
        if task.family == "F1":
            self.add("repeat", task.value, "task", "origin-0")
            for i in range(1, task.sources):
                self.add(f"e{i}", task.value + i, "task", f"origin-{i}")
            if task.mode == 3:
                self.material[f"e{task.sources - 1}"]["source"] = None
                self.material[f"e{task.sources - 1}"]["group"] = None
        if task.family in {"F2", "F4"}:
            self.add("rules0", task.threshold, "rules", "rules-0")
            self.add("extra", task.threshold, "rules", "rules-0")
            self.add("unused", task.threshold + 100, "rules", "rules-unrelated")
            if task.family == "F2" and task.mode % 3 == 2:
                self.add("stage", 0, "rules", "rule-stage")
            if task.family == "F4" and task.mode == 0:
                self.add("alias", task.value, "task", "origin-0")
        if task.family == "F6":
            for i in range(1, task.sources):
                self.add(f"e{i}", task.value + i, "task", f"origin-{i}")
            if task.sources > 1:
                self.state = s.State(
                    obligations=(obligation.model_copy(update={"min_evidence": task.sources}),)
                )
        if task.family == "F5":
            self.add("alias", task.value, "task", "origin-0")
            diagnostic = None if task.mode == 1 else task.value + 1
            raw = json.dumps(
                {"value": task.value, "minimum": task.threshold, "diagnostic_minimum": diagnostic},
                sort_keys=True,
            ).encode()
            self.material["e0"]["raw"] = raw
            self.material["alias"]["raw"] = raw
        if task.family == "F8":
            self.prepare_files()

    def add(self, identifier: str, value: int, owner: str, source: str) -> None:
        raw = raw_number(value, self.task.threshold if owner == "task" else 0)
        self.material[identifier] = {
            "raw": raw.encode(),
            "owner": owner,
            "source": source,
            "group": source,
            "role": "number",
        }

    def prepare_files(self) -> None:
        task = self.task
        rows = 10000 if task.index == 29 else 1 + task.index * 3
        minimum = str(task.threshold)
        amount = str(task.value)
        if task.mode == 2:
            minimum = f"{task.threshold}.00000000000000001"
            amount = f"{task.threshold}.00000000000000002"
        if task.mode == 3:
            minimum, amount = "9007199254740993.0", "9007199254740992"
        header = "order_id,amount,currency\n"
        duplicate_header = task.mode == 4 and task.index < 12
        if duplicate_header:
            header = "order_id,amount,amount,currency\n"
        body = "".join(
            f"row-{i},-999,{amount},USD\n"
            if duplicate_header
            else f"row-{i}{'-' + 'x' * 40 if task.index == 29 else ''},{amount},USD\n"
            for i in range(rows)
        )
        raw_csv = (header + body).encode()
        rules = (
            '{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
            f'"minimum_amount":{minimum},"allowed_currencies":["USD"]' + "}"
        ).encode()
        if task.mode == 4 and not duplicate_header:
            # A last-value-wins reader silently hides the first duplicate threshold.
            rules = rules.replace(
                f'"minimum_amount":{minimum}'.encode(),
                f'"minimum_amount":{task.value + 1},"minimum_amount":{minimum}'.encode(),
            )
        if task.mode in {1, 5}:
            raw_csv = b"\xef\xbb\xbf" + raw_csv.replace(b"\n", b"\r\n")
            rules = b"\xef\xbb\xbf" + rules
        folder = Path(self.directory.name) / "日本語 path"
        folder.mkdir()
        data_path, rules_path = folder / "受注 data.csv", folder / "規則 rules.json"
        data_path.write_bytes(raw_csv)
        rules_path.write_bytes(rules)
        self.file_bytes = raw_csv, rules
        self.material = {
            "e0": {
                "raw": raw_csv,
                "owner": "task",
                "source": str(data_path),
                "group": "local-data",
                "role": "csv",
                "path": data_path,
            },
            "rules0": {
                "raw": rules,
                "owner": "rules",
                "source": str(rules_path),
                "group": "local-rules",
                "role": "rules",
                "path": rules_path,
            },
        }

    def read_action(self, identifier: str):
        m, s = self.material[identifier], self.s
        return s.ActionCandidate(
            id=f"read:{identifier}",
            obligation_id=m["owner"],
            scope=self.scope,
            kind="diversify" if self.task.family == "F1" else "investigate",
            handler_id="read",
            produces_evidence_id=identifier,
            source=m["source"],
            provenance_group=m["group"],
        )

    def check_action(
        self,
        identifier: str,
        state,
        *,
        checker: str = "main",
        purpose: str = "content",
        target: str | None = None,
    ):
        s = self.s
        e = next(e for e in state.evidence if e.id == identifier)
        dependencies = []
        if e.obligation_id == "task" and self.task.family in {"F2", "F4", "F8"}:
            dep_id = "extra" if self.task.family == "F2" else "rules0"
            if self.task.family == "F4" and self.task.mode in {3, 4}:
                dep_id = "extra"
            dependencies.append(
                s.DependencyRequirement(
                    evidence_id=dep_id,
                    obligation_id="rules",
                    scope=self.scope,
                    requirement="verified",
                )
            )
        if identifier == "extra" and "stage" in self.material:
            dependencies.append(
                s.DependencyRequirement(
                    evidence_id="stage",
                    obligation_id="rules",
                    scope=self.scope,
                    requirement="verified",
                )
            )
        if purpose == "contradiction_resolution":
            dependencies.append(
                s.DependencyRequirement(evidence_id="alias", obligation_id="task", scope=self.scope)
            )
        return s.ActionCandidate(
            id=f"check:{identifier}:{checker}:{purpose}:{len(state.checks)}",
            obligation_id=e.obligation_id,
            scope=self.scope,
            kind="verify",
            handler_id="check",
            target_evidence_id=identifier,
            target_digest=e.digest,
            checker_id=checker,
            purpose=purpose,
            resolution_target_id=target,
            dependencies=tuple(dependencies),
            resources=s.Resources(actions=1, verifications=1),
        )

    def pool(self, state) -> tuple:
        if self.task.family == "F7" and self.task.mode == 1:
            raise RuntimeError("declared factory fault")
        actions = []
        have = {e.id for e in state.evidence}
        for identifier in self.material:
            if identifier not in have and not (self.task.family == "F7" and self.task.mode == 0):
                actions.append(self.read_action(identifier))
        for evidence in state.evidence:
            if ("evidence", evidence.id) in self.invalidated:
                continue
            checkers = (
                [f"checker-{i}" for i in range(self.task.checkers)]
                if self.task.family == "F3"
                else ["main"]
            )
            if self.task.family == "F3" and self.task.mode == 3:
                checkers = checkers[:-1]
            if self.task.family == "F3" and self.task.mode == 2:
                # checker-0 is prohibited, checker-1 is an allowed alternative.
                checkers = ["checker-0", "checker-1"]
            actions.extend(
                self.check_action(evidence.id, state, checker=checker) for checker in checkers
            )
        if self.task.family in {"F4", "F5"}:
            for negative in state.checks:
                if negative.id not in self.negative_ids:
                    continue
                subject = "alias" if self.alias_wrong else "e0"
                if subject in have and self.task.mode != 4:
                    actions.insert(
                        0,
                        self.check_action(
                            subject, state, purpose="check_resolution", target=negative.id
                        ),
                    )
            for contradiction in state.contradictions:
                if "alias" in have and self.task.mode != 4:
                    actions.insert(
                        0,
                        self.check_action(
                            "e0", state, purpose="contradiction_resolution", target=contradiction.id
                        ),
                    )
        if self.variant == "reversed":
            actions.reverse()
        elif self.variant == "renamed":
            # Changing public candidate IDs is harmless; factual material IDs stay fixed.
            actions = [
                a.model_copy(update={"id": f"candidate-{len(actions) - i:03d}:{a.id}"})
                for i, a in enumerate(actions)
            ]
        return tuple(actions)

    def callback(self, view):
        s, task = self.s, self.task
        if task.family == "F7":
            if task.mode == 2:
                raise RuntimeError("declared callback fault")
            if task.mode == 3:
                return "invalid receipt"
            if task.mode == 4:
                return view.result(
                    actual_resources=s.Resources(actions=1, verifications=None),
                    status="unknown",
                    side_effects="unknown",
                )
            if task.mode == 5:
                return view.result(actual_resources=s.Resources(actions=1, verifications=0))
        if view.action.kind != "verify":
            identifier = view.action.produces_evidence_id
            material = self.material[identifier]
            raw = material["path"].read_bytes() if "path" in material else material["raw"]
            content = raw.decode("utf-8-sig")
            producer = "checker-0" if task.family == "F3" and task.mode == 2 else "collector"
            evidence = s.Evidence(
                id=identifier,
                obligation_id=view.action.obligation_id,
                scope=self.scope,
                digest=digest(raw),
                content=content,
                producer=producer,
                source=material["source"],
                provenance_group=material["group"],
            )
            receipt = view.result(
                actual_resources=s.Resources(actions=1, verifications=0), evidence=(evidence,)
            )
        else:
            status, reason = self.compute(view)
            check = view.check(status=status, reason=reason)
            supersessions = ()
            if status == "PASS" and view.action.purpose != "content":
                kind = "check" if view.action.purpose == "check_resolution" else "contradiction"
                supersessions = (
                    s.Supersession(
                        id=view.attempt_id + ":resolution",
                        kind=kind,
                        target_id=view.action.resolution_target_id,
                        replacement_id=check.id if kind == "check" else None,
                        check_id=check.id if kind == "contradiction" else None,
                        reason="computed authorized recomputation on pinned materials",
                    ),
                )
            receipt = view.result(
                actual_resources=s.Resources(actions=1, verifications=1),
                checks=(check,),
                supersessions=supersessions,
            )
        self.trace.append(
            {
                "action": view.action.model_dump(mode="json"),
                "obligation": view.obligation.model_dump(mode="json"),
                "inputs": [
                    {"id": e.id, "digest": e.digest, "content": e.content} for e in view.inputs
                ],
                "receipt": receipt.model_dump(mode="json"),
            }
        )
        return receipt

    def compute(self, view) -> tuple[str, str]:
        target = view.inputs[0]
        role = self.material[target.id]["role"]
        if role in {"csv", "rules"}:
            from evidence_gap_router.data_quality import (
                parse_dataset,
                parse_rules,
                validate_dataset,
            )

            try:
                if role == "rules":
                    parse_rules((target.content or "").encode())
                    return "PASS", "strict dictionary parsed"
                rules = parse_rules((view.inputs[1].content or "").encode())
                errors = validate_dataset(parse_dataset((target.content or "").encode()), rules)
                return ("FAIL" if errors else "PASS"), "actual file validation: " + str(errors)
            except ValueError as error:
                return "FAIL", "actual file rejection: " + str(error)
        raw = json.loads(target.content)
        if view.action.checker_id == "audit":
            if raw["diagnostic_minimum"] is None:
                return "UNKNOWN", "raw diagnostic reading absent"
            return (
                "PASS" if raw["value"] >= raw["diagnostic_minimum"] else "FAIL"
            ), "diagnostic comparison with raw imported reading"
        minimum = json.loads(view.obligation.acceptance)["minimum"]
        if target.obligation_id == "task" and view.basis.dependencies:
            minimum = max(minimum, *(json.loads(e.content)["value"] for e in view.inputs[1:]))
        valid = raw["value"] is not None and raw["value"] >= minimum
        return (
            "PASS" if valid else "FAIL"
        ), f"computed raw value {raw['value']} >= declared/bound minimum {minimum}"

    def issue(self, state, action, budget, pool, prefix="bench"):
        s = self.s
        issued = s.start(
            state,
            action,
            f"{prefix}-{len(state.attempts) + 1}",
            budget,
            self.policy,
            candidates=pool,
        )
        attempt = issued.attempts[-1]
        bound = {e.id: e for e in issued.evidence}
        view = s.CallbackView(
            action=attempt.action,
            attempt_id=attempt.id,
            obligation=next(o for o in issued.obligations if o.id == action.obligation_id),
            basis=attempt.basis,
            inputs=tuple(bound[b.evidence_id] for b in attempt.inputs),
        )
        try:
            receipt = self.recorded_callback(view)
            if not isinstance(receipt, s.Result):
                raise ValueError("invalid callback receipt")
            if (
                receipt.attempt_id != attempt.id
                or receipt.action_id != action.id
                or receipt.obligation_id != action.obligation_id
                or receipt.scope != action.scope
                or receipt.target_digest != action.target_digest
            ):
                raise ValueError("callback receipt does not match the issued attempt")
            return s.observe(issued, receipt, self.policy), None
        except Exception as error:
            receipt = view.result(
                actual_resources=s.Resources(actions=1, verifications=None),
                status="unknown",
                side_effects="unknown",
                reason=f"{type(error).__name__}: {error}",
            )
            return s.observe(issued, receipt, self.policy), f"{type(error).__name__}: {error}"

    def recorded_callback(self, view):
        before = len(self.trace)
        wall_start, cpu_start = time.perf_counter(), time.process_time()
        try:
            receipt = self.callback(view)
            return receipt
        finally:
            self.callback_wall += time.perf_counter() - wall_start
            self.callback_cpu += time.process_time() - cpu_start
            if len(self.trace) == before:
                self.trace.append(
                    {
                        "action": view.action.model_dump(mode="json"),
                        "inputs": [
                            {"id": e.id, "digest": e.digest, "content": e.content}
                            for e in view.inputs
                        ],
                        "receipt": None,
                        "note": (
                            "Invocation observed; missing/uncertain receipt retained in State."
                        ),
                    }
                )

    def initialize(self) -> None:
        s, task = self.s, self.task
        budget = s.Budget(limits=s.Resources(actions=100, verifications=100))
        sequence = []
        if task.family in {"F1", "F2", "F3", "F4", "F5"} or task.family == "F6" and task.mode == 5:
            sequence.append(("read", "e0", "main"))
        if task.family in {"F1", "F2", "F4"} or task.family == "F6" and task.mode == 5:
            if task.family in {"F2", "F4"}:
                sequence.extend((("read", "rules0", "main"), ("check", "rules0", "main")))
            if task.family == "F4" and task.mode == 0:
                sequence.append(("read", "alias", "main"))
            if task.family != "F2":
                sequence.append(("check", "e0", "main"))
        if task.family == "F3" and task.checkers > 1 and task.mode != 2:
            sequence.append(("check", "e0", "checker-0"))
        if task.family == "F5":
            sequence.append(("check", "e0", "audit"))
            if task.mode in {2, 3}:
                sequence.append(("read", "alias", "main"))
        for kind, identifier, checker in sequence:
            action = (
                self.read_action(identifier)
                if kind == "read"
                else self.check_action(identifier, self.state, checker=checker)
            )
            # F4 initial verification uses the original rules, before any update.
            if task.family == "F4" and identifier == "e0" and kind == "check":
                action = action.model_copy(
                    update={
                        "dependencies": (
                            s.DependencyRequirement(
                                evidence_id="rules0",
                                obligation_id="rules",
                                scope=self.scope,
                                requirement="verified",
                            ),
                        )
                    }
                )
            self.state, error = self.issue(self.state, action, budget, (action,), prefix="initial")
            if error:
                raise RuntimeError("initialization callback failed: " + error)
        if task.family == "F5":
            self.negative_ids = {c.id for c in self.state.checks if c.status in {"FAIL", "UNKNOWN"}}
            self.alias_wrong = task.mode == 3
            if task.mode == 2:
                conflict = s.Contradiction(
                    id="disputed",
                    obligation_id="task",
                    scope=self.scope,
                    evidence_ids=("e0", "alias"),
                    reason="diagnostic reading conflicts with actual raw value",
                )
                self.state = s.State(**{**self.state.model_dump(), "contradictions": (conflict,)})
                self.host_updates.append(
                    {"kind": "contradiction", "record": conflict.model_dump(mode="json")}
                )
        if task.family == "F4":
            if task.mode == 0:
                conflict = s.Contradiction(
                    id="disputed",
                    obligation_id="task",
                    scope=self.scope,
                    evidence_ids=("e0", "alias"),
                    reason="host requires an explicit current comparison of both readings",
                )
                self.state = s.State(**{**self.state.model_dump(), "contradictions": (conflict,)})
                action = self.check_action(
                    "e0", self.state, purpose="contradiction_resolution", target=conflict.id
                )
                self.state, error = self.issue(
                    self.state, action, budget, (action,), prefix="initial"
                )
                if error:
                    raise RuntimeError("initialization callback failed: " + error)
                obligations = tuple(
                    o.model_copy(update={"contract_revision": "2"}) if o.id == "task" else o
                    for o in self.state.obligations
                )
                self.state = s.State(**{**self.state.model_dump(), "obligations": obligations})
                self.host_updates.append(
                    {
                        "kind": "contract_revision",
                        "obligation_id": "task",
                        "before": "1",
                        "after": "2",
                    }
                )
            elif task.mode in {1, 2, 3, 4}:
                if not hasattr(s, "invalidate"):
                    raise NotImplementedError("new host invalidation API is unsupported by v0.2.0")
                target_kind = "check" if task.mode == 2 else "evidence"
                target_id = (
                    self.state.checks[-1].id
                    if target_kind == "check"
                    else ("e0" if task.mode == 1 else "rules0")
                )
                event = s.Invalidation(
                    id="host-expiry",
                    kind=target_kind,
                    target_id=target_id,
                    obligation_id="task" if task.mode in {1, 2} else "rules",
                    scope=self.scope,
                    reason="declared current-world update",
                )
                self.state = s.invalidate(self.state, event)
                self.host_updates.append(
                    {"kind": "invalidation", "record": event.model_dump(mode="json")}
                )
                self.invalidated.add((target_kind, target_id))
                if task.mode == 1:
                    self.add("replacement", task.value + 1, "task", "origin-replacement")
                elif task.mode == 4:
                    self.add("extra", task.value + 1, "rules", "rules-new")
            elif task.mode == 5:
                self.add("unrelated", task.value + 1, "rules", "unrelated-origin")
                # Explicit host initial material; no check or callback cost is invented.
                m = self.material["unrelated"]
                addition = s.Evidence(
                    id="unrelated",
                    obligation_id="rules",
                    scope=self.scope,
                    digest=digest(m["raw"]),
                    content=m["raw"].decode(),
                    producer="host-seed",
                    source=m["source"],
                    provenance_group=m["group"],
                )
                self.state = s.State(
                    **{**self.state.model_dump(), "evidence": (*self.state.evidence, addition)}
                )
                self.host_updates.append(
                    {
                        "kind": "unrelated_host_seed",
                        "record": addition.model_dump(mode="json"),
                        "callback_cost": 0,
                    }
                )
        self.initial_trace, self.trace = self.trace, []
        self.initial_callback_wall, self.callback_wall = self.callback_wall, 0.0
        self.initial_callback_cpu, self.callback_cpu = self.callback_cpu, 0.0
        self.initial_results = len(self.state.results)
        # Limits are total public costs: add common initialization to frozen continuation bounds.
        used_actions = sum(r.actual_resources.actions or 0 for r in self.state.results)
        used_checks = sum(r.actual_resources.verifications or 0 for r in self.state.results)
        self.budget = s.Budget(
            limits=s.Resources(
                actions=used_actions + task.actions, verifications=used_checks + task.verifications
            )
        )


def independent_rules(raw: bytes) -> dict:
    """Only the declared finite file contract, without the SDK's parser."""
    if len(raw) > 1048576:
        raise ValueError("dictionary byte limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    rules = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal, object_pairs_hook=unique)
    required = {"required_columns", "primary_key", "minimum_amount", "allowed_currencies"}
    if (
        not isinstance(rules, dict)
        or not required <= set(rules)
        or set(rules) - required - {"description"}
    ):
        raise ValueError("dictionary fields")
    if (
        rules["primary_key"] != "order_id"
        or not isinstance(rules["required_columns"], list)
        or len(rules["required_columns"]) != 3
        or set(rules["required_columns"]) != {"order_id", "amount", "currency"}
        or isinstance(rules["minimum_amount"], bool)
        or not isinstance(rules["minimum_amount"], (int, Decimal))
    ):
        raise ValueError("dictionary types")
    if "description" in rules and not isinstance(rules["description"], str):
        raise ValueError("dictionary description")
    minimum = independent_decimal(str(rules["minimum_amount"]))
    if minimum < 0:
        raise ValueError("dictionary minimum")
    currencies = rules["allowed_currencies"]
    if (
        not isinstance(currencies, list)
        or not currencies
        or any(not isinstance(c, str) or not c for c in currencies)
        or len(set(currencies)) != len(currencies)
    ):
        raise ValueError("dictionary currencies")
    return rules


def independent_decimal(text: str) -> Decimal:
    value = Decimal(text)
    if not value.is_finite():
        raise ValueError("nonfinite numeric input")
    parts = value.as_tuple()
    if (
        len(text.strip()) > 256
        or len(parts.digits) > 64
        or abs(parts.exponent) > 128
        or abs(value.adjusted()) > 128
    ):
        raise ValueError("finite numeric input bounds")
    return value


def file_oracle(raw_csv: bytes, raw_rules: bytes) -> bool:
    """Independent exact input oracle, separate from the SDK parser/checker."""
    try:
        rules = independent_rules(raw_rules)
        minimum = Decimal(str(rules["minimum_amount"]))
        rows = list(csv.reader(io.StringIO(raw_csv.decode("utf-8-sig"), newline="")))
        if not rows or len(rows[0]) != 3 or set(rows[0]) != {"order_id", "amount", "currency"}:
            return False
        if not 1 <= len(rows) - 1 <= 10000 or len(raw_csv) > 1048576:
            return False
        seen = set()
        for values in rows[1:]:
            if len(values) != 3:
                return False
            row = dict(zip(rows[0], values, strict=True))
            amount = independent_decimal(row["amount"])
            if (
                not amount.is_finite()
                or amount < minimum
                or not row["order_id"]
                or row["order_id"] in seen
                or row["currency"] not in rules["allowed_currencies"]
            ):
                return False
            seen.add(row["order_id"])
        return True
    except (ValueError, ArithmeticError, KeyError, UnicodeError, TypeError, csv.Error):
        return False


def oracle(world: World, state) -> dict:
    """Inspect explicit world truth and receipts, without router acceptance functions."""
    evidence = {e.id: e for e in state.evidence}
    obligations = {o.id: o for o in state.obligations}

    def contract(obligation):
        fields = {
            name: getattr(obligation, name)
            for name in (
                "id",
                "scope",
                "contract_revision",
                "acceptance",
                "min_evidence",
                "min_provenance_groups",
            )
        }
        fields["required_verifiers"] = sorted(set(obligation.required_verifiers))
        return digest(json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    invalid = set(world.invalidated)
    # Invalidation history is also checked independently where the API is available.
    for record in getattr(state, "invalidations", ()):
        invalid.add((record.kind, record.target_id))
    invalid.update(
        ("evidence", event.target_id) for event in state.supersessions if event.kind == "evidence"
    )

    def current(check):
        basis = check.basis
        if check.expired or check.withdrawn or ("check", check.id) in invalid:
            return False
        if basis is None:
            return check.legacy and check.status in {"FAIL", "UNKNOWN"}
        owner = obligations.get(check.obligation_id)
        if owner is None or (
            basis.obligation_id != check.obligation_id
            or basis.scope != check.scope
            or basis.contract_fingerprint != contract(owner)
            or basis.checker_id != check.verifier_id
            or basis.target.digest != check.target_digest
        ):
            return False
        if check.verifier_id not in world.policy.trusted_verifiers:
            return False
        if not any(
            "verify" in registration.roles
            and any(
                permission.checker_id == basis.checker_id
                and permission.revision == basis.checker_revision
                and basis.purpose in permission.purposes
                for permission in registration.checkers
            )
            for registration in world.policy.handlers
        ):
            return False
        for binding in (basis.target, *basis.dependencies):
            target = evidence.get(binding.evidence_id)
            owner = obligations.get(binding.obligation_id)
            if (
                target is None
                or owner is None
                or target.expired
                or target.withdrawn
                or ("evidence", target.id) in invalid
                or target.digest != binding.digest
                or (target.obligation_id, target.scope) != (binding.obligation_id, binding.scope)
                or binding.contract_fingerprint != contract(owner)
            ):
                return False
            material = world.material.get(target.id)
            if (
                material is None
                or target.digest != digest(material["raw"])
                or target.content != material["raw"].decode("utf-8-sig")
            ):
                return False
        if basis.purpose != "content":
            kind = "check" if basis.purpose == "check_resolution" else "contradiction"
            records = state.checks if kind == "check" else state.contradictions
            subject = next((r for r in records if r.id == basis.resolution_target_id), None)
            if subject is None:
                return False
            if kind == "check" and (
                subject.basis is None
                or subject.basis.target.evidence_id != basis.target.evidence_id
                or (subject.obligation_id, subject.scope, subject.target_digest)
                != (basis.obligation_id, basis.scope, basis.target.digest)
            ):
                return False
            related = []
            if kind == "contradiction":
                for identifier in subject.evidence_ids:
                    item = evidence.get(identifier)
                    if item is None:
                        return False
                    related.append(
                        {
                            "evidence_id": item.id,
                            "digest": item.digest,
                            "obligation_id": item.obligation_id,
                            "scope": item.scope,
                            "contract_fingerprint": contract(obligations[item.obligation_id]),
                            "requirement": "active",
                        }
                    )
            expected = digest(
                json.dumps(
                    {
                        "kind": kind,
                        "record": subject.model_dump(mode="json"),
                        "contract": contract(obligations[subject.obligation_id]),
                        "related": related,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            if basis.resolution_fingerprint != expected:
                return False
        return not (
            world.policy.prohibit_self_verification
            and evidence[basis.target.evidence_id].producer == basis.checker_id
        )

    receipts = {c.id for r in state.results for c in r.checks}
    applicable = []
    for check in state.checks:
        basis = check.basis
        if (
            not current(check)
            or check.status != "PASS"
            or basis is None
            or check.id not in receipts
            or check.expired
            or check.withdrawn
            or ("check", check.id) in invalid
        ):
            continue
        target = evidence.get(basis.target.evidence_id)
        obligation = obligations.get(check.obligation_id)
        if (
            target is None
            or obligation is None
            or target.expired
            or target.withdrawn
            or ("evidence", target.id) in invalid
        ):
            continue
        if target.digest != basis.target.digest or basis.contract_fingerprint != contract(
            obligation
        ):
            continue
        if world.policy.prohibit_self_verification and check.verifier_id == target.producer:
            continue
        if any(
            b.evidence_id not in evidence
            or evidence[b.evidence_id].digest != b.digest
            or ("evidence", b.evidence_id) in invalid
            or evidence[b.evidence_id].expired
            or evidence[b.evidence_id].withdrawn
            or b.contract_fingerprint != contract(obligations[b.obligation_id])
            for b in basis.dependencies
        ):
            continue
        if world.task.family == "F8":
            if target.obligation_id == "task":
                correct = file_oracle(*world.file_bytes)
            else:
                try:
                    independent_rules(world.file_bytes[1])
                    correct = True
                except (ValueError, ArithmeticError, KeyError, UnicodeError, TypeError):
                    correct = False
        else:
            raw = json.loads(target.content)
            minimum = json.loads(obligation.acceptance)["minimum"]
            if target.obligation_id == "task" and basis.dependencies:
                minimum = max(
                    minimum,
                    *(
                        json.loads(evidence[b.evidence_id].content)["value"]
                        for b in basis.dependencies
                    ),
                )
            correct = raw.get("value", 0) is not None and raw.get("value", 0) >= minimum
        if correct:
            applicable.append(check)
    grounded = []
    while True:
        added = [
            c
            for c in applicable
            if c not in grounded
            if all(
                b.requirement != "verified"
                or (
                    any(
                        p.basis.target.evidence_id == b.evidence_id
                        and p.basis.purpose in {"content", "check_resolution"}
                        for p in grounded
                    )
                    and set(obligations[b.obligation_id].required_verifiers)
                    <= {
                        p.verifier_id
                        for p in grounded
                        if p.basis.target.evidence_id == b.evidence_id
                        and p.basis.purpose in {"content", "check_resolution"}
                    }
                )
                for b in c.basis.dependencies
            )
        ]
        if not added:
            break
        grounded.extend(added)
    applicable = grounded
    resolved = set()
    conflicts_resolved = set()
    for event in state.supersessions:
        replacement_id = event.replacement_id if event.kind == "check" else event.check_id
        replacement = next((c for c in applicable if c.id == replacement_id), None)
        if replacement is None:
            continue
        basis = replacement.basis
        if basis.resolution_target_id != event.target_id:
            continue
        if event.kind == "check" and basis.purpose == "check_resolution":
            old = next(c for c in state.checks if c.id == event.target_id)
            if old.basis and old.basis.target.evidence_id == basis.target.evidence_id:
                resolved.add(old.id)
        elif event.kind == "contradiction" and basis.purpose == "contradiction_resolution":
            conflict = next(c for c in state.contradictions if c.id == event.target_id)
            if set(conflict.evidence_ids) <= {
                basis.target.evidence_id,
                *(b.evidence_id for b in basis.dependencies),
            }:
                conflicts_resolved.add(conflict.id)
    negatives = [
        c.id
        for c in state.checks
        if current(c)
        and c.status in {"FAIL", "UNKNOWN"}
        and c.id not in resolved
        and ("check", c.id) not in invalid
    ]
    conflicts = [
        c.id for c in state.contradictions if c.blocking and c.id not in conflicts_resolved
    ]
    solved = []
    raw_goal_met = []
    unchecked_targets = []
    for obligation in state.obligations:
        if not obligation.required:
            continue
        targets = [
            e
            for e in state.evidence
            if e.obligation_id == obligation.id
            and ("evidence", e.id) not in invalid
            and not e.expired
            and not e.withdrawn
        ]
        accepted = []
        for target in targets:
            checks = [
                c
                for c in applicable
                if c.basis.target.evidence_id == target.id
                and c.basis.purpose in {"content", "check_resolution"}
            ]
            if checks and set(obligation.required_verifiers) <= {c.verifier_id for c in checks}:
                accepted.append(target)
        # Positive deduplication is independent from exact-ID negative resolution.
        # Construct explicit equivalence components instead of using router helpers.
        components = [{e.id} for e in targets]
        for left in targets:
            for right in targets:
                if left.digest != right.digest or not (
                    left.source
                    and left.source == right.source
                    or left.provenance_group
                    and left.provenance_group == right.provenance_group
                ):
                    continue
                a = next(c for c in components if left.id in c)
                b = next(c for c in components if right.id in c)
                if a is not b:
                    a.update(b)
                    components.remove(b)
        accepted_ids = {e.id for e in accepted}
        supported_components = [c for c in components if c & accepted_ids]
        unchecked = [e.id for e in targets if not any(e.id in c for c in supported_components)]
        unchecked_targets.extend(unchecked)
        source_groups = [{e.provenance_group} for e in accepted if e.provenance_group]
        for source in {e.source for e in accepted if e.source}:
            declared = {e.provenance_group for e in accepted if e.source == source}
            overlapping = [g for g in source_groups if g & declared]
            if overlapping:
                merged = set().union(*overlapping)
                source_groups = [g for g in source_groups if g not in overlapping] + [merged]
        groups = {frozenset(g) for g in source_groups}
        if (
            len(supported_components) >= obligation.min_evidence
            and len(groups) >= obligation.min_provenance_groups
            and not any(
                c.obligation_id == obligation.id and c.id in negatives for c in state.checks
            )
            and not any(
                c.obligation_id == obligation.id and c.id in conflicts for c in state.contradictions
            )
        ):
            raw_goal_met.append(obligation.id)
            if not unchecked:
                solved.append(obligation.id)
    denominator = sum(o.required for o in state.obligations)
    return {
        "completion": len(solved) == denominator and not negatives and not conflicts,
        "raw_goal_met": len(raw_goal_met) == denominator,
        "solved_required": len(solved),
        "required": denominator,
        "negative_records_remaining": negatives,
        "contradictions_remaining": conflicts,
        "applicable_pass_ids": [c.id for c in applicable],
        "unchecked_current_target_ids": unchecked_targets,
    }


def select(world: World, state, pool: tuple, method: str, rng: random.Random):
    s = world.s
    if method == "egr":
        return s.plan(state, pool, world.budget, world.policy).action
    if not hasattr(s, "feasible_actions"):
        raise NotImplementedError("public shared feasibility API unavailable in this version")
    feasible = s.feasible_actions(state, pool, world.budget, world.policy)
    if not feasible:
        return None
    if method == "fixed-feasible":
        return feasible[0]
    if method in {"without-gap-rank", "without-provenance-rank"}:
        owners = {o.id: o for o in state.obligations}
        best = min(
            (not owners[a.obligation_id].required, -owners[a.obligation_id].priority)
            for a in feasible
        )
        feasible = tuple(
            a
            for a in feasible
            if (not owners[a.obligation_id].required, -owners[a.obligation_id].priority) == best
        )
        if method == "without-gap-rank":
            return feasible[0]
    if method in {"verify-first", "without-provenance-rank"}:
        return next((a for a in feasible if a.kind == "verify"), feasible[0])
    if method == "random-feasible":
        return rng.choice(feasible)
    raise ValueError("Unknown method")


def trial(task: Task, variant: str, method: str, random_seed: int, frozen: dict) -> dict:
    started = time.perf_counter()
    cpu_start = time.process_time()
    tracemalloc.start()
    row = {
        "question": "Q1/Q2",
        "task": task.document(),
        "task_id": task.id,
        "variant": variant,
        "random_seed": random_seed,
        "method": method,
        "manifest_sha256": digest(PROTOCOL.read_bytes()),
        "implementation_commit": frozen.get("implementation_commit"),
        "wheel_sha256": frozen.get(
            "baseline_wheel_sha256" if environment()["package"] == "0.2.0" else "wheel_sha256"
        ),
        "package_sha256": frozen.get(
            "baseline_package_sha256"
            if environment()["package"] == "0.2.0"
            else "candidate_package_sha256"
        ),
        "environment": environment(),
        "status": "completed",
        "exception": None,
        "timeout": False,
        "tokens": None,
        "money": None,
        "measurement_observer": (
            "Q1/Q2 timing includes tracemalloc overhead; Q3 timing is separate/uninstrumented."
        ),
    }
    world = World(task, variant)
    planning_cpu, execution_seconds, serialization_seconds = 0.0, 0.0, 0.0
    try:
        if method != "direct-pipeline":
            world.initialize()
        state = world.state
        init_results = tuple(state.results)
        if method == "direct-pipeline":
            if task.family == "F8":
                # Skip routed transitions; shared World setup remains in measured cost.
                from evidence_gap_router.data_quality import (
                    parse_dataset,
                    parse_rules,
                    validate_dataset,
                )

                try:
                    data_raw = world.material["e0"]["path"].read_bytes()
                    dictionary_raw = world.material["rules0"]["path"].read_bytes()
                    errors = validate_dataset(parse_dataset(data_raw), parse_rules(dictionary_raw))
                    complete = not errors
                except ValueError:
                    complete = False
                truth = file_oracle(*world.file_bytes)
            else:
                complete = all(
                    json.loads(m["raw"])["value"] >= task.threshold for m in world.material.values()
                )
                truth = all(
                    json.loads(m["raw"])["value"] >= task.threshold for m in world.material.values()
                )
            row.update(
                {
                    "oracle": {
                        "completion": complete and truth,
                        "solved_required": int(complete and truth),
                        "required": 1,
                    },
                    "router_satisfied": complete,
                    "false_satisfied": complete and not truth,
                    "callbacks": None,
                    "verifications": None,
                    "pipeline_material_reads": 2 if task.family == "F8" else task.sources,
                    "pipeline_validation_operations": 1,
                    "bound_applicability": (
                        "Different batching/receipt contract; not comparable to SDK bounds; "
                        "excluded from primary comparisons. Shared World/State/Policy/material "
                        "setup remains in measured cost; a minimal ordinary pipeline "
                        "can be cheaper."
                    ),
                    "stop_reason": "direct-accepted" if complete else "direct-rejected",
                    "initialization_actions": 0,
                    "initialization_verifications": 0,
                    "trace": [{"raw_sha256": [digest(m["raw"]) for m in world.material.values()]}],
                    "snapshot_resume": None,
                    "state": None,
                    "reference_only": True,
                }
            )
            return row
        rng = random.Random(random_seed)
        stop, error = "max_steps_reached", None
        if method == "egr":
            import evidence_gap_router.runner as runner

            original_plan = runner.plan

            def timed_plan(*args, **kwargs):
                nonlocal planning_cpu
                begin = time.process_time()
                try:
                    return original_plan(*args, **kwargs)
                finally:
                    planning_cpu += time.process_time() - begin

            runner.plan = timed_plan
            begin = time.perf_counter()
            try:
                report = world.s.run(
                    state,
                    world.pool,
                    world.budget,
                    world.policy,
                    {"read": world.recorded_callback, "check": world.recorded_callback},
                    max_steps=manifest()["max_steps"],
                )
                state, stop, error = report.state, report.stop_reason, report.error
                row["runner_decision"] = report.decision.model_dump(mode="json")
                world.state = state
            finally:
                runner.plan = original_plan
                execution_seconds = time.perf_counter() - begin
        for _ in range(0 if method == "egr" else manifest()["max_steps"]):
            if time.perf_counter() - started > manifest()["task_timeout_seconds"]:
                row["timeout"] = True
                stop = "task_timeout"
                break
            before = time.process_time()
            try:
                pool = world.pool(state)
                action = select(world, state, pool, method, rng)
            except NotImplementedError:
                raise
            except Exception as exc:
                stop, error = "factory_error", f"{type(exc).__name__}: {exc}"
                break
            planning_cpu += time.process_time() - before
            if action is None:
                stop = "router_stopped"
                break
            before = time.perf_counter()
            state, error = world.issue(state, action, world.budget, pool)
            world.state = state
            execution_seconds += time.perf_counter() - before
            if error:
                stop = "callback_error"
                break
            receipt_value = world.trace[-1]["receipt"] if world.trace else None
            if not receipt_value or not (
                receipt_value["evidence"]
                or receipt_value["checks"]
                or receipt_value["supersessions"]
            ):
                stop = "no_progress"
                break
        before = time.process_time()
        decision = world.s.plan(state, (), world.budget, world.policy)
        planning_cpu += time.process_time() - before
        assessed = oracle(world, state)
        before = time.perf_counter()
        try:
            dump = getattr(world.s, "dump_snapshot", world.s.dump_json)(state)
            load = getattr(world.s, "load_snapshot", world.s.load_json)(dump, world.s.State)
            snapshot_resume = (
                load == state and world.s.plan(load, (), world.budget, world.policy) == decision
            )
        except Exception as exc:
            snapshot_resume = False
            row["snapshot_exception"] = f"{type(exc).__name__}: {exc}"
        serialization_seconds = time.perf_counter() - before
        continuation = state.results[len(init_results) :]
        read_keys, verification_keys = set(), set()
        identical_reads, repeated_verifications = 0, 0
        for record in world.initial_trace + world.trace:
            action = record["action"]
            if action["kind"] != "verify":
                material = world.material.get(action["produces_evidence_id"])
                if material:
                    key = (digest(material["raw"]), material["source"], material["group"])
                    identical_reads += key in read_keys
                    read_keys.add(key)
            elif record.get("receipt"):
                for check in record["receipt"]["checks"]:
                    key = json.dumps(check["basis"], sort_keys=True, separators=(",", ":"))
                    repeated_verifications += key in verification_keys
                    verification_keys.add(key)
        row.update(
            {
                "oracle": assessed,
                "router_satisfied": decision.stop_reason == "satisfied",
                "false_satisfied": decision.stop_reason == "satisfied"
                and not assessed["completion"],
                "callbacks": len(continuation),
                "verifications": (
                    None
                    if any(r.actual_resources.verifications is None for r in continuation)
                    else sum(r.actual_resources.verifications for r in continuation)
                ),
                "initialization_actions": sum(
                    r.actual_resources.actions or 0 for r in init_results
                ),
                "initialization_verifications": sum(
                    r.actual_resources.verifications or 0 for r in init_results
                ),
                "resource_unknown": any(
                    r.actual_resources.verifications is None for r in continuation
                ),
                "resource_overrun": (
                    True
                    if len(continuation) > task.actions
                    or sum(r.actual_resources.verifications or 0 for r in continuation)
                    > task.verifications
                    else None
                    if any(r.actual_resources.verifications is None for r in continuation)
                    else False
                ),
                "identical_material_read_invocations_including_initialization": identical_reads,
                "same_basis_verification_invocations_including_initialization": (
                    repeated_verifications
                ),
                "duplicate_metric_limitation": (
                    "Repeated bytes or basis are observed counts, not assumed unnecessary work."
                ),
                "stop_reason": stop,
                "domain_stop": decision.stop_reason,
                "exception": error,
                "snapshot_resume": snapshot_resume,
                "trace": world.trace,
                "initial_trace": world.initial_trace,
                "host_updates": world.host_updates,
                "state": state.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
            }
        )
    except NotImplementedError as error:
        row.update(
            {
                "status": "unsupported",
                "exception": str(error),
                "oracle": None,
                "false_satisfied": None,
                "stop_reason": "unsupported_old_api",
                "trace": world.trace,
                "initial_trace": world.initial_trace,
                "state": world.state.model_dump(mode="json"),
            }
        )
    except Exception as error:
        row.update(
            {
                "status": "exception",
                "exception": f"{type(error).__name__}: {error}",
                "oracle": None,
                "false_satisfied": None,
                "stop_reason": "exception",
                "trace": world.trace,
                "state": world.state.model_dump(mode="json"),
                "callbacks": None,
                "verifications": None,
            }
        )
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        row.update(
            {
                "planning_cpu_seconds": planning_cpu,
                "execution_and_transitions_seconds": execution_seconds,
                "callback_wall_seconds": world.callback_wall,
                "callback_cpu_seconds": world.callback_cpu,
                "initial_callback_wall_seconds": world.initial_callback_wall,
                "initial_callback_cpu_seconds": world.initial_callback_cpu,
                "serialization_seconds": serialization_seconds,
                "cpu_seconds": time.process_time() - cpu_start,
                "end_to_end_seconds": time.perf_counter() - started,
                "peak_traced_python_allocation_bytes": peak,
            }
        )
        world.directory.cleanup()
    return row


def run_trials(
    phase: str, output: Path, *, frozen: dict, limit: int | None = None, version_only: bool = False
) -> None:
    if output.exists():
        raise ValueError("Results exist; never silently overwrite measured evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with output.open("x", encoding="utf-8") as stream:
        for task in generate(phase, limit=limit):
            variants = manifest()["variants"] if phase == "holdout" else ["original"]
            for variant in variants:
                methods = (
                    ["egr"]
                    if version_only
                    else ["egr", "fixed-feasible", "verify-first", "random-feasible"]
                )
                if not version_only and task.family in manifest()["ablations"]:
                    methods.append(manifest()["ablations"][task.family])
                if not version_only and task.family in {"F6", "F8"}:
                    methods.append("direct-pipeline")
                for method in methods:
                    seeds = manifest()["random_seeds"] if method == "random-feasible" else [0]
                    for seed in seeds:
                        remaining = manifest()["experiment_timeout_seconds"] - (
                            time.perf_counter() - started
                        )
                        row = {
                            "question": "Q1/Q2",
                            "task_id": task.id,
                            "task": task.document(),
                            "variant": variant,
                            "method": method,
                            "random_seed": seed,
                            "status": "unexecuted",
                            "timeout": False,
                            "exception": None,
                            "oracle": None,
                            "false_satisfied": None,
                            "callbacks": None,
                            "verifications": None,
                            "tokens": None,
                            "money": None,
                            "state": None,
                            "trace": [],
                            "reference_only": method == "direct-pipeline",
                            "manifest_sha256": digest(PROTOCOL.read_bytes()),
                            "implementation_commit": frozen.get("implementation_commit"),
                            "wheel_sha256": frozen.get(
                                "baseline_wheel_sha256"
                                if environment()["package"] == "0.2.0"
                                else "wheel_sha256"
                            ),
                            "environment": environment(),
                            "stop_reason": "experiment_budget_exhausted",
                        }
                        if remaining > 0:
                            timeout = min(manifest()["task_timeout_seconds"], remaining)
                            worker_started = time.perf_counter()
                            try:
                                outcome = subprocess.run(
                                    [sys.executable, "-m", "benchmarks.harness", "worker"],
                                    input=json.dumps(
                                        {
                                            "task": task.document(),
                                            "variant": variant,
                                            "method": method,
                                            "seed": seed,
                                            "frozen": frozen,
                                        }
                                    ),
                                    capture_output=True,
                                    text=True,
                                    check=True,
                                    timeout=timeout,
                                )
                                row = json.loads(outcome.stdout)
                                row["whole_worker_seconds"] = time.perf_counter() - worker_started
                                row["startup_import_and_ipc_seconds"] = max(
                                    0.0, row["whole_worker_seconds"] - row["end_to_end_seconds"]
                                )
                            except subprocess.TimeoutExpired:
                                row.update(
                                    status="timeout",
                                    timeout=True,
                                    timeout_seconds=timeout,
                                    right_censored=True,
                                    stop_reason="worker_timeout",
                                    timeout_scope=(
                                        "whole trial worker, startup/import/trial/serialization "
                                        "included; phase unknown"
                                    ),
                                    trace_unavailable_reason=(
                                        "worker terminated before final trace record"
                                    ),
                                )
                            except (subprocess.CalledProcessError, ValueError) as error:
                                row.update(
                                    status="exception",
                                    exception=str(error),
                                    stop_reason="worker_exception",
                                    stderr=getattr(error, "stderr", None),
                                )
                            row.setdefault(
                                "whole_worker_seconds", time.perf_counter() - worker_started
                            )
                        stream.write(json.dumps(row, ensure_ascii=True) + "\n")
                        stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lock = commands.add_parser("freeze")
    lock.add_argument("--output", type=Path, required=True)
    lock.add_argument("--implementation-commit", required=True)
    lock.add_argument("--wheel", type=Path, required=True)
    lock.add_argument("--baseline-wheel", type=Path, required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--phase", choices=("development", "holdout"), default="development")
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--freeze", type=Path)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--version-only", action="store_true")
    commands.add_parser("worker")
    args = parser.parse_args()
    if args.command == "worker":
        request = json.loads(sys.stdin.read())
        result = trial(
            Task(**request["task"]),
            request["variant"],
            request["method"],
            request["seed"],
            request["frozen"],
        )
        print(json.dumps(result, ensure_ascii=True))
    elif args.command == "freeze":
        freeze(args.output, args.implementation_commit, args.wheel, args.baseline_wheel)
    else:
        if args.phase == "holdout" and (args.freeze is None or args.limit is not None):
            parser.error("Holdout requires freeze record and complete frozen task count")
        frozen = validate_freeze(args.freeze, phase=args.phase) if args.freeze else {}
        run_trials(
            args.phase, args.output, frozen=frozen, limit=args.limit, version_only=args.version_only
        )


if __name__ == "__main__":
    main()
