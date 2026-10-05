"""Finite helper inputs and separate-process diagnostics; no formal controller.

The small reference scans simultaneous grounded alternatives using public record
fields. It does not call plan, make_basis, coverage, or private acceptance code.
Large inputs deliberately leave this bounded reference unassessed. The worker
uses the same public plan/start/observe sequence on either installed version.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import tracemalloc
from hashlib import sha256

from benchmarks.harness import environment
from benchmarks.tasks import manifest


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _parents(topology: str, depth: int) -> list[list[int]]:
    if topology == "chain":
        return [[] if i == 0 else [i - 1] for i in range(depth)]
    if topology == "diamond":
        return [list(range(max(0, i - 2), i)) for i in range(depth)]
    if topology == "shared":
        return [[] if i == 0 else sorted({0, (i - 1) // 2}) for i in range(depth)]
    if topology == "branches":
        return [[] if i == 0 else [0] for i in range(depth)]
    if topology == "cycle":
        return [[(i - 1) % depth] for i in range(depth)]
    raise ValueError("unknown helper topology")


def cases(config: dict | None = None) -> tuple[dict, ...]:
    """The frozen manifest's finite case list, without executing any case."""
    cfg = manifest()["helper_scaling"] if config is None else config
    values = [
        {
            "id": f"chain-{depth}-{alternatives}",
            "topology": "chain",
            "depth": depth,
            "alternatives": alternatives,
            "boundary": "none",
        }
        for depth in cfg["depths"]
        for alternatives in cfg["alternatives"]
    ]
    values.extend(
        {
            "id": f"{topology}-{depth}-{cfg['additional_alternatives']}",
            "topology": topology,
            "depth": depth,
            "alternatives": cfg["additional_alternatives"],
            "boundary": "none",
        }
        for topology in cfg["additional_topologies"]
        for depth in cfg["additional_depths"]
    )
    values.extend(
        {
            "id": name,
            "topology": "cycle" if name in ("ungrounded-cycle", "grounded-exit") else "chain",
            "depth": cfg["boundary_depth"],
            "alternatives": cfg["boundary_alternatives"],
            "boundary": name,
        }
        for name in cfg["boundary_cases"]
    )
    return tuple(values)


def generated_confirmation(seed: int, count: int = 32) -> tuple[dict, ...]:
    """Unused-seed recipes vary actual prerequisites, validity and authority.

    Calling the generator does not run a planner or consult an outcome label.
    Cyclic recipes are kept rather than filtered for solvability.
    """
    rng = random.Random(seed)
    conditions = (
        "none",
        "half-current",
        "verified-two-checkers",
        "verified-three-checkers",
        "unavailable-checker",
        "wrong-scope",
        "wrong-digest",
        "invalidated-dependency",
        "contract-update",
        "satisfied-owner",
        "optional-owner",
        "grounded-exit",
    )
    result = []
    for index in range(count):
        depth = rng.randrange(3, 9)
        boundary = conditions[index % len(conditions)]
        cyclic = boundary == "grounded-exit" or index % 7 == 0
        parents = []
        for i in range(depth):
            choices = list(range(depth)) if cyclic else list(range(i))
            parents.append(sorted(rng.sample(choices, min(len(choices), rng.randrange(3)))))
        result.append(
            {
                "id": f"confirmation-{index:02}",
                "seed": seed,
                "index": index,
                "topology": "generated",
                "depth": depth,
                "alternatives": rng.randrange(1, 4),
                "boundary": boundary,
                "parents": parents,
                "root_indices": sorted(
                    rng.sample(range(depth), rng.randrange(1, min(3, depth) + 1))
                ),
                "available_handlers": rng.choice([None, None, None, ["read"], ["check"], []]),
                "remaining_actions": rng.choice([10000, 10000, depth, 1, 0]),
            }
        )
    return tuple(result)


def _changed(value, **fields):
    return type(value)(**{**value.model_dump(), **fields})


