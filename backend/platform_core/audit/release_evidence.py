"""Technical execution evidence recorded through the existing platform audit log.

This is caller-reported engineering evidence only. It does not validate test or build
results, certify a market, or represent any legal, provider, or production approval.
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


RESULT_STATUSES = frozenset({
    "PASSED",
    "FAILED",
    "NOT_RUN",
    "BLOCKED",
    "NOT_APPLICABLE",
})
ARTIFACT_UPLOAD_STATUSES = frozenset({"NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "UNKNOWN"})
_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")


class ReleaseEvidenceValidationError(ValueError):
    """Raised when a technical execution evidence record is incomplete or invalid."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseEvidenceValidationError(f"{field} is required.")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise ReleaseEvidenceValidationError(f"{field} contains unsupported control characters.")
    return value.strip()


def _optional_text(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    return _required_text(value, field)


def _nullable_text(value: Optional[str], field: str) -> Optional[str]:
    """Normalize absent GitHub-provided values to null rather than inventing defaults."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _optional_text(value, field)


def _optional_positive_int(value: Optional[Any], field: str) -> Optional[int]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ReleaseEvidenceValidationError(f"{field} must be a positive integer when provided.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseEvidenceValidationError(f"{field} must be a positive integer when provided.") from exc
    if number < 1 or str(value).strip() != str(number):
        raise ReleaseEvidenceValidationError(f"{field} must be a positive integer when provided.")
    return number


def _workflow_file_path(workflow_ref: Optional[str], repository: Optional[str]) -> Optional[str]:
    ref = _nullable_text(workflow_ref, "workflow_ref")
    repo = _nullable_text(repository, "repository")
    if not ref or not repo or "@" not in ref:
        return None
    path_and_repo = ref.rsplit("@", 1)[0]
    prefix = f"{repo}/"
    if not path_and_repo.startswith(prefix):
        return None
    path = path_and_repo[len(prefix):]
    return path or None


def _result(status: str, command: Optional[str], summary: Optional[str], name: str) -> Dict[str, Any]:
    normalized_status = _required_text(status, f"{name}_status").upper()
    if normalized_status not in RESULT_STATUSES:
        allowed = ", ".join(sorted(RESULT_STATUSES))
        raise ReleaseEvidenceValidationError(f"{name}_status must be one of: {allowed}.")

    normalized_command = _optional_text(command, f"{name}_command")
    if normalized_status in {"PASSED", "FAILED"} and not normalized_command:
        raise ReleaseEvidenceValidationError(
            f"{name}_command is required when {name}_status is {normalized_status}."
        )

    return {
        "status": normalized_status,
        "command": normalized_command,
        "summary": _optional_text(summary, f"{name}_summary"),
    }


def _limitations(values: Optional[Iterable[str]]) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    try:
        result = [_required_text(value, "limitation") for value in values]
    except TypeError as exc:
        raise ReleaseEvidenceValidationError("limitations must be a list of text values.") from exc
    return result


def build_release_evidence(
    *,
    requirement_ref: str,
    repository: str,
    environment: str,
    test_status: str,
    build_status: str,
    commit_sha: Optional[str] = None,
    test_command: Optional[str] = None,
    test_summary: Optional[str] = None,
    build_command: Optional[str] = None,
    build_summary: Optional[str] = None,
    artifact_location: Optional[str] = None,
    limitations: Optional[Iterable[str]] = None,
    result_source: str = "CALLER_REPORTED",
    repository_id: Optional[Any] = None,
    run_id: Optional[Any] = None,
    run_number: Optional[Any] = None,
    run_attempt: Optional[Any] = None,
    workflow_name: Optional[str] = None,
    workflow_ref: Optional[str] = None,
    workflow_file_sha: Optional[str] = None,
    artifact_name: Optional[str] = None,
    artifact_upload_status: str = "NOT_ATTEMPTED",
    artifact_id: Optional[str] = None,
    artifact_digest: Optional[str] = None,
    artifact_url: Optional[str] = None,
    artifact_retention_days: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a validated, JSON-safe technical execution record with a UTC timestamp."""
    normalized_sha = _nullable_text(commit_sha, "commit_sha")
    if normalized_sha and not _COMMIT_SHA_PATTERN.fullmatch(normalized_sha):
        raise ReleaseEvidenceValidationError("commit_sha must be a 7-64 character hexadecimal SHA.")

    artifact = _optional_text(artifact_location, "artifact_location")
    normalized_result_source = _required_text(result_source, "result_source").upper()
    if normalized_result_source not in {"CALLER_REPORTED", "CI_EXECUTION_OUTCOME"}:
        raise ReleaseEvidenceValidationError("result_source must be CALLER_REPORTED or CI_EXECUTION_OUTCOME.")
    captured_at = datetime.now(datetime_timezone.utc)

    normalized_run_id = _optional_positive_int(run_id, "run_id")
    normalized_run_number = _optional_positive_int(run_number, "run_number")
    normalized_run_attempt = _optional_positive_int(run_attempt, "run_attempt")
    normalized_repository_id = _optional_positive_int(repository_id, "repository_id")
    normalized_workflow_sha = _nullable_text(workflow_file_sha, "workflow_file_sha")
    if normalized_workflow_sha and not _COMMIT_SHA_PATTERN.fullmatch(normalized_workflow_sha):
        raise ReleaseEvidenceValidationError("workflow_file_sha must be a 7-64 character hexadecimal SHA.")

    normalized_artifact_status = _required_text(artifact_upload_status, "artifact_upload_status").upper()
    if normalized_artifact_status not in ARTIFACT_UPLOAD_STATUSES:
        allowed = ", ".join(sorted(ARTIFACT_UPLOAD_STATUSES))
        raise ReleaseEvidenceValidationError(f"artifact_upload_status must be one of: {allowed}.")
    normalized_artifact_id = _nullable_text(artifact_id, "artifact_id")
    normalized_artifact_digest = _nullable_text(artifact_digest, "artifact_digest")
    normalized_artifact_url = _nullable_text(artifact_url, "artifact_url")
    retention_days = _optional_positive_int(artifact_retention_days, "artifact_retention_days")

    limitations_list = _limitations(limitations)
    if normalized_result_source == "CI_EXECUTION_OUTCOME":
        for value, label in (
            (normalized_run_id, "GitHub Actions run ID"),
            (normalized_run_number, "GitHub Actions run number"),
            (normalized_run_attempt, "GitHub Actions run attempt"),
            (_nullable_text(workflow_name, "workflow_name"), "workflow name"),
            (_workflow_file_path(workflow_ref, repository), "workflow file path"),
            (normalized_workflow_sha, "workflow-file SHA"),
        ):
            if value is None:
                limitations_list.append(f"{label} was unavailable from the GitHub Actions environment.")

    if normalized_artifact_status == "FAILED":
        limitations_list.append("Evidence payload artifact upload failed; no successful publication is claimed.")
    elif normalized_artifact_status == "SUCCEEDED":
        missing_artifact_metadata = [
            label for value, label in (
                (normalized_artifact_id, "artifact ID"),
                (normalized_artifact_digest, "artifact digest"),
                (normalized_artifact_url, "artifact URL"),
            ) if value is None
        ]
        if missing_artifact_metadata:
            limitations_list.append(
                "Artifact upload succeeded but GitHub did not expose "
                + ", ".join(missing_artifact_metadata)
                + "."
            )

    workflow_name_clean = _nullable_text(workflow_name, "workflow_name")
    workflow_ref_clean = _nullable_text(workflow_ref, "workflow_ref")
    workflow_path = _workflow_file_path(workflow_ref_clean, repository)
    artifact_name_clean = _nullable_text(artifact_name, "artifact_name")
    metadata_values = [normalized_artifact_id, normalized_artifact_digest, normalized_artifact_url]
    if all(metadata_values):
        artifact_metadata_status = "COMPLETE"
    elif any(metadata_values):
        artifact_metadata_status = "PARTIAL"
    else:
        artifact_metadata_status = "UNAVAILABLE"

    return {
        "evidence_id": str(uuid.uuid4()),
        "evidence_type": "TECHNICAL_EXECUTION",
        "evidence_scope": "TECHNICAL_EXECUTION_ONLY",
        "requirement_ref": _required_text(requirement_ref, "requirement_ref"),
        "repository": _required_text(repository, "repository"),
        "repository_id": normalized_repository_id,
        "commit_sha": normalized_sha,
        "github_actions": {
            "run_id": normalized_run_id,
            "run_number": normalized_run_number,
            "run_attempt": normalized_run_attempt,
            "workflow": {
                "name": workflow_name_clean,
                "ref": workflow_ref_clean,
                "file_path": workflow_path,
                "file_sha": normalized_workflow_sha,
            },
        },
        "environment": _required_text(environment, "environment"),
        "test": _result(test_status, test_command, test_summary, "test"),
        "build": _result(build_status, build_command, build_summary, "build"),
        "artifact_location": normalized_artifact_url if normalized_artifact_status == "SUCCEEDED" and normalized_artifact_url else artifact,
        "artifact_publication": {
            "status": normalized_artifact_status,
            "metadata_status": artifact_metadata_status,
            "name": artifact_name_clean,
            "id": normalized_artifact_id,
            "digest": normalized_artifact_digest,
            "digest_algorithm": "SHA-256" if normalized_artifact_digest else None,
            "url": normalized_artifact_url,
            "retention_days": retention_days,
            "retention_source": "upload-artifact action input" if retention_days is not None else None,
        },
        "execution_timestamp_utc": captured_at.isoformat().replace("+00:00", "Z"),
        "limitations": limitations_list,
        "result_source": normalized_result_source,
        "results_are_caller_reported": normalized_result_source == "CALLER_REPORTED",
    }


def persist_release_evidence(evidence: Dict[str, Any]):
    """Append the evidence payload to the existing platform audit log."""
    from platform_core.audit.writer import record_audit_entry

    return record_audit_entry(
        event_type="engineering.release_evidence.recorded",
        action="engineering:release_evidence.record",
        resource_type="EngineeringExecutionEvidence",
        resource_id=evidence["evidence_id"],
        actor_kind="SYSTEM",
        metadata=evidence,
    )


def record_release_evidence(**metadata: Any) -> Dict[str, Any]:
    """Validate and append a technical execution record, returning its JSON payload."""
    evidence = build_release_evidence(**metadata)
    persist_release_evidence(evidence)
    return evidence


def status_from_execution(
    exit_code: Optional[int],
    *,
    attempted: bool,
    blocked: bool = False,
    failed: bool = False,
) -> str:
    """Derive a check status from its captured process exit code and execution state."""
    if exit_code is not None:
        return "PASSED" if exit_code == 0 else "FAILED"
    if failed:
        return "FAILED"
    if blocked or attempted:
        return "BLOCKED"
    return "NOT_RUN"


def build_release_evidence_from_execution(
    *,
    requirement_ref: str,
    repository: str,
    environment: str,
    test_command: Optional[str],
    test_exit_code: Optional[int],
    build_command: Optional[str],
    build_exit_code: Optional[int],
    commit_sha: Optional[str] = None,
    test_attempted: bool = False,
    test_blocked: bool = False,
    test_failed: bool = False,
    build_attempted: bool = False,
    build_blocked: bool = False,
    build_failed: bool = False,
    artifact_location: Optional[str] = None,
    limitations: Optional[Iterable[str]] = None,
    run_id: Optional[Any] = None,
    repository_id: Optional[Any] = None,
    run_number: Optional[Any] = None,
    run_attempt: Optional[Any] = None,
    workflow_name: Optional[str] = None,
    workflow_ref: Optional[str] = None,
    workflow_file_sha: Optional[str] = None,
    artifact_name: Optional[str] = None,
    artifact_upload_status: str = "NOT_ATTEMPTED",
    artifact_id: Optional[str] = None,
    artifact_digest: Optional[str] = None,
    artifact_url: Optional[str] = None,
    artifact_retention_days: Optional[Any] = None,
) -> Dict[str, Any]:
    """Create evidence from actual captured process exit codes, without database access."""
    test_status = status_from_execution(
        test_exit_code, attempted=test_attempted, blocked=test_blocked, failed=test_failed,
    )
    build_status = status_from_execution(
        build_exit_code, attempted=build_attempted, blocked=build_blocked, failed=build_failed,
    )

    test_summary = (
        f"Process exited with code {test_exit_code}." if test_exit_code is not None
        else "Execution step failed without a captured process exit code." if test_status == "FAILED"
        else "Check was blocked before execution." if test_status == "BLOCKED"
        else "Check was not run."
    )
    build_summary = (
        f"Process exited with code {build_exit_code}." if build_exit_code is not None
        else "Execution step failed without a captured process exit code." if build_status == "FAILED"
        else "Check was blocked before execution." if build_status == "BLOCKED"
        else "Check was not run."
    )

    return build_release_evidence(
        requirement_ref=requirement_ref,
        repository=repository,
        commit_sha=commit_sha,
        environment=environment,
        test_status=test_status,
        test_command=test_command,
        test_summary=test_summary,
        build_status=build_status,
        build_command=build_command,
        build_summary=build_summary,
        artifact_location=artifact_location,
        limitations=limitations,
        result_source="CI_EXECUTION_OUTCOME",
        repository_id=repository_id,
        run_id=run_id,
        run_number=run_number,
        run_attempt=run_attempt,
        workflow_name=workflow_name,
        workflow_ref=workflow_ref,
        workflow_file_sha=workflow_file_sha,
        artifact_name=artifact_name,
        artifact_upload_status=artifact_upload_status,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
        artifact_url=artifact_url,
        artifact_retention_days=artifact_retention_days,
    )


def _write_json_report(evidence: Dict[str, Any], output: str) -> None:
    serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    with Path(output).open("x", encoding="utf-8") as report:
        report.write(serialized)


def main(argv: Optional[list[str]] = None) -> int:
    """Standalone JSON-only collector used by CI; deliberately does not import Django."""
    actual_argv = sys.argv[1:] if argv is None else argv
    if actual_argv and actual_argv[0] == "finalize":
        return finalize_main(actual_argv[1:])

    parser = argparse.ArgumentParser(description="Collect technical CI execution evidence as JSON.")
    parser.add_argument("--requirement-ref", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id")
    parser.add_argument("--commit-sha")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--run-number")
    parser.add_argument("--run-attempt")
    parser.add_argument("--workflow-name")
    parser.add_argument("--workflow-ref")
    parser.add_argument("--workflow-file-sha")
    parser.add_argument("--test-command")
    parser.add_argument("--test-exit-code", type=int)
    parser.add_argument("--test-attempted", action="store_true")
    parser.add_argument("--test-blocked", action="store_true")
    parser.add_argument("--test-failed", action="store_true")
    parser.add_argument("--build-command")
    parser.add_argument("--build-exit-code", type=int)
    parser.add_argument("--build-attempted", action="store_true")
    parser.add_argument("--build-blocked", action="store_true")
    parser.add_argument("--build-failed", action="store_true")
    parser.add_argument("--artifact-location")
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-upload-status", choices=sorted(ARTIFACT_UPLOAD_STATUSES), default="NOT_ATTEMPTED")
    parser.add_argument("--artifact-id")
    parser.add_argument("--artifact-digest")
    parser.add_argument("--artifact-url")
    parser.add_argument("--artifact-retention-days", type=int)
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--fail-on-unsuccessful",
        action="store_true",
        help="Exit non-zero after writing the report unless both checks passed.",
    )
    options = parser.parse_args(argv)

    try:
        evidence = build_release_evidence_from_execution(
            requirement_ref=options.requirement_ref,
            repository=options.repository,
            repository_id=options.repository_id,
            commit_sha=options.commit_sha,
            environment=options.environment,
            test_command=options.test_command,
            test_exit_code=options.test_exit_code,
            test_attempted=options.test_attempted,
            test_blocked=options.test_blocked,
            test_failed=options.test_failed,
            build_command=options.build_command,
            build_exit_code=options.build_exit_code,
            build_attempted=options.build_attempted,
            build_blocked=options.build_blocked,
            build_failed=options.build_failed,
            artifact_location=options.artifact_location,
            limitations=options.limitation,
            run_id=options.run_id,
            run_number=options.run_number,
            run_attempt=options.run_attempt,
            workflow_name=options.workflow_name,
            workflow_ref=options.workflow_ref,
            workflow_file_sha=options.workflow_file_sha,
            artifact_name=options.artifact_name,
            artifact_upload_status=options.artifact_upload_status,
            artifact_id=options.artifact_id,
            artifact_digest=options.artifact_digest,
            artifact_url=options.artifact_url,
            artifact_retention_days=options.artifact_retention_days,
        )
        _write_json_report(evidence, options.output)
    except (ReleaseEvidenceValidationError, OSError) as exc:
        print(f"release evidence collection failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(evidence, indent=2, sort_keys=True))
    if options.fail_on_unsuccessful and (
        evidence["test"]["status"] != "PASSED" or evidence["build"]["status"] != "PASSED"
    ):
        return 1
    return 0


def finalize_artifact_publication(
    evidence: Dict[str, Any],
    *,
    upload_status: str,
    artifact_name: Optional[str],
    artifact_id: Optional[str] = None,
    artifact_digest: Optional[str] = None,
    artifact_url: Optional[str] = None,
    retention_days: Optional[Any] = None,
) -> Dict[str, Any]:
    """Attach actual upload-action outputs to a previously collected report."""
    status = _required_text(upload_status, "artifact_upload_status").upper()
    if status not in ARTIFACT_UPLOAD_STATUSES:
        allowed = ", ".join(sorted(ARTIFACT_UPLOAD_STATUSES))
        raise ReleaseEvidenceValidationError(f"artifact_upload_status must be one of: {allowed}.")

    finalized = dict(evidence)
    limitations = list(evidence.get("limitations") or [])
    name = _nullable_text(artifact_name, "artifact_name")
    artifact_id_value = _nullable_text(artifact_id, "artifact_id")
    digest_value = _nullable_text(artifact_digest, "artifact_digest")
    url_value = _nullable_text(artifact_url, "artifact_url")
    days_value = _optional_positive_int(retention_days, "artifact_retention_days")
    metadata_values = [artifact_id_value, digest_value, url_value]
    metadata_status = "COMPLETE" if all(metadata_values) else "PARTIAL" if any(metadata_values) else "UNAVAILABLE"

    finalized["artifact_publication"] = {
        "status": status,
        "metadata_status": metadata_status,
        "name": name,
        "id": artifact_id_value,
        "digest": digest_value,
        "digest_algorithm": "SHA-256" if digest_value else None,
        "url": url_value,
        "retention_days": days_value,
        "retention_source": "upload-artifact action input" if days_value is not None else None,
    }
    finalized["artifact_location"] = url_value if status == "SUCCEEDED" and url_value else None

    if status == "FAILED":
        limitations.append("Evidence payload artifact upload failed; no successful publication is claimed.")
    elif status == "SUCCEEDED" and metadata_status != "COMPLETE":
        limitations.append("Evidence payload artifact uploaded, but one or more GitHub artifact outputs were unavailable.")
    elif status in {"NOT_ATTEMPTED", "UNKNOWN"}:
        limitations.append("Evidence payload artifact publication was not confirmed.")
    if days_value is not None:
        limitations.append("Artifact retention_days records the configured upload input; repository retention policy may impose a lower effective period.")
    limitations.append(
        "This finalized JSON manifest is a separate artifact; embedded publication metadata describes the primary evidence payload artifact."
    )

    finalized["limitations"] = limitations
    return finalized


def finalize_main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize release evidence with actual upload-artifact outputs.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--upload-status", required=True, choices=sorted(ARTIFACT_UPLOAD_STATUSES))
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-id")
    parser.add_argument("--artifact-digest")
    parser.add_argument("--artifact-url")
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--fail-on-unsuccessful", action="store_true")
    options = parser.parse_args(argv)
    try:
        with Path(options.input).open(encoding="utf-8") as source:
            evidence = json.load(source)
        finalized = finalize_artifact_publication(
            evidence,
            upload_status=options.upload_status,
            artifact_name=options.artifact_name,
            artifact_id=options.artifact_id,
            artifact_digest=options.artifact_digest,
            artifact_url=options.artifact_url,
            retention_days=options.retention_days,
        )
        _write_json_report(finalized, options.output)
    except (OSError, json.JSONDecodeError, ReleaseEvidenceValidationError) as exc:
        print(f"release evidence finalization failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(finalized, indent=2, sort_keys=True))
    if options.fail_on_unsuccessful and (
        finalized.get("test", {}).get("status") != "PASSED"
        or finalized.get("build", {}).get("status") != "PASSED"
        or finalized["artifact_publication"]["status"] != "SUCCEEDED"
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
