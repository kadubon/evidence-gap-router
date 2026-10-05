"""Offline controller integrity and denominator/cost uncertainty regressions."""

import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.ollama import analysis, cli  # noqa: E402
from experiments.ollama.tasks import confirmation_tasks  # noqa: E402


def args(tmp_path):
    return SimpleNamespace(
        directory=tmp_path,
        url="http://127.0.0.1:11435",
        server_pid=12,
        server_log=None,
        freeze=tmp_path / "freeze.json",
    )


def item(arm="A", seed=None):
    task = confirmation_tasks()[0][0]
    seed = cli.PROTOCOL["seed"] if seed is None else seed
    model = cli.PROTOCOL["models"][0]
    return {
        "task_id": task.task_id,
        "model": model,
        "arm": arm,
        "seed": seed,
        "key": cli.key("confirmation", task.task_id, model, arm, seed),
    }


def terminal(tmp_path, entry, **trial):
    record = {
        **entry,
        "phase": "confirmation",
        "execution": "completed",
        "formal_freeze_sha256": "f",
        "trial": {
            "runner_stop": "satisfied",
            "fault": None,
            "pending": False,
            "system_claimed_complete": True,
            **trial,
        },
    }
    cli.write_json(tmp_path / "trials/confirmation" / (entry["key"] + ".json"), record)
    return record


def reservation(entry, request_id="r", phase="confirmation"):
    return {
        "event": "reserve",
        "request_id": request_id,
        "trial_id": entry["key"],
        "request": {"model": entry["model"]},
        "reserved_total_tokens": 4608,
        "metadata": {"phase": phase},
    }


def response(request_id="r", unknown=False, **extra):
    return {
        "event": "response",
        "request_id": request_id,
        "record": {
            "unknown_consumption": unknown,
            "status": "ok",
            "usage": {"generated_tokens": 4, "total_tokens": 10},
            "client_wall_seconds": 2,
            "durations_seconds": {
                "load_duration": 0,
                "eval_duration": 1,
                "prompt_eval_duration": None,
            },
            **extra,
        },
    }


@pytest.fixture
def scored(monkeypatch):
    def score(_task, _gold, trial):
        return {
            "oracle_assessed": True,
            "answer_correct": trial.get("success", True),
            "evidence_supported_completion": trial.get("success", True),
            "grounded_abstention": False,
            "errors": [],
        }

    monkeypatch.setattr(analysis, "evaluate", score)


def analyze(tmp_path, planned=None):
    protocol = {**cli.PROTOCOL, "bootstrap_replicates": 100}
    return analysis.analyze(
        tmp_path,
        tmp_path / "output",
        protocol,
        frozen=None if planned is None else {"planned_trial_keys": planned},
    )


def test_unknown_usage_and_missing_duration_are_not_actual_zero(tmp_path, scored):
    entry = item()
    terminal(tmp_path, entry, fault="unknown_consumption", pending=True, success=False)
    cli.append(tmp_path / "calls.jsonl", reservation(entry))
    cli.append(tmp_path / "calls.jsonl", response(unknown=True, client_wall_seconds=None))
    summary = analyze(tmp_path)
    cost = summary["all_attempt_costs"][entry["model"] + "/confirmation"]
    assert cost["total_tokens"] is cost["generated_tokens"] is cost["client_wall_seconds"] is None
    assert cost["observed_total_tokens"] == 0 and cost["unknown_usage_calls"] == 1
    assert cost["load_seconds"] == 0 and cost["prefill_seconds"] is None
    assert summary["comparisons"][entry["model"]]["paired_assessed_parents"] == 0


def test_missing_frozen_terminal_is_explicit_unexecuted_not_a_pair(tmp_path, scored):
    first, second, third = (item(arm) for arm in "ABC")
    terminal(tmp_path, first)
    summary = analyze(tmp_path, [first, second, third])
    assert summary["rows"] == 3 and summary["missing_terminal_keys"] == 2
    assert summary["outcomes"][first["model"]]["B"]["scheduled"] == 1
    assert summary["outcomes"][first["model"]]["B"]["oracle_assessed"] == 0
    assert summary["comparisons"][first["model"]]["paired_assessed_parents"] == 0


def test_known_faults_remain_assessed_and_pending_pairs_excluded(tmp_path, scored):
    first, second = item(), item("B")
    terminal(tmp_path, first, fault="schema_error", success=False)
    terminal(tmp_path, second)
    assert analyze(tmp_path)["comparisons"][first["model"]]["paired_assessed_parents"] == 1
    terminal(tmp_path, first, fault="pending_or_unknown_dispatch", pending=True, success=False)
    summary = analyze(tmp_path)
    assert summary["outcomes"][first["model"]]["A"]["oracle_assessed"] == 1
    assert summary["comparisons"][first["model"]]["paired_assessed_parents"] == 0