def _transition(state, action, pool, budget, policy, world, attempt_id):
    """One genuine callback on exactly the public issued inputs and full pool."""
    import evidence_gap_router as sdk

    issued = sdk.start(state, action, attempt_id, budget, policy, candidates=pool)
    attempt = issued.attempts[-1]
    view = sdk.CallbackView(
        action=action,
        attempt_id=attempt_id,
        obligation=next(o for o in state.obligations if o.id == action.obligation_id),
        basis=attempt.basis,
        inputs=tuple(
            next(e for e in state.evidence if e.id == b.evidence_id) for b in attempt.inputs
        ),
    )
    if action.kind == "verify":
        valid = all(
            e.content is not None and _digest(e.content) == e.digest and int(e.content) >= 0
            for e in view.inputs
        )
        receipt = view.result(
            actual_resources=sdk.Resources(actions=1, verifications=1),
            checks=(
                view.check(
                    status="PASS" if valid else "FAIL",
                    reason="Parsed nonnegative raw integer and checked digest",
                ),
            ),
        )
    else:
        receipt = view.result(
            actual_resources=sdk.Resources(actions=1, verifications=0),
            evidence=(world[action.produces_evidence_id],),
        )
    return sdk.observe(issued, receipt), receipt


def build(case: dict) -> dict:
    """Materialize finite candidates; real seed receipts are explicitly timed."""
    import evidence_gap_router as sdk

    begin = time.perf_counter()
    depth, alternatives, boundary = case["depth"], case["alternatives"], case["boundary"]
    if not 1 <= depth <= 64 or not 1 <= alternatives <= 4:
        raise ValueError("helper input bound exceeded")
    parents = (
        case.get("parents", _parents(case["topology"], depth))
        if (case["topology"] != "generated")
        else case["parents"]
    )
    if len(parents) != depth or any(j < 0 or j >= depth for row in parents for j in row):
        raise ValueError("invalid finite prerequisite indices")
    checker_count = (
        3
        if boundary == "verified-three-checkers"
        else (2 if boundary in ("verified-two-checkers", "unavailable-checker") else 1)
    )
    identifiers = tuple(f"v{i + 1}" for i in range(checker_count))
    helper = sdk.Obligation(
        id="helper",
        scope="helper",
        description="Finite helper material",
        acceptance="integer",
        required=boundary == "satisfied-owner",
        required_verifiers=identifiers if checker_count > 1 else (),
    )
    task = sdk.Obligation(
        id="task",
        scope="task",
        description="Validate root",
        acceptance="integer",
        required=True,
    )
    state = sdk.State(obligations=(task, helper))
    world = {
        name: sdk.Evidence(
            id=name,
            obligation_id=owner,
            scope=owner,
            digest=_digest(content),
            content=content,
            producer="reader",
            source=name,
            provenance_group=name,
        )
        for name, owner, content in [("root", "task", "100"), ("anchor", "helper", "101")]
        + [(f"h{i}", "helper", str(i)) for i in range(depth)]
    }
    permissions = identifiers[:-1] if boundary == "unavailable-checker" else identifiers
    policy = sdk.Policy(
        trusted_verifiers=identifiers,
        max_pending_verifications=1,
        handlers=(
            sdk.HandlerRegistration(handler_id="read", roles=("investigate",)),
            sdk.HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=tuple(sdk.CheckerPermission(checker_id=v) for v in permissions),
            ),
        ),
    )
    budget = sdk.Budget(limits=sdk.Resources(actions=10000, verifications=10000))
    construction = time.perf_counter() - begin
    begin = time.perf_counter()

    def requirement(i, *, verified=False):
        return sdk.DependencyRequirement(
            evidence_id=f"h{i}",
            obligation_id="helper",
            scope="helper",
            requirement="verified" if verified else "active",
        )

    def read(name, identifier, dependencies=()):
        return sdk.ActionCandidate(
            id=identifier,
            obligation_id=world[name].obligation_id,
            scope=world[name].scope,
            kind="investigate",
            handler_id="read",
            produces_evidence_id=name,
            dependencies=dependencies,
            resources=sdk.Resources(actions=1, verifications=0),
        )

    def check(name, identifier, checker="v1", dependencies=()):
        return sdk.ActionCandidate(
            id=identifier,
            obligation_id=world[name].obligation_id,
            scope=world[name].scope,
            kind="verify",
            handler_id="check",
            target_evidence_id=name,
            target_digest=world[name].digest,
            checker_id=checker,
            dependencies=dependencies,
            resources=sdk.Resources(actions=1, verifications=1),
        )

    root_indices = case.get(
        "root_indices", list(range(1, depth)) if case["topology"] == "branches" else [depth - 1]
    )
    root_dependencies = tuple(requirement(i, verified=checker_count > 1) for i in root_indices)
    if boundary == "wrong-scope":
        root_dependencies = tuple(_changed(d, scope="wrong") for d in root_dependencies)
    elif boundary == "wrong-digest":
        root_dependencies = tuple(_changed(d, digest="0" * 64) for d in root_dependencies)
    elif boundary == "contract-update":
        root_dependencies = tuple(
            _changed(d, contract_fingerprint=helper.contract_fingerprint) for d in root_dependencies
        )
    reads = tuple(
        read(
            f"h{i}",
            f"read-{i}-{j}",
            ()
            if boundary == "grounded-exit" and i == 0 and j == 0
            else tuple(requirement(k) for k in parents[i]),
        )
        for i in range(depth)
        for j in range(alternatives)
    )
    checks = (
        tuple(
            check(f"h{i}", f"check-{i}-{v}", v, (requirement(i),))
            for i in root_indices
            for v in identifiers
        )
        if checker_count > 1
        else ()
    )
    pool = (check("root", "consume-root", dependencies=root_dependencies), *reads, *checks)
    candidate_construction = time.perf_counter() - begin
    begin = time.perf_counter()
    # Initialization uses a disclosed generous capacity, identical in old/new.
    # It changes no checker authority and every callback remains a public receipt.
    initialization_policy = _changed(
        policy, max_pending_verifications=10000, available_handlers=None
    )
    state, _ = _transition(
        state,
        read("root", "initialize-root"),
        (),
        budget,
        initialization_policy,
        world,
        "initialize-root",
    )
    initial_count = (
        depth
        if boundary == "wrong-digest"
        else (
            depth // 2
            if boundary == "half-current"
            else 1
            if boundary == "invalidated-dependency"
            else 0
        )
    )
    # Generated DAGs need not have a ready prefix. These are explicit independent
    # initialization observations, not a claim that a continuation action ran.
    for i in range(initial_count):
        action = read(f"h{i}", f"initialize-{i}")
        state, _ = _transition(
            state, action, (), budget, initialization_policy, world, f"initialize-{i}"
        )
    if boundary == "satisfied-owner":
        for action in (
            read("anchor", "initialize-anchor"),
            check("anchor", "initialize-anchor-check"),
        ):
            state, _ = _transition(
                state, action, (), budget, initialization_policy, world, action.id
            )
    if boundary == "invalidated-dependency":
        state = sdk.invalidate(
            state,
            sdk.Invalidation(
                id="invalidate-h0",
                kind="evidence",
                target_id="h0",
                obligation_id="helper",
                scope="helper",
                reason="Host withdrawal",
            ),
        )
    if boundary == "contract-update":
        revised = _changed(helper, contract_revision="2", acceptance="revised integer")
        state = _changed(state, obligations=(task, revised))
    if case.get("available_handlers") is not None:
        policy = _changed(policy, available_handlers=tuple(case["available_handlers"]))
    if "remaining_actions" in case:
        spent = sum(r.actual_resources.actions for r in state.results)
        budget = sdk.Budget(
            limits=sdk.Resources(actions=spent + case["remaining_actions"], verifications=10000)
        )
    initialization = time.perf_counter() - begin
    return {
        "state": state,
        "pool": pool,
        "world": world,
        "budget": budget,
        "policy": policy,
        "construction_seconds": construction,
        "candidate_construction_seconds": candidate_construction,
        "initialization_seconds": initialization,
        "initial_callbacks": len(state.results),
        "initial_actual_resources": {
            name: sum(getattr(r.actual_resources, name) or 0 for r in state.results)
            for name in ("actions", "verifications")
        },
    }


