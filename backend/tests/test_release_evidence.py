import json
from io import StringIO
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from django.core.management import call_command, CommandError

from platform_core.audit import release_evidence
from platform_core.audit.release_evidence import (
    RESULT_STATUSES,
    ReleaseEvidenceValidationError,
    build_release_evidence,
    record_release_evidence,
)


def _valid_metadata(**overrides):
    values = {
        "requirement_ref": "DX-GC-08/RE-01",
        "repository": "example/driverxtra",
        "commit_sha": "abcdef1234567",
        "environment": "ci-test",
        "test_status": "PASSED",
        "test_command": "python -m pytest tests/test_release_evidence.py",
        "build_status": "NOT_RUN",
        "limitations": ["Frontend build not run."],
    }
    values.update(overrides)
    return values


def test_build_release_evidence_captures_required_metadata_and_utc_timestamp():
    evidence = build_release_evidence(**_valid_metadata())

    assert evidence["evidence_type"] == "TECHNICAL_EXECUTION"
    assert evidence["evidence_scope"] == "TECHNICAL_EXECUTION_ONLY"
    assert evidence["requirement_ref"] == "DX-GC-08/RE-01"
    assert evidence["repository"] == "example/driverxtra"
    assert evidence["commit_sha"] == "abcdef1234567"
    assert evidence["environment"] == "ci-test"
    assert evidence["test"]["status"] == "PASSED"
    assert evidence["test"]["command"].startswith("python -m pytest")
    assert evidence["build"]["status"] == "NOT_RUN"
    assert evidence["results_are_caller_reported"] is True
    assert evidence["result_source"] == "CALLER_REPORTED"
    assert evidence["limitations"] == ["Frontend build not run."]
    # Existing top-level fields remain JSON serializable for consumers of the original report shape.
    assert json.loads(json.dumps(evidence))["artifact_location"] is None
    assert datetime.fromisoformat(evidence["execution_timestamp_utc"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


def test_complete_github_actions_run_workflow_and_upload_metadata():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08/RE-01",
        repository="example/driverxtra",
        repository_id="123456789",
        commit_sha="abcdef1234567",
        environment="github-actions",
        run_id="987654321",
        run_number="42",
        run_attempt="2",
        workflow_name="Deploy DriverXtra Platform",
        workflow_ref="example/driverxtra/.github/workflows/deploy.yml@refs/heads/main",
        workflow_file_sha="1234567abcdef0",
        test_command="python -m pytest",
        test_exit_code=0,
        test_attempted=True,
        build_command="npm run build",
        build_exit_code=0,
        build_attempted=True,
        artifact_name="driverxtra-release-evidence-987654321-attempt-2",
        artifact_upload_status="SUCCEEDED",
        artifact_id="456789",
        artifact_digest="sha256:deadbeef",
        artifact_url="https://github.com/example/driverxtra/actions/runs/987654321/artifacts/456789",
        artifact_retention_days=90,
    )

    assert evidence["repository_id"] == 123456789
    assert evidence["commit_sha"] == "abcdef1234567"
    assert evidence["github_actions"] == {
        "run_id": 987654321,
        "run_number": 42,
        "run_attempt": 2,
        "workflow": {
            "name": "Deploy DriverXtra Platform",
            "ref": "example/driverxtra/.github/workflows/deploy.yml@refs/heads/main",
            "file_path": ".github/workflows/deploy.yml",
            "file_sha": "1234567abcdef0",
        },
    }
    publication = evidence["artifact_publication"]
    assert publication["name"] == "driverxtra-release-evidence-987654321-attempt-2"
    assert publication["id"] == "456789"
    assert publication["digest"] == "sha256:deadbeef"
    assert publication["digest_algorithm"] == "SHA-256"
    assert publication["retention_days"] == 90
    assert publication["metadata_status"] == "COMPLETE"
    assert evidence["artifact_location"] == publication["url"]
    assert evidence["results_are_caller_reported"] is False


@pytest.mark.parametrize("field", ["run_id", "run_number"])
def test_missing_github_run_identity_is_unavailable_not_fabricated(field):
    metadata = {
        "run_id": "100",
        "run_number": "12",
        "run_attempt": "1",
        "workflow_name": "Build",
        "workflow_ref": "example/driverxtra/.github/workflows/ci.yml@refs/heads/main",
        "workflow_file_sha": "abcdef1234567",
    }
    metadata[field] = ""
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command=None,
        test_exit_code=None,
        build_command=None,
        build_exit_code=None,
        **metadata,
    )

    assert evidence["github_actions"][field] is None
    assert any(field.replace("_", " ") in limitation.lower() for limitation in evidence["limitations"])