def test_pairs_require_the_same_predeclared_primary_seed(tmp_path, scored):
    first = item()
    terminal(tmp_path, first)
    terminal(tmp_path, item("B", cli.PROTOCOL["seed"] + 1))
    summary = analyze(tmp_path)
    assert summary["comparisons"][first["model"]]["paired_assessed_parents"] == 0


def test_main_success_costs_exclude_same_trial_auxiliary_calls(tmp_path, scored):
    first, second = item(), item("B")
    for entry, rid in ((first, "a"), (second, "b")):
        terminal(tmp_path, entry)
        cli.append(tmp_path / "calls.jsonl", reservation(entry, rid))
        cli.append(tmp_path / "calls.jsonl", response(rid))
    cli.append(tmp_path / "calls.jsonl", reservation(first, "aux", "auxiliary"))
    cli.append(
        tmp_path / "calls.jsonl",
        response("aux", usage={"generated_tokens": 99, "total_tokens": 100}),
    )
    summary = analyze(tmp_path)
    subset = summary["comparisons"][first["model"]]["both_successful_costs"]
    assert subset["A"]["total_tokens"] == 10 and subset["A"]["attempted_calls"] == 1
    assert summary["all_attempt_costs"][first["model"] + "/auxiliary"]["total_tokens"] == 100


def test_success_without_cost_records_is_not_free(tmp_path, scored):
    first, second = item(), item("B")
    terminal(tmp_path, first)
    terminal(tmp_path, second)
    subset = analyze(tmp_path)["comparisons"][first["model"]]["both_successful_costs"]["A"]
    assert subset["parents"] == 1 and subset["parents_with_cost_records"] == 0
    assert subset["total_tokens"] is subset["client_wall_seconds"] is None


def test_saved_trial_conflicting_identity_rejected_without_execution(tmp_path, monkeypatch):
    first = item()
    terminal(tmp_path, first)
    monkeypatch.setattr(cli, "run_trial", lambda *a, **k: pytest.fail("no replay"))
    assert cli.execute(args(tmp_path), None, "confirmation", first, "f")["key"] == first["key"]
    for field, value in (("task_id", "wrong"), ("model", "wrong"), ("seed", 0), ("arm", "B")):
        with pytest.raises(ValueError, match="identity"):
            cli.execute(args(tmp_path), None, "confirmation", {**first, field: value}, "f")


@pytest.mark.parametrize(
    "alive,status,pid",
    [(None, "okay", 12), (True, "unknown", 12), (True, "below_floor", 12), (True, "okay", None)],
)
def test_resource_uncertainty_blocks_before_dispatch(tmp_path, monkeypatch, alive, status, pid):
    monkeypatch.setattr(
        cli,
        "resource_gate",
        lambda *a, **k: {
            "resources": {"server_alive": alive, "memory_status": status},
            "safe_for_new_request": status == "okay",
            "blocking_reasons": ["memory_" + status],
            "raw_bytes": 0,
            "disk_free_bytes": 100,
        },
    )
    options = args(tmp_path)
    options.server_pid = pid
    with pytest.raises(cli.ClientBlocked):
        cli.guard(options)


