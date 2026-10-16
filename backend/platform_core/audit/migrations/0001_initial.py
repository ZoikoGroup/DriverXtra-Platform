import uuid
from django.db import migrations, models


def create_table_safely(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                CREATE SCHEMA IF NOT EXISTS platform;

                CREATE TABLE IF NOT EXISTS "platform"."audit_log" (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    event_type VARCHAR(150) NOT NULL,
                    action VARCHAR(150) NOT NULL,
                    resource_type VARCHAR(100) NOT NULL,
                    resource_id VARCHAR(255) NOT NULL DEFAULT '',
                    actor_id UUID NULL,
                    actor_kind VARCHAR(50) NOT NULL DEFAULT 'USER',
                    operating_org_id UUID NULL,
                    status VARCHAR(10) NOT NULL,
                    correlation_id VARCHAR(255) NOT NULL DEFAULT '',
                    reason_code VARCHAR(100) NOT NULL DEFAULT '',
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                );

                CREATE INDEX IF NOT EXISTS audit_log_event_t_e775dd_idx ON "platform"."audit_log" (event_type, created_at);
                CREATE INDEX IF NOT EXISTS audit_log_resourc_2570dd_idx ON "platform"."audit_log" (resource_type, resource_id);
            """)
    elif schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            try:
                cursor.execute("ATTACH DATABASE ':memory:' AS platform;")
            except Exception:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "platform"."audit_log" (
                    id CHAR(32) PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    event_type VARCHAR(150) NOT NULL,
                    action VARCHAR(150) NOT NULL,
                    resource_type VARCHAR(100) NOT NULL,
                    resource_id VARCHAR(255) NOT NULL DEFAULT '',
                    actor_id CHAR(32) NULL,
                    actor_kind VARCHAR(50) NOT NULL DEFAULT 'USER',
                    operating_org_id CHAR(32) NULL,
                    status VARCHAR(10) NOT NULL,
                    correlation_id VARCHAR(255) NOT NULL DEFAULT '',
                    reason_code VARCHAR(100) NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
            """)


def drop_table_safely(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS "platform"."audit_log";')
    elif schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS "platform"."audit_log";')


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='AuditLog',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                        ('event_type', models.CharField(db_index=True, max_length=150)),
                        ('action', models.CharField(db_index=True, max_length=150)),
                        ('resource_type', models.CharField(max_length=100)),
                        ('resource_id', models.CharField(blank=True, default='', max_length=255)),
                        ('actor_id', models.UUIDField(blank=True, db_index=True, null=True)),
                        ('actor_kind', models.CharField(blank=True, default='USER', max_length=50)),
                        ('operating_org_id', models.UUIDField(blank=True, db_index=True, null=True)),
                        ('status', models.CharField(choices=[('ALLOWED', 'Allowed'), ('DENIED', 'Denied')], db_index=True, max_length=10)),
                        ('correlation_id', models.CharField(blank=True, db_index=True, default='', max_length=255)),
                        ('reason_code', models.CharField(blank=True, default='', max_length=100)),
                        ('metadata', models.JSONField(blank=True, default=dict)),
                    ],
                    options={
                        'db_table': '"platform"."audit_log"',
                        'ordering': ['-created_at'],
                        'indexes': [models.Index(fields=['event_type', 'created_at'], name='audit_log_event_t_e775dd_idx'), models.Index(fields=['resource_type', 'resource_id'], name='audit_log_resourc_2570dd_idx')],
                    },
                ),
            ],
            database_operations=[
                migrations.RunPython(create_table_safely, reverse_code=drop_table_safely),
            ],
        ),
    ]
