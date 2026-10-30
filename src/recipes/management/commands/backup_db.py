"""Back up the SQLite database as SQL.

Writes two files:

- **schema** (`docs/schema.sql`) — `CREATE` statements only, sorted so the file
  only changes when the schema does. Committed: it is the record of what the
  migrations add up to, kept current per AGENTS.md.
- **dump** (`docs/dump-<timestamp>.sql`) — schema and every row, enough to
  rebuild the database with `sqlite3 db.sqlite3 < docs/dump-….sql`. Git-ignored:
  it holds the data.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

_SCHEMA_SQL = """
    SELECT sql FROM sqlite_master
    WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
    ORDER BY tbl_name, type DESC, name
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Command(BaseCommand):
    help = "Write the database schema to docs/schema.sql and a full SQL dump next to it"

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument("--schema", type=Path, help="Schema file (default docs/schema.sql)")
        parser.add_argument(
            "--dump", type=Path, help="Dump file (default docs/dump-<timestamp>.sql)"
        )
        parser.add_argument(
            "--schema-only", action="store_true", help="Write the schema, skip the data dump"
        )

    def handle(self, *args, **options):
        """Write the schema and, unless --schema-only, the full dump."""
        if connection.vendor != "sqlite":
            msg = f"backup_db supports SQLite only, not {connection.vendor}"
            raise CommandError(msg)

        docs = Path(settings.BASE_DIR) / "docs"
        schema_path = options["schema"] or docs / "schema.sql"
        with connection.cursor() as cursor:
            cursor.execute(_SCHEMA_SQL)
            statements = [row[0] for row in cursor.fetchall()]
        _write(schema_path, "".join(f"{sql};\n" for sql in statements))
        self.stdout.write(self.style.SUCCESS(f"Schema written to {schema_path}"))

        if options["schema_only"]:
            return
        stamp = f"{timezone.localtime():%Y%m%d-%H%M%S}"
        dump_path = options["dump"] or docs / f"dump-{stamp}.sql"
        _write(dump_path, "".join(f"{line}\n" for line in connection.connection.iterdump()))
        self.stdout.write(self.style.SUCCESS(f"Dump written to {dump_path}"))