@pytest.mark.parametrize("count", [24, 16, 8])
def test_reduced_predeclared_profiles_keep_all_families_and_quarter_unknown(count):
    selected = set(cli.selected_parent_ids(count))
    pairs = [(task, gold) for task, gold in confirmation_tasks() if task.task_id in selected]
    assert len(pairs) == count
    assert {
        family: sum(task.family == family for task, _ in pairs) for family in "L1 L2 L3 L4".split()
    } == {family: count // 4 for family in "L1 L2 L3 L4".split()}
    assert sum(gold.decision == "unknown" for _, gold in pairs) == count // 4
    assert all(
        any(task.family == family and int(task.task_id.rsplit("-", 1)[1]) == 1 for task, _ in pairs)
        for family in "L1 L2 L3 L4".split()
    )


def test_speed_forecast_charges_observed_cold_load_once_and_real_overhead():
    model = cli.PROTOCOL["models"][0]
    ledger = [
        response(
            "cold", model=model, client_wall_seconds=100, durations_seconds={"load_duration": 90}
        ),
        response(
            "warm", model=model, client_wall_seconds=12, durations_seconds={"load_duration": 1}
        ),
    ]
    resources = [
        {
            "request_id": rid,
            "model": model,
            "before_sampling_wall_seconds": 1,
            "sampling_wall_seconds": 2,
        }
        for rid in ("cold", "warm")
    ]
    forecast = cli.speed_forecast(ledger, resources, [model])[model]
    assert forecast["per_request_seconds"] == 14
    assert forecast["once_per_model_load_seconds"] == 90
    assert forecast["unknown_load_records"] == 0
    unknown = cli.speed_forecast(
        [response(model=model, client_wall_seconds=100, durations_seconds={})], resources, [model]
    )[model]
    assert unknown["per_request_seconds"] == 103
    assert unknown["once_per_model_load_seconds"] is None and unknown["unknown_load_records"] == 1


def test_auxiliary_uses_copied_checkpoint_and_original_budget_identity(tmp_path, monkeypatch):
    first = item()
    primary = terminal(tmp_path, first, runner_stop="no_progress")
    source = tmp_path / "checkpoints" / (first["key"] + ".json")
    source.parent.mkdir()
    source.write_bytes(b'{"original":true}')
    cli.append(tmp_path / "calls.jsonl", reservation(first))
    client = SimpleNamespace(
        profiles={first["model"]: SimpleNamespace(digest="a" * 64)},
        summary=lambda: {
            "blocked": False,
            "started_epoch": time.time(),
            "trials": {
                first["key"]: {"calls": 2, "total_tokens": 100, "started_epoch": time.time()}
            },
        },
    )
    monkeypatch.setattr(cli, "guard", lambda _a: {})
    observed = []

    def run(_task, **kwargs):
        observed.append(kwargs)
        kwargs["checkpoint"].write_bytes(b'{"continued":true}')
        return {"runner_stop": "step_completed", "fault": None}

    monkeypatch.setattr(cli, "run_trial", run)
    result = cli.auxiliary(args(tmp_path), client, primary, "f")
    assert result["execution"] == "completed" and len(observed) == 1
    assert observed[0]["resume"] and observed[0]["secondary_steps"] == 2
    assert observed[0]["client"].trial_key == first["key"]
    assert observed[0]["client"].phase == "auxiliary"
    assert source.read_bytes() == b'{"original":true}'
    assert cli.auxiliary(args(tmp_path), client, primary, "f") == result
    assert len(observed) == 1


def test_auxiliary_noneligible_has_no_fabricated_generation_cost(tmp_path, monkeypatch):
    first = item()
    primary = terminal(tmp_path, first, runner_stop="satisfied")
    (tmp_path / "calls.jsonl").write_text("", encoding="utf-8")
    client = SimpleNamespace(
        summary=lambda: {"blocked": False, "started_epoch": time.time(), "trials": {}}
    )
    monkeypatch.setattr(cli, "run_trial", lambda *a, **k: pytest.fail("no auxiliary call"))
    result = cli.auxiliary(args(tmp_path), client, primary, "f")
    assert result["execution"] == "not_eligible_for_auxiliary" and result["trial"] == {}


def test_installed_runtime_checks_actual_package_bytes_and_import_scope(tmp_path, monkeypatch):
    import evidence_gap_router as sdk
    from scripts import package_audit

    package = tmp_path / "site-packages/evidence_gap_router"
    package.mkdir(parents=True)
    module = package / "__init__.py"
    module.write_bytes(b"candidate bytes\n")
    wheel = tmp_path / "candidate.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("evidence_gap_router/__init__.py", module.read_bytes())
    monkeypatch.setattr(sdk, "__file__", str(module))
    monkeypatch.setattr(sdk, "__version__", cli.PROTOCOL["package_version"])
    monkeypatch.setattr(package_audit, "package_fingerprint", lambda _p: "fp")
    assert (
        cli.verify_installed_runtime(wheel)["sdk_import_scope"]
        == "outside-repository/site-packages"
    )
    module.write_bytes(b"different actual import")
    with pytest.raises(ValueError, match="bytes differ"):
        cli.verify_installed_runtime(wheel)
    monkeypatch.setattr(
        sdk, "__file__", str(cli.ROOT.parents[1] / "src/evidence_gap_router/__init__.py")
    )
    with pytest.raises(ValueError, match="outside"):
        cli.verify_installed_runtime(wheel)


def test_bound_client_preserves_known_receipt_after_backend_observation_failure(
    tmp_path, monkeypatch
):
    first = item()
    actual = {"request_id": "actual", "usage": {"total_tokens": 10}, "unknown_consumption": False}
    client = SimpleNamespace(
        profiles={first["model"]: SimpleNamespace(digest="a" * 64)}, chat=lambda **_kw: actual
    )
    monkeypatch.setattr(cli, "guard", lambda _a: {})
    monkeypatch.setattr(cli, "verify_inventory", lambda *a: {"verified": True})
    monkeypatch.setattr(
        cli, "observe_backend", lambda *a: (_ for _ in ()).throw(ValueError("private"))
    )
    monkeypatch.setattr(cli, "collect_resources", lambda **kw: {})
    returned = cli.BoundClient(client, args(tmp_path), "confirmation", first["key"]).chat(
        request_id="original", model=first["model"]
    )
    assert returned["usage"] == actual["usage"] and returned["unknown_consumption"] is False
    observation = json.loads((tmp_path / "resources.jsonl").read_text("utf-8"))
    assert observation["backend_after"] == {"observation_error": "ValueError"}
    assert "private" not in json.dumps(observation)


def test_bound_client_digest_violation_halts_future_calls_without_refunding_receipt(
    tmp_path, monkeypatch
):
    first = item()
    client = SimpleNamespace(
        profiles={first["model"]: SimpleNamespace(digest="a" * 64)},
        chat=lambda **kw: {"request_id": kw["request_id"], "usage": {"total_tokens": 10}},
        summary=lambda: {"blocked": False},
    )
    monkeypatch.setattr(cli, "guard", lambda _a: {})
    monkeypatch.setattr(cli, "verify_inventory", lambda *a: {})
    monkeypatch.setattr(
        cli,
        "observe_backend",
        lambda *a: {"loaded_models": [{"name": first["model"], "digest": "b" * 64}]},
    )
    monkeypatch.setattr(cli, "collect_resources", lambda **kw: {})
    bound = cli.BoundClient(client, args(tmp_path), "confirmation", first["key"])
    assert bound.chat(request_id="original", model=first["model"])["usage"]["total_tokens"] == 10
    assert bound.summary()["blocked"]


def test_live_expired_global_first_reservation_writes_all_unexecuted(tmp_path, monkeypatch):
    source = tmp_path / "harness"
    source.mkdir()
    (source / "protocol.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", source)
    planned = [item(arm) for arm in "ABC"]
    frozen = {
        "harness_sha256": hashlib.sha256().hexdigest(),
        "manifest_sha256": cli.sha(source / "protocol.json"),
        "planned_trial_keys": planned,
        "planned_auxiliary_source_keys": [],
    }
    cli.write_json(tmp_path / "freeze.json", frozen)
    client = SimpleNamespace(
        summary=lambda: {
            "blocked": False,
            "started_epoch": time.time() - 14401,
            "calls": 0,
            "generated_tokens": 0,
            "total_tokens": 0,
        }
    )
    monkeypatch.setattr(cli, "guard", lambda _a: {})
    monkeypatch.setattr(cli, "execute", lambda *a: pytest.fail("expired budget cannot dispatch"))
    cli.live(args(tmp_path), client)
    records = [
        json.loads(path.read_text("utf-8"))
        for path in (tmp_path / "trials/confirmation").glob("*.json")
    ]
    assert len(records) == 3 and all(r["execution"] == "unexecuted_due_to_budget" for r in records)


def test_resumed_trial_labels_only_current_segment_without_inventing_total_wall(
    tmp_path, monkeypatch
):
    first = item()
    checkpoint = tmp_path / "checkpoints" / (first["key"] + ".json")
    checkpoint.parent.mkdir()
    checkpoint.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli, "run_trial", lambda *a, **k: {"calls": [], "runner_stop": "no_progress", "fault": None}
    )
    client = SimpleNamespace(profiles={first["model"]: SimpleNamespace(digest="a" * 64)})
    saved = cli.execute(args(tmp_path), client, "confirmation", first, "f")
    assert saved["resumed_checkpoint"] and saved["trial_wall_seconds"] is None
    assert saved["current_controller_segment_wall_seconds"] >= 0


