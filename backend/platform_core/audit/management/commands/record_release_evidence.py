"""Management command for caller-reported technical execution evidence."""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_core.audit.release_evidence import (
    ReleaseEvidenceValidationError,
    build_release_evidence,
    persist_release_evidence,
    RESULT_STATUSES,
)


class Command(BaseCommand):
    help = "Record caller-reported technical test/build evidence in the platform audit log."

    def add_arguments(self, parser):
        parser.add_argument("--requirement-ref", required=True)
        parser.add_argument("--repository", default=os.getenv("DRIVERXTRA_REPOSITORY") or os.getenv("GITHUB_REPOSITORY"))
        parser.add_argument("--commit-sha", default=os.getenv("DRIVERXTRA_COMMIT_SHA") or os.getenv("GITHUB_SHA"))
        parser.add_argument("--environment", default=os.getenv("DRIVERXTRA_ENVIRONMENT"))
        parser.add_argument("--test-status", required=True, choices=sorted(RESULT_STATUSES))
        parser.add_argument("--test-command")
        parser.add_argument("--test-summary")
        parser.add_argument("--build-status", required=True, choices=sorted(RESULT_STATUSES))
        parser.add_argument("--build-command")
        parser.add_argument("--build-summary")
        parser.add_argument("--artifact-location")
        parser.add_argument("--limitation", action="append", default=[])
        parser.add_argument("--output", help="Optional path for a JSON copy of the evidence record.")

    def handle(self, *args, **options):
        if not options["repository"]:
            raise CommandError("--repository or DRIVERXTRA_REPOSITORY/GITHUB_REPOSITORY is required.")
        if not options["environment"]:
            raise CommandError("--environment or DRIVERXTRA_ENVIRONMENT is required.")

        try:
            evidence = build_release_evidence(
                requirement_ref=options["requirement_ref"],
                repository=options["repository"],
                commit_sha=options["commit_sha"],
                environment=options["environment"],
                test_status=options["test_status"],
                test_command=options["test_command"],
                test_summary=options["test_summary"],
                build_status=options["build_status"],
                build_command=options["build_command"],
                build_summary=options["build_summary"],
                artifact_location=options["artifact_location"],
                limitations=options["limitation"],
            )
        except ReleaseEvidenceValidationError as exc:
            raise CommandError(str(exc)) from exc

        serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        output_path = options["output"]
        if output_path:
            try:
                with Path(output_path).open("x", encoding="utf-8") as report:
                    report.write(serialized)
            except FileExistsError as exc:
                raise CommandError(f"Evidence JSON already exists at '{output_path}'; refusing to overwrite it.") from exc
            except OSError as exc:
                raise CommandError(f"Could not write evidence JSON to '{output_path}': {exc}") from exc

        persist_release_evidence(evidence)
        self.stdout.write(serialized.rstrip())
