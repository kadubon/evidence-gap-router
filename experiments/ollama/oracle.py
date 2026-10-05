"""Post-trial scoring from separate artificial truth keys, never model verdict alone."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .tasks import GoldTask, PublicTask


def _contract(owner: dict[str, Any]) -> str:
    value = {
        key: owner[key]
        for key in (
            "id",
            "scope",
            "contract_revision",
            "acceptance",
            "min_evidence",
            "min_provenance_groups",
        )
    }
    value["required_verifiers"] = sorted(set(owner["required_verifiers"]))
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _current_binding(
    binding: dict[str, Any],
    evidence: dict[str, Any],
    owners: dict[str, Any],
    inactive: set[str],
) -> bool:
    identity = binding.get("evidence_id")
    if not isinstance(identity, str):
        return False
    item = evidence.get(identity)
    if item is None or item["id"] in inactive or item.get("withdrawn") or item.get("expired"):
        return False
    owner = owners.get(item["obligation_id"])
    return (
        owner is not None
        and all(
            binding.get(key) == item[key]
            for key in (
                "digest",
                "obligation_id",
                "scope",
            )
        )
        and binding.get("contract_fingerprint") == _contract(owner)
    )


def _issued_check(check: dict[str, Any], receipts: list[Any], attempts: dict[str, Any]) -> bool:
    for receipt in receipts:
        if check not in receipt.get("checks", []) or receipt.get("status") != "completed":
            continue
        attempt = attempts.get(receipt.get("attempt_id"))
        if (
            attempt is None
            or attempt.get("legacy")
            or attempt.get("basis") != check.get("basis")
            or attempt.get("action", {}).get("kind") != "verify"
            or (receipt.get("actual_resources", {}).get("verifications") or 0) < 1
        ):
            continue
        basis = check["basis"]
        registration = attempt.get("registration") or {}
        if "verify" in registration.get("roles", []) and any(
            permission.get("checker_id") == basis["checker_id"]
            and permission.get("revision") == basis["checker_revision"]
            and basis["purpose"] in permission.get("purposes", [])
            for permission in registration.get("checkers", [])
        ):
            return True
    return False


def evaluate(task: PublicTask, gold: GoldTask, trial: dict[str, Any]) -> dict[str, Any]:
    """Assess canonical decision and exact grounded witness completion separately.

    This does not call router acceptance, share gold with prompts, or interpret
    literal quotation as semantic entailment. Gold states the artificial rule's
    required witness text; the live model supplies the answer and citations.
    """
    if task.task_id != gold.task_id or trial.get("task_id") != task.task_id:
        raise ValueError("oracle task identity mismatch")
    answer = trial.get("answer")
    if not isinstance(answer, dict):
        return {
            "oracle_assessed": True,
            "answer_correct": False,
            "evidence_supported_completion": False,
            "grounded_abstention": False,
            "errors": ["no_structured_answer"],
        }
    correct = answer.get("decision") == gold.decision
    errors: list[str] = []
    if not correct:
        errors.append("wrong_canonical_decision")
    documents = {doc.source_id: doc for doc in task.documents}
    citations = answer.get("citations", [])
    quoted: dict[str, list[str]] = {}
    for citation in citations:
        if not isinstance(citation, dict):
            errors.append("invalid_citation")
            continue
        source, quote = citation.get("source_id"), citation.get("quote")
        if not isinstance(source, str):
            errors.append("invalid_citation_source")
            continue
        document = documents.get(source)
        if (
            document is None
            or not isinstance(quote, str)
            or not quote
            or quote not in document.text
        ):
            errors.append("fabricated_or_foreign_quote")
            continue
        if citation.get("version") != document.version:
            errors.append("wrong_source_version")
        quoted.setdefault(source, []).append(quote)
    for witness in gold.witnesses:
        # Full short witness records are preregistered. Splitting one record
        # across multiple exact citations is allowed; irrelevant true quotes do
        # not substitute for an omitted condition or exception.
        joined = "".join(quoted.get(witness.source_id, []))
        clauses = tuple(clause for clause in witness.quote.split("。") if clause)
        if not all(clause in joined for clause in clauses):
            errors.append(f"missing_witness:{witness.source_id}")
    origins = {documents[source].origin for source in quoted}
    if len(origins) < gold.minimum_origins:
        errors.append("insufficient_independent_origins")
    state = trial.get("state", {})
    evidence = {item["id"]: item for item in state.get("evidence", [])}
    owners = {item["id"]: item for item in state.get("obligations", [])}
    attempts = {item["id"]: item for item in state.get("attempts", [])}
    inactive = {
        event["target_id"]
        for event in state.get("invalidations", [])
        if event["kind"] == "evidence"
    }
    inactive.update(
        event["target_id"]
        for event in state.get("supersessions", [])
        if event["kind"] == "evidence"
    )
    inactive_checks = {
        event["target_id"] for event in state.get("invalidations", []) if event["kind"] == "check"
    }
    inactive_checks.update(
        event["target_id"] for event in state.get("supersessions", []) if event["kind"] == "check"
    )
    target = evidence.get(trial.get("answer_evidence_id"))
    if target is None:
        errors.append("missing_answer_receipt")
    else:
        content = target.get("content")
        if not isinstance(content, str):
            errors.append("answer_digest_mismatch")
        else:
            payload = json.loads(content)
            canonical = json.dumps(
                payload.get("output"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            if hashlib.sha256(canonical.encode()).hexdigest() != target["digest"]:
                errors.append("answer_digest_mismatch")
            if target["id"] in inactive or target.get("withdrawn") or target.get("expired"):
                errors.append("inactive_answer")
            if payload.get("output") != answer:
                errors.append("answer_not_actual_model_output")
            input_ids = set(payload.get("related_inputs", []))
            used_sources = set(payload.get("retrieved_sources", []))
            for source in quoted:
                document = documents[source]
                raw = evidence.get(f"raw:{source}")
                if (
                    source not in used_sources
                    or f"raw:{source}" not in input_ids
                    or raw is None
                    or raw.get("digest") != document.digest
                    or raw.get("content") != document.text
                    or raw.get("source") != source
                    or raw.get("provenance_group") != document.origin
                    or raw.get("scope") != task.task_id
                    or raw.get("obligation_id") != "raw"
                ):
                    errors.append(f"unbound_source:{source}")
            receipts = state.get("results", [])
            answer_receipts = [
                receipt
                for receipt in receipts
                if any(
                    item.get("id") == target["id"] and item == target
                    for item in receipt.get("evidence", [])
                )
            ]
            calls = {record.get("request_id"): record for record in trial.get("calls", [])}
            call = calls.get(payload.get("request_id"))
            if (
                len(answer_receipts) != 1
                or answer_receipts[0].get("status") != "completed"
                or call is None
                or call.get("status") != "ok"
                or call.get("parsed") != answer
                or call.get("model_digest") != trial.get("model_digest")
            ):
                errors.append("answer_not_completed_live_receipt")
            if answer_receipts:
                issued = attempts.get(answer_receipts[0]["attempt_id"])
                replaced = {
                    event["target_id"]
                    for event in answer_receipts[0].get("supersessions", [])
                    if event["kind"] == "evidence" and event["replacement_id"] == target["id"]
                }
                if (
                    issued is None
                    or set(payload.get("related_inputs", []))
                    != {binding["evidence_id"] for binding in issued["inputs"]}
                    or not all(
                        _current_binding(binding, evidence, owners, inactive - replaced)
                        for binding in issued["inputs"]
                    )
                ):
                    errors.append("answer_inputs_not_current_issued_inputs")
            passed = []
            for check in state.get("checks", []):
                basis = check.get("basis")
                if (
                    not isinstance(basis, dict)
                    or basis.get("target", {}).get("evidence_id") != target["id"]
                ):
                    continue
                if check.get("status") != "PASS":
                    continue
                if check["id"] in inactive_checks:
                    continue
                owner = next((o for o in state.get("obligations", []) if o["id"] == "answer"), None)
                target_binding = basis["target"]
                expected_checker = f"semantic:{trial.get('model_digest')}"
                if (
                    check.get("legacy")
                    or basis.get("purpose") != "content"
                    or basis.get("checker_id") != expected_checker
                    or check.get("verifier_id") != expected_checker
                    or basis.get("checker_revision") != "1"
                    or owner is None
                    or basis.get("obligation_id") != "answer"
                    or basis.get("scope") != task.task_id
                    or target_binding.get("digest") != target["digest"]
                    or target_binding.get("obligation_id") != "answer"
                    or target_binding.get("scope") != task.task_id
                    or basis.get("contract_fingerprint") != _contract(owner)
                    or not _current_binding(target_binding, evidence, owners, inactive)
                ):
                    continue
                dependencies = {
                    binding["evidence_id"]: binding for binding in basis.get("dependencies", [])
                }
                related = set(dependencies)
                expected = {f"raw:{source}" for source in used_sources}
                if trial.get("arm") != "C":
                    expected.update(f"extracted:{source}" for source in used_sources)
                reviews = [
                    e
                    for e in evidence.values()
                    if e.get("obligation_id") == "review" and e["id"] in related
                ]
                if not expected.issubset(related) or len(reviews) != 1:
                    continue
                review = reviews[0]
                review_payload = json.loads(review["content"])
                review_call = calls.get(review_payload.get("request_id"))
                review_canonical = json.dumps(
                    review_payload.get("output"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if (
                    review_payload.get("reviewed_answer_id") != target["id"]
                    or review_payload.get("output", {}).get("status") != "PASS"
                    or review_call is None
                    or review_call.get("status") != "ok"
                    or review_call.get("parsed") != review_payload["output"]
                    or hashlib.sha256(review_canonical.encode()).hexdigest() != review["digest"]
                ):
                    continue
                if not all(
                    _current_binding(binding, evidence, owners, inactive)
                    for binding in dependencies.values()
                ):
                    continue
                # Require this check to occur in an actual matching issued receipt.
                if not _issued_check(check, receipts, attempts):
                    continue
                if trial.get("arm") != "C":
                    literal_proofs = True
                    for source in used_sources:
                        extracted = evidence[f"extracted:{source}"]
                        valid_literal = any(
                            literal.get("status") == "PASS"
                            and literal["id"] not in inactive_checks
                            and literal.get("verifier_id") == "host:literal-citation"
                            and literal.get("basis", {}).get("target", {}).get("evidence_id")
                            == extracted["id"]
                            and _current_binding(
                                literal["basis"]["target"], evidence, owners, inactive
                            )
                            and all(
                                _current_binding(dep, evidence, owners, inactive)
                                for dep in literal["basis"]["dependencies"]
                            )
                            and {f"raw:{source}"}.issubset(
                                {dep["evidence_id"] for dep in literal["basis"]["dependencies"]}
                            )
                            and _issued_check(literal, receipts, attempts)
                            for literal in state.get("checks", [])
                            if literal.get("basis")
                        )
                        literal_proofs = literal_proofs and valid_literal
                    if not literal_proofs:
                        continue
                passed.append(check)
            if not passed:
                errors.append("no_grounded_semantic_review_receipt")
            for check in state.get("checks", []):
                basis = check.get("basis")
                if (
                    check.get("status") in ("FAIL", "UNKNOWN")
                    and check["id"] not in inactive_checks
                    and basis
                    and basis["target"]["evidence_id"] == target["id"]
                    and _current_binding(basis["target"], evidence, owners, inactive)
                    and all(
                        _current_binding(dep, evidence, owners, inactive)
                        for dep in basis["dependencies"]
                    )
                    and _issued_check(check, receipts, attempts)
                ):
                    errors.append("current_negative_check")
            resolved = {
                event["target_id"]
                for event in state.get("supersessions", [])
                if event["kind"] == "contradiction"
            }
            if any(
                c.get("blocking") and c["obligation_id"] == "answer" and c["id"] not in resolved
                for c in state.get("contradictions", [])
            ):
                errors.append("unresolved_contradiction")
    if trial.get("pending") or trial.get("fault") in (
        "unknown_consumption",
        "pending_or_unknown_dispatch",
        "callback_exception",
    ):
        errors.append("uncertain_execution")
    supported = not errors
    return {
        "oracle_assessed": True,
        "answer_correct": correct,
        "evidence_supported_completion": supported,
        "grounded_abstention": supported and gold.decision == "unknown",
        "errors": sorted(set(errors)),
    }