def test_auxiliary_does_not_reset_original_trial_deadline(tmp_path, monkeypatch):
    first = item()
    primary = terminal(tmp_path, first, runner_stop="no_progress")
    (tmp_path / "calls.jsonl").write_text("", encoding="utf-8")
    client = SimpleNamespace(
        summary=lambda: {
            "blocked": False,
            "started_epoch": time.time(),
            "trials": {
                first["key"]: {"calls": 1, "total_tokens": 1, "started_epoch": time.time() - 601}
            },
        }
    )
    monkeypatch.setattr(cli, "run_trial", lambda *a, **k: pytest.fail("no deadline reset"))
    saved = cli.auxiliary(args(tmp_path), client, primary, "f")
    assert saved["stop_detail"] == "original_trial_budget_exhausted" and saved["trial"] == {}


def test_missing_predeclared_auxiliary_record_keeps_its_unexecuted_denominator(tmp_path, scored):
    first = item()
    terminal(tmp_path, first)
    summary = analysis.analyze(
        tmp_path,
        tmp_path / "output",
        {**cli.PROTOCOL, "bootstrap_replicates": 100},
        frozen={"planned_trial_keys": [first], "planned_auxiliary_source_keys": [first["key"]]},
    )
    assert summary["rows"] == 2 and summary["planned_auxiliary_keys"] == 1
    rows = json.loads((tmp_path / "output/scored-trials.json").read_text("utf-8"))
    aux = next(row for row in rows if row["phase"] == "auxiliary")
    assert aux["execution"] == "unexecuted_no_terminal_record" and not aux["oracle_assessed"]
