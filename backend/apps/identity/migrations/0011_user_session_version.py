"""Session-version revocation for JWTs.

1. Adds ``User.session_version`` (default 0). JWTs carry it as the ``sv`` claim; tokens without
   ``sv`` (issued before this migration) are treated as version 0.
2. Backfill: accounts that are unusable right now (is_active=False, SUSPENDED or DEACTIVATED) are
   set to version 1, so tokens issued before this migration die if those accounts are reactivated.
   Usable accounts are not touched.
3. Creates a database trigger on the user table (PostgreSQL and SQLite) so that the version is
   maintained by EVERY update path (Model.save, QuerySet.update, bulk_update, raw SQL):
     - usable -> unusable transition: version = max(OLD, NEW) + 1
     - any other update:              version = max(OLD, NEW)   (it can never be lowered,
                                                                   e.g. by saving a stale object)

Reversible: reverse drops the triggers, skips the backfill and removes the column.
Note (SQLite only): a future migration that rebuilds the user table drops SQLite triggers;
tests/test_session_revocation.py asserts the trigger exists so this would fail loudly.
"""
from django.db import migrations, models
from django.db.models import Q

TRIGGER_NAME = 'trg_identity_user_session_version'
PG_FUNCTION_NAME = 'identity_user_session_version_guard'
BLOCKED_STATUSES = ('SUSPENDED', 'DEACTIVATED')


def _usable_sql(prefix):
    return f"({prefix}.is_active AND {prefix}.status NOT IN ('SUSPENDED', 'DEACTIVATED'))"


def backfill_unusable_accounts(apps, schema_editor):
    User = apps.get_model('identity', 'User')
    User.objects.filter(Q(is_active=False) | Q(status__in=BLOCKED_STATUSES)).update(session_version=1)


def create_session_version_trigger(apps, schema_editor):
    User = apps.get_model('identity', 'User')
    table = schema_editor.quote_name(User._meta.db_table)
    became_unusable = f"({_usable_sql('OLD')} AND NOT {_usable_sql('NEW')})"
    vendor = schema_editor.connection.vendor

    if vendor == 'postgresql':
        # BEFORE trigger edits NEW in place: no second UPDATE, so no recursion.
        sql = f"""
            CREATE OR REPLACE FUNCTION {PG_FUNCTION_NAME}() RETURNS TRIGGER AS $$
            BEGIN
                NEW.session_version := GREATEST(OLD.session_version, NEW.session_version)
                    + CASE WHEN {became_unusable} THEN 1 ELSE 0 END;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON {table};
            CREATE TRIGGER {TRIGGER_NAME}
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION {PG_FUNCTION_NAME}();
        """
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql)

    elif vendor == 'sqlite':
        # SQLite cannot assign NEW in a BEFORE trigger, so an AFTER trigger corrects the row.
        # Recursion: Django leaves recursive_triggers OFF; even if ON, the inner UPDATE changes
        # neither status nor is_active and never lowers the version, so WHEN is false and it stops.
        sql = f"""
            CREATE TRIGGER IF NOT EXISTS {TRIGGER_NAME}
            AFTER UPDATE ON {table}
            FOR EACH ROW
            WHEN NEW.session_version < OLD.session_version OR {became_unusable}
            BEGIN
                UPDATE {table}
                SET session_version = max(OLD.session_version, NEW.session_version)
                    + CASE WHEN {became_unusable} THEN 1 ELSE 0 END
                WHERE id = NEW.id;
            END;
        """
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql)


def drop_session_version_trigger(apps, schema_editor):
    User = apps.get_model('identity', 'User')
    table = schema_editor.quote_name(User._meta.db_table)
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON {table};")
            cursor.execute(f"DROP FUNCTION IF EXISTS {PG_FUNCTION_NAME}();")
        elif vendor == 'sqlite':
            cursor.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME};")


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0010_add_review_moderate_permission'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='session_version',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(backfill_unusable_accounts, migrations.RunPython.noop),
        migrations.RunPython(create_session_version_trigger, drop_session_version_trigger),
    ]
