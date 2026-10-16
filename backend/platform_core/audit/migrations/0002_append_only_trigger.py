from django.db import migrations


def create_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE OR REPLACE FUNCTION platform.reject_audit_mutation()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'AuditLog is append-only. UPDATE, DELETE, and TRUNCATE operations are strictly forbidden.';
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_audit_log_immutable ON "platform"."audit_log";
                CREATE TRIGGER trg_audit_log_immutable
                BEFORE UPDATE OR DELETE ON "platform"."audit_log"
                FOR EACH ROW
                EXECUTE FUNCTION platform.reject_audit_mutation();
            """)


def drop_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                DROP TRIGGER IF EXISTS trg_audit_log_immutable ON "platform"."audit_log";
                DROP FUNCTION IF EXISTS platform.reject_audit_mutation();
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('platform_audit', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_append_only_trigger, reverse_code=drop_append_only_trigger),
    ]