def reference_helpers(fixture: dict) -> frozenset[str]:
    """Independent small scanning fixed point for these positive AND/OR recipes.

    Exact imported resolution, FAIL/UNKNOWN and supersession histories are outside
    this restricted generator and checked by separate installed audit regressions.
    No result is obtained from the SDK's feasibility/acceptance implementation.
    """
    state, pool, policy, budget = (fixture[k] for k in ("state", "pool", "policy", "budget"))
    owners = {o.id: o for o in state.obligations}
    evidence = {e.id: e for e in state.evidence}
    handlers = {h.handler_id: h for h in policy.handlers}
    invalid = {i.target_id for i in state.invalidations if i.kind == "evidence"}
    invalid_checks = {i.target_id for i in state.invalidations if i.kind == "check"}
    attempted = {a.action.id for a in state.attempts}
    if state.supersessions or state.contradictions or any(c.status != "PASS" for c in state.checks):
        raise ValueError("reference recipe includes unsupported negative/resolution history")

    def active(record):
        owner = owners.get(record.obligation_id)
        return (
            owner is not None
            and owner.scope == record.scope
            and not (record.withdrawn or record.expired or record.id in invalid)
        )

    def binding(binding):
        record, owner = evidence.get(binding.evidence_id), owners.get(binding.obligation_id)
        return (
            record is not None
            and owner is not None
            and (record.obligation_id, record.scope, record.digest, owner.contract_fingerprint)
            == (binding.obligation_id, binding.scope, binding.digest, binding.contract_fingerprint)
            and (binding.requirement == "exists" or active(record))
        )

    verified = set()
    while True:
        passes = {}
        for check_record in state.checks:
            basis = check_record.basis
            if basis is None or check_record.id in invalid_checks or basis.purpose != "content":
                continue
            if basis.checker_id not in policy.trusted_verifiers or not any(
                "verify" in h.roles
                and any(
                    p.checker_id == basis.checker_id
                    and p.revision == basis.checker_revision
                    and basis.purpose in p.purposes
                    for p in h.checkers
                )
                for h in policy.handlers
            ):
                continue
            if not binding(basis.target) or any(
                not binding(d) or d.requirement == "verified" and d.evidence_id not in verified
                for d in basis.dependencies
            ):
                continue
            if policy.prohibit_self_verification and (
                evidence[basis.target.evidence_id].producer == basis.checker_id
            ):
                continue
            passes.setdefault(basis.target.evidence_id, set()).add(basis.checker_id)
        grounded = {
            identifier
            for identifier, ids in passes.items()
            if (
                not owners[evidence[identifier].obligation_id].required_verifiers
                or set(owners[evidence[identifier].obligation_id].required_verifiers) <= ids
            )
        }
        if grounded <= verified:
            break
        verified.update(grounded)
    if all(
        not o.required or any(e.obligation_id == o.id and e.id in verified for e in state.evidence)
        for o in state.obligations
    ):
        return frozenset()

    def allowed(action):
        owner, handler = owners.get(action.obligation_id), handlers.get(action.handler_id)
        if (
            owner is None
            or owner.scope != action.scope
            or handler is None
            or (
                action.kind not in handler.roles
                or action.id in attempted
                or policy.available_handlers is not None
                and action.handler_id not in policy.available_handlers
                or policy.executable_handlers
                and action.handler_id not in policy.executable_handlers
            )
        ):
            return False
        if action.kind == "verify":
            if (
                action.checker_id not in policy.trusted_verifiers
                or action.purpose != "content"
                or not any(
                    p.checker_id == action.checker_id
                    and p.revision == action.checker_revision
                    and action.purpose in p.purposes
                    for p in handler.checkers
                )
            ):
                return False
            target = evidence.get(action.target_evidence_id)
            if target is not None and (
                not active(target)
                or (target.obligation_id, target.scope, target.digest)
                != (action.obligation_id, action.scope, action.target_digest)
                or policy.prohibit_self_verification
                and target.producer == action.checker_id
            ):
                return False
        for name in ("actions", "verifications", "tokens"):
            limit, cost = getattr(budget.limits, name), getattr(action.resources, name)
            spent = sum(getattr(r.actual_resources, name) or 0 for r in state.results)
            if limit is not None and (cost is None or cost > max(0, limit - spent)):
                return False
        return True

    def routes_for(dep, grounded):
        owner, record = owners.get(dep.obligation_id), evidence.get(dep.evidence_id)
        if (
            owner is None
            or owner.scope != dep.scope
            or (
                dep.contract_fingerprint is not None
                and dep.contract_fingerprint != owner.contract_fingerprint
            )
        ):
            return None
        result = set()
        if record is None:
            routes = [
                a
                for a in pool
                if a.kind != "verify"
                and a.produces_evidence_id == dep.evidence_id
                and (a.obligation_id, a.scope) == (dep.obligation_id, dep.scope)
                and a.id in grounded
            ]
            if not routes:
                return None
            result.update(a.id for a in routes)
        elif (record.obligation_id, record.scope) != (dep.obligation_id, dep.scope) or (
            dep.digest is not None
            and dep.digest != record.digest
            or dep.requirement != "exists"
            and not active(record)
        ):
            return None
        if dep.requirement != "verified" or dep.evidence_id in verified:
            return result
        existing_passes = passes.get(dep.evidence_id, set())
        for checker in owner.required_verifiers or (None,):
            if checker in existing_passes:
                continue
            routes = [
                a
                for a in pool
                if a.kind == "verify"
                and a.target_evidence_id == dep.evidence_id
                and (a.obligation_id, a.scope) == (dep.obligation_id, dep.scope)
                and (dep.digest is None or a.target_digest == dep.digest)
                and (record is None or a.target_digest == record.digest)
                and (checker is None or a.checker_id == checker)
                and a.id in grounded
            ]
            dynamic = record is None and any(
                "verify" in h.roles
                and (policy.available_handlers is None or h.handler_id in policy.available_handlers)
                and (not policy.executable_handlers or h.handler_id in policy.executable_handlers)
                and any(
                    p.checker_id in policy.trusted_verifiers
                    and "content" in p.purposes
                    and (checker is None or p.checker_id == checker)
                    for p in h.checkers
                )
                for h in policy.handlers
            )
            if not routes and not dynamic:
                return None
            if routes:
                result.update(a.id for a in routes)
        return result

    result = set()
    allowed_ids = {a.id for a in pool if allowed(a)}
    by_id = {a.id: a for a in pool}
    for root in pool:
        target = evidence.get(root.target_evidence_id)
        if (
            root.kind == "verify"
            and owners[root.obligation_id].required
            and target is not None
            and active(target)
            and target.id not in verified
            and root.id in allowed_ids
        ):
            grounded = set()
            while True:
                additions = {
                    a.id
                    for a in pool
                    if a.id != root.id
                    and a.id in allowed_ids
                    and all(routes_for(d, grounded) is not None for d in a.dependencies)
                }
                if additions <= grounded:
                    break
                grounded.update(additions)
            root_routes = [routes_for(d, grounded) for d in root.dependencies]
            if any(route is None for route in root_routes):
                continue
            pending = set().union(*root_routes)
            seen = set()
            while pending:
                identifier = pending.pop()
                if identifier in seen:
                    continue
                seen.add(identifier)
                for dep in by_id[identifier].dependencies:
                    pending.update(routes_for(dep, grounded) or ())
            result.update(seen)
    return frozenset(result)