def test_missing_workflow_file_sha_is_unavailable_and_does_not_use_repository_sha():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        commit_sha="abcdef1234567",
        environment="github-actions",
        workflow_ref="example/driverxtra/.github/workflows/ci.yml@refs/heads/main",
        test_command=None,
        test_exit_code=None,
        build_command=None,
        build_exit_code=None,
    )

    assert evidence["commit_sha"] == "abcdef1234567"
    assert evidence["github_actions"]["workflow"]["file_sha"] is None
    assert evidence["github_actions"]["workflow"]["file_path"] == ".github/workflows/ci.yml"
    assert any("workflow-file SHA" in limitation for limitation in evidence["limitations"])


def test_finalizer_captures_actual_artifact_outputs_and_reports_missing_digest():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command="pytest",
        test_exit_code=0,
        test_attempted=True,
        build_command="npm run build",
        build_exit_code=0,
        build_attempted=True,
    )
    finalized = release_evidence.finalize_artifact_publication(
        evidence,
        upload_status="SUCCEEDED",
        artifact_name="primary-evidence",
        artifact_id="987",
        artifact_digest="",
        artifact_url="https://example.test/artifacts/987",
        retention_days="90",
    )

    assert finalized["artifact_publication"]["name"] == "primary-evidence"
    assert finalized["artifact_publication"]["id"] == "987"
    assert finalized["artifact_publication"]["digest"] is None
    assert finalized["artifact_publication"]["metadata_status"] == "PARTIAL"
    assert any("outputs were unavailable" in item for item in finalized["limitations"])
    assert finalized["artifact_location"] == "https://example.test/artifacts/987"


def test_finalizer_records_upload_failure_without_claiming_publication():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command="pytest",
        test_exit_code=1,
        test_attempted=True,
        build_command="npm run build",
        build_exit_code=2,
        build_attempted=True,
    )
    finalized = release_evidence.finalize_artifact_publication(
        evidence,
        upload_status="FAILED",
        artifact_name="primary-evidence",
        artifact_id="",
        artifact_digest="",
        artifact_url="",
        retention_days=90,
    )

    assert finalized["artifact_publication"]["status"] == "FAILED"
    assert finalized["artifact_publication"]["metadata_status"] == "UNAVAILABLE"
    assert finalized["artifact_publication"]["id"] is None
    assert finalized["artifact_publication"]["digest"] is None
    assert finalized["artifact_location"] is None
    assert finalized["test"]["status"] == "FAILED"
    assert finalized["build"]["status"] == "FAILED"
    assert any("upload failed" in item for item in finalized["limitations"])


def test_finalized_json_is_written_before_failure_exit_and_serializes_legacy_fields():
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
        source = Path(temp_dir) / "source.json"
        output = Path(temp_dir) / "final.json"
        evidence = release_evidence.build_release_evidence_from_execution(
            requirement_ref="DX-GC-08",
            repository="example/driverxtra",
            environment="github-actions",
            test_command="pytest",
            test_exit_code=1,
            test_attempted=True,
            build_command="npm run build",
            build_exit_code=0,
            build_attempted=True,
        )
        source.write_text(json.dumps(evidence), encoding="utf-8")
        result = release_evidence.main([
            "finalize", "--input", str(source), "--output", str(output),
            "--upload-status", "SUCCEEDED", "--artifact-name", "primary",
            "--artifact-id", "123", "--artifact-digest", "sha256:abc",
            "--artifact-url", "https://example.test/artifacts/123", "--retention-days", "90",
            "--fail-on-unsuccessful",
        ])
        saved = json.loads(output.read_text(encoding="utf-8"))

    assert result == 1
    assert saved["test"]["status"] == "FAILED"
    assert saved["build"]["status"] == "PASSED"
    assert saved["result_source"] == "CI_EXECUTION_OUTCOME"
    assert saved["evidence_scope"] == "TECHNICAL_EXECUTION_ONLY"
    assert saved["artifact_publication"]["digest"] == "sha256:abc"
    assert json.loads(json.dumps(saved))["execution_timestamp_utc"] == evidence["execution_timestamp_utc"]


def test_finalizer_writes_failed_upload_result_then_exits_nonzero():
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
        source = Path(temp_dir) / "source.json"
        output = Path(temp_dir) / "final.json"
        evidence = release_evidence.build_release_evidence_from_execution(
            requirement_ref="DX-GC-08",
            repository="example/driverxtra",
            environment="github-actions",
            test_command="pytest",
            test_exit_code=0,
            test_attempted=True,
            build_command="npm run build",
            build_exit_code=0,
            build_attempted=True,
        )
        source.write_text(json.dumps(evidence), encoding="utf-8")
        result = release_evidence.main([
            "finalize", "--input", str(source), "--output", str(output),
            "--upload-status", "FAILED", "--artifact-name", "primary",
            "--retention-days", "90", "--fail-on-unsuccessful",
        ])
        saved = json.loads(output.read_text(encoding="utf-8"))

    assert result == 1
    assert saved["test"]["status"] == "PASSED"
    assert saved["build"]["status"] == "PASSED"
    assert saved["artifact_publication"]["status"] == "FAILED"
    assert saved["artifact_publication"]["id"] is None
    assert saved["artifact_publication"]["digest"] is None


