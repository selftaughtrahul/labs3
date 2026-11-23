"""Merge duplicate deliverable spellings onto one keeper id."""

from django.core.management.base import BaseCommand
from django.db import transaction

from creators.deliverable_compact import compact, consolidate, dump_affected


class Command(BaseCommand):
    help = (
        "Point duplicate deliverable types at a keeper name, rebuild rate bundle keys, "
        "and delete unused names. Rate rows that would share a bundle stay as they are."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the moves without writing.",
        )
        parser.add_argument(
            "--dump",
            help="Write deal lines and rate links for affected types to this JSON file first.",
        )
        parser.add_argument(
            "--legacy-ids",
            action="store_true",
            help="Use the previous id map instead of the name-based consolidation.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        dump_path = options.get("dump")
        with transaction.atomic():
            if dump_path:
                dump_affected(dump_path, stdout=self.stdout)
            if options["legacy_ids"]:
                result = compact(stdout=self.stdout)
            else:
                result = consolidate(stdout=self.stdout)
            if dry_run:
                transaction.set_rollback(True)
        prefix = "Would " if dry_run else ""
        self.stdout.write(f"{prefix}move {result['moved_deals']} deal lines")
        self.stdout.write(f"{prefix}drop {result['dropped_deals']} extra deal lines")
        self.stdout.write(f"{prefix}move {result['moved_rates']} rates")
        self.stdout.write(f"{prefix}skip {result['skipped_rates']} rates with a price clash")
        self.stdout.write(f"{prefix}rename {result['renamed']} names")
        self.stdout.write(f"{prefix}delete {result['deleted']} unused deliverable types")