def _sequence(fixture: dict, profile: bool = False) -> dict:
    import evidence_gap_router as sdk
    import evidence_gap_router.router as router
    import evidence_gap_router.runner as runner

    counts, timings, cpu = {}, {}, {}
    source_files = {
        router._helper_actions.__code__.co_filename,
        runner._binding_progress.__code__.co_filename,
    }
    wanted = {
        "action_path",
        "material_path",
        "authorized",
        "expand_action",
        "expand_material",
        "material_node",
        "node",
        "rule",
        "solve",
        "_consume_edge",
        "needed",
        "_helper_actions",
        "_needed_helper_actions",
        "_binding_progress",
        "_Evaluation.__init__",
    }

    def measured(phase, operation):
        current = {}

        def counter(frame, event, arg):
            if event == "call" and frame.f_code.co_filename in source_files:
                name = frame.f_code.co_name
                if name in wanted or frame.f_code.co_qualname == "_Evaluation.__init__":
                    label = frame.f_code.co_qualname
                    current[label] = current.get(label, 0) + 1

        wall_begin, cpu_begin = time.perf_counter(), time.process_time()
        if profile:
            sys.setprofile(counter)
        try:
            return operation()
        finally:
            if profile:
                sys.setprofile(None)
            timings[phase] = time.perf_counter() - wall_begin
            cpu[phase] = time.process_time() - cpu_begin
            if profile:
                counts[phase] = current

    state, pool, budget, policy = (fixture[k] for k in ("state", "pool", "budget", "policy"))
    decision = measured("plan", lambda: sdk.plan(state, pool, budget, policy))
    after, receipt = state, None
    if decision.action is not None:
        after, receipt = measured(
            "start_observe",
            lambda: _transition(
                state, decision.action, pool, budget, policy, fixture["world"], "measured-step"
            ),
        )
        progress = measured(
            "binding_progress",
            lambda: runner._binding_progress(state, after, pool, budget, policy, decision.action),
        )
    else:
        timings.update(start_observe=0.0, binding_progress=0.0)
        cpu.update(start_observe=0.0, binding_progress=0.0)
        progress = None
    return {
        "decision": decision,
        "after": after,
        "receipt": receipt,
        "progress": progress,
        "phase_wall_seconds": timings,
        "phase_cpu_seconds": cpu,
        "visits": counts,
    }