@pytest.mark.parametrize("status", sorted(RESULT_STATUSES))
def test_all_result_statuses_are_recordable(status):
    test_command = "pytest tests" if status in {"PASSED", "FAILED"} else None
    build_command = "npm run build" if status in {"PASSED", "FAILED"} else None
    evidence = build_release_evidence(**_valid_metadata(
        test_status=status,
        test_command=test_command,
        build_status=status,
        build_command=build_command,
    ))

    assert evidence["test"]["status"] == status
    assert evidence["build"]["status"] == status


@pytest.mark.parametrize("field", ["requirement_ref", "repository", "environment", "test_status", "build_status"])
def test_missing_required_metadata_is_rejected(field):
    with pytest.raises(ReleaseEvidenceValidationError, match="required"):
        build_release_evidence(**_valid_metadata(**{field: "   "}))


@pytest.mark.parametrize("field,status,command_field", [
    ("test_command", "test_status", "PASSED"),
    ("build_command", "build_status", "FAILED"),
])
def test_executed_result_requires_command(field, status, command_field):
    with pytest.raises(ReleaseEvidenceValidationError, match="command is required"):
        build_release_evidence(**_valid_metadata(**{field: None, status: command_field}))


def test_optional_commit_and_artifact_reference_are_preserved():
    location = "https://ci.example/reports/run-123/junit.xml"
    evidence = build_release_evidence(**_valid_metadata(commit_sha=None, artifact_location=location))

    assert evidence["commit_sha"] is None
    assert evidence["artifact_location"] == location


@pytest.mark.parametrize("sha", ["not-a-sha", "abc", "g" * 40])
def test_invalid_commit_sha_is_rejected(sha):
    with pytest.raises(ReleaseEvidenceValidationError, match="hexadecimal SHA"):
        build_release_evidence(**_valid_metadata(commit_sha=sha))


def test_record_uses_existing_audit_writer(monkeypatch):
    captured = {}

    def fake_audit_writer(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("platform_core.audit.writer.record_audit_entry", fake_audit_writer)
    evidence = record_release_evidence(**_valid_metadata())

    assert captured["event_type"] == "engineering.release_evidence.recorded"
    assert captured["resource_type"] == "EngineeringExecutionEvidence"
    assert captured["resource_id"] == evidence["evidence_id"]
    assert captured["metadata"] == evidence


def test_management_command_writes_json_and_records_audit(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "platform_core.audit.management.commands.record_release_evidence.persist_release_evidence",
        lambda evidence: captured.append(evidence),
    )
    command_output = StringIO()
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
        output = Path(temp_dir) / "execution-evidence.json"
        call_command(
            "record_release_evidence",
            "--requirement-ref", "DX-GC-08/RE-01",
            "--repository", "example/driverxtra",
            "--environment", "ci-test",
            "--test-status", "NOT_RUN",
            "--build-status", "NOT_APPLICABLE",
            "--artifact-location", "artifacts/report.xml",
            "--output", str(output),
            stdout=command_output,
        )
        saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["test"]["status"] == "NOT_RUN"
    assert saved["build"]["status"] == "NOT_APPLICABLE"
    assert saved["artifact_location"] == "artifacts/report.xml"
    assert len(captured) == 1
    assert captured[0] == saved
    assert json.loads(command_output.getvalue()) == saved


def test_management_command_rejects_missing_environment(monkeypatch):
    monkeypatch.delenv("DRIVERXTRA_ENVIRONMENT", raising=False)
    with pytest.raises(CommandError, match="environment"):
        call_command(
            "record_release_evidence",
            "--requirement-ref", "DX-GC-08/RE-01",
            "--repository", "example/driverxtra",
            "--test-status", "NOT_RUN",
            "--build-status", "NOT_RUN",
        )


def test_ci_execution_codes_are_mapped_without_manual_success_claims():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        commit_sha="abcdef1234567",
        environment="github-actions",
        test_command="python -m pytest",
        test_exit_code=7,
        test_attempted=True,
        build_command="npm run build",
        build_exit_code=0,
        build_attempted=True,
    )

    assert evidence["test"]["status"] == "FAILED"
    assert evidence["test"]["summary"] == "Process exited with code 7."
    assert evidence["build"]["status"] == "PASSED"
    assert evidence["result_source"] == "CI_EXECUTION_OUTCOME"
    assert evidence["results_are_caller_reported"] is False


