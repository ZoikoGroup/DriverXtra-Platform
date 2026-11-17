import hashlib
import os
import shutil
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.support.models import TicketAttachment


def calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class Command(BaseCommand):
    help = (
        "Idempotently copies legacy support attachments from MEDIA_ROOT to PRIVATE_STORAGE_ROOT. "
        "Verifies content hashes and preserves original media files without deletion."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate migration without copying files.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        media_root = Path(settings.MEDIA_ROOT)
        private_root = Path(getattr(settings, 'PRIVATE_STORAGE_ROOT', settings.BASE_DIR / 'private_media'))

        self.stdout.write(self.style.NOTICE(f"Source media root:  {media_root}"))
        self.stdout.write(self.style.NOTICE(f"Target private root: {private_root}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No files will be modified."))

        # 1. Scan filesystem for legacy support_attachments
        legacy_dir = media_root / 'support_attachments'
        if not legacy_dir.exists():
            self.stdout.write(self.style.SUCCESS("No legacy 'support_attachments' directory found in MEDIA_ROOT."))
            return

        copied_count = 0
        skipped_count = 0
        verified_count = 0
        error_count = 0

        for root, _, files in os.walk(legacy_dir):
            for filename in files:
                source_path = Path(root) / filename
                rel_path = source_path.relative_to(media_root)
                target_path = private_root / rel_path

                try:
                    src_hash = calculate_sha256(source_path)

                    if target_path.exists() and target_path.is_file():
                        tgt_hash = calculate_sha256(target_path)
                        if src_hash == tgt_hash:
                            skipped_count += 1
                            continue

                    if not dry_run:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, target_path)
                        verify_hash = calculate_sha256(target_path)
                        if verify_hash != src_hash:
                            self.stdout.write(self.style.ERROR(f"Hash mismatch on copied file: {rel_path}"))
                            error_count += 1
                            continue

                    copied_count += 1
                    verified_count += 1
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"Error processing {rel_path}: {exc}"))
                    error_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nMigration complete: {copied_count} copied, {skipped_count} skipped (identical), "
            f"{verified_count} verified, {error_count} errors."
        ))