def worker(case: dict, mode: str) -> dict:
    """One bounded externally supervised worker; this function adds no timeout."""
    if mode not in ("time", "count", "memory", "semantic"):
        raise ValueError("unknown helper worker mode")
    total = time.perf_counter()
    import evidence_gap_router as sdk
    import evidence_gap_router.router as router

    imported = time.perf_counter() - total
    if mode == "memory":
        tracemalloc.start()
    fixture = build(case)
    snapshots_begin = time.perf_counter()
    raw = sdk.dump_json(fixture["state"])
    assert sdk.load_json(raw, sdk.State) == fixture["state"]
    snapshot_seconds = time.perf_counter() - snapshots_begin
    if mode == "time":
        _sequence(fixture)
        values = [_sequence(fixture) for _ in range(10)]
    else:
        values = [_sequence(fixture, profile=mode == "count")]
    peak = None
    if mode == "memory":
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    semantic_begin = time.perf_counter()
    actual_helpers = sorted(
        router._needed_helper_actions(
            fixture["state"], fixture["pool"], fixture["budget"], fixture["policy"]
        )
    )
    max_depth = manifest()["helper_scaling"]["small_reference_max_depth"]
    expected = sorted(reference_helpers(fixture)) if case["depth"] <= max_depth else None
    semantic_seconds = time.perf_counter() - semantic_begin
    result = values[-1]
    totals = [sum(v["phase_wall_seconds"].values()) for v in values]
    phases = tuple(result["phase_wall_seconds"])
    row = {
        "question": "C-helper",
        "case": case,
        "mode": mode,
        "environment": environment(),
        "status": "completed",
        "exception": None,
        "timeout": False,
        "cold_sdk_import_seconds": imported,
        **{
            k: fixture[k]
            for k in (
                "construction_seconds",
                "candidate_construction_seconds",
                "initialization_seconds",
                "initial_callbacks",
                "initial_actual_resources",
            )
        },
        "candidate_count": len(fixture["pool"]),
        "dependency_incidence": sum(len(a.dependencies) for a in fixture["pool"]),
        "snapshot_bytes": len(raw.encode()),
        "serialization_load_seconds": snapshot_seconds,
        "selected_action": None
        if result["decision"].action is None
        else result["decision"].action.id,
        "router_stop": result["decision"].stop_reason,
        "binding_progress": result["progress"],
        "callback_calls": int(result["receipt"] is not None),
        "reachable_helper_ids": actual_helpers,
        "reference_assessed": expected is not None,
        "reference_helper_ids": expected,
        "reference_agrees": None if expected is None else actual_helpers == expected,
        "reference_scope": (
            "Small positive finite recipes only; scanning public-field AND/OR fixed point, "
            "root blocked; no resolution/negative history"
        ),
        "semantic_observation_seconds": semantic_seconds,
        "phase_samples_seconds": {
            phase: [v["phase_wall_seconds"][phase] for v in values] for phase in phases
        },
        "phase_cpu_samples_seconds": {
            phase: [v["phase_cpu_seconds"][phase] for v in values] for phase in phases
        },
        "phase_median_seconds": {
            phase: statistics.median(v["phase_wall_seconds"][phase] for v in values)
            for phase in phases
        },
        "sequence_median_seconds": statistics.median(totals),
        "warmup": 1 if mode == "time" else 0,
        "repeats": len(values),
        "visits_by_phase": result["visits"],
        "visit_unit_limitation": (
            "Old recursive path entries and new rule/edge entries are method-specific "
            "diagnostics, not a universal speed ratio"
        ),
        "peak_traced_python_allocation_bytes": peak,
        "memory_scope": (
            "Construction, candidates, real initialization, snapshot roundtrip and one sequence; "
            "excludes cold SDK import and post-measurement semantic oracle; not RSS"
        ),
        "worker_end_to_end_seconds": time.perf_counter() - total,
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-json", required=True)
    parser.add_argument("--mode", choices=("time", "count", "memory", "semantic"), required=True)
    args = parser.parse_args()
    print(json.dumps(worker(json.loads(args.case_json), args.mode), sort_keys=True))


if __name__ == "__main__":
    main()