def test_nonzero_build_exit_code_is_failed():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command="python -m pytest",
        test_exit_code=0,
        test_attempted=True,
        build_command="npm run build",
        build_exit_code=2,
        build_attempted=True,
    )

    assert evidence["test"]["status"] == "PASSED"
    assert evidence["build"]["status"] == "FAILED"
    assert evidence["build"]["summary"] == "Process exited with code 2."


def test_json_only_collector_writes_report_then_fails_for_failed_check():
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
        output = Path(temp_dir) / "failed-evidence.json"
        result = release_evidence.main([
            "--requirement-ref", "DX-GC-08",
            "--repository", "example/driverxtra",
            "--commit-sha", "abcdef1234567",
            "--environment", "github-actions",
            "--test-command", "python -m pytest",
            "--test-exit-code", "1",
            "--test-attempted",
            "--build-command", "npm run build",
            "--build-exit-code", "0",
            "--build-attempted",
            "--artifact-location", "github-actions://artifact/run-123",
            "--output", str(output),
            "--fail-on-unsuccessful",
        ])
        saved = json.loads(output.read_text(encoding="utf-8"))

    assert result == 1
    assert saved["test"]["status"] == "FAILED"
    assert saved["build"]["status"] == "PASSED"


def test_json_only_collector_returns_success_when_both_exit_codes_are_zero():
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
        output = Path(temp_dir) / "passed-evidence.json"
        result = release_evidence.main([
            "--requirement-ref", "DX-GC-08",
            "--repository", "example/driverxtra",
            "--environment", "github-actions",
            "--test-command", "python -m pytest",
            "--test-exit-code", "0",
            "--test-attempted",
            "--build-command", "npm run build",
            "--build-exit-code", "0",
            "--build-attempted",
            "--output", str(output),
            "--fail-on-unsuccessful",
        ])
        saved = json.loads(output.read_text(encoding="utf-8"))

    assert result == 0
    assert saved["test"]["status"] == "PASSED"
    assert saved["build"]["status"] == "PASSED"


def test_json_only_collector_marks_dependency_block_as_blocked():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command="python -m pytest",
        test_exit_code=None,
        test_blocked=True,
        build_command="npm run build",
        build_exit_code=None,
        build_blocked=True,
        limitations=["Dependency installs failed."],
    )

    assert evidence["test"]["status"] == "BLOCKED"
    assert evidence["build"]["status"] == "BLOCKED"
    assert evidence["test"]["command"] == "python -m pytest"
    assert evidence["build"]["command"] == "npm run build"
    assert evidence["limitations"][0] == "Dependency installs failed."
    assert any("GitHub Actions run ID was unavailable" in item for item in evidence["limitations"])


def test_skipped_check_keeps_intended_command_with_not_run_status():
    evidence = release_evidence.build_release_evidence_from_execution(
        requirement_ref="DX-GC-08",
        repository="example/driverxtra",
        environment="github-actions",
        test_command="python -m pytest",
        test_exit_code=None,
        build_command="npm run build",
        build_exit_code=None,
    )

    assert evidence["test"]["status"] == "NOT_RUN"
    assert evidence["test"]["command"] == "python -m pytest"
    assert evidence["build"]["status"] == "NOT_RUN"
    assert evidence["build"]["command"] == "npm run build"


def test_existing_workflow_uploads_evidence_and_fails_on_unsuccessful_checks():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
    contents = workflow.read_text(encoding="utf-8")

    assert "--fail-on-unsuccessful" in contents
    assert "actions/upload-artifact@v4" in contents
    assert "if: always()" in contents
    assert "driverxtra-release-evidence-${{ github.run_id }}" in contents
    for expression in (
        "${GITHUB_RUN_ID:-}", "${GITHUB_RUN_NUMBER:-}", "${GITHUB_RUN_ATTEMPT:-}",
        "${GITHUB_WORKFLOW:-}", "${GITHUB_WORKFLOW_REF:-}", "${GITHUB_WORKFLOW_SHA:-}",
        "${GITHUB_SHA}", "${GITHUB_REPOSITORY_ID:-}",
    ):
        assert expression in contents
    assert "steps.primary_upload.outputs.artifact-id" in contents
    assert "steps.primary_upload.outputs.artifact-digest" in contents
    assert "retention-days: 90" in contents
    assert "release-evidence-final.json" in contents
    deploy_job = contents.split("\n  deploy:\n", 1)[1]
    assert "needs:" not in deploy_job
