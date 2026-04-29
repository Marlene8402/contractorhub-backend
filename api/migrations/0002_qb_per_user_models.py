from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0001_initial'),
    ]

    operations = [
        # Drop the old per-Company QBSyncLog (different schema, no production data).
        migrations.DeleteModel(
            name='QBSyncLog',
        ),

        # Per-User QB OAuth account.
        migrations.CreateModel(
            name='QBAccount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.TextField()),
                ('refresh_token', models.TextField()),
                ('token_expires_at', models.DateTimeField()),
                ('realm_id', models.CharField(max_length=20)),
                ('is_connected', models.BooleanField(default=True)),
                ('connected_at', models.DateTimeField(auto_now_add=True)),
                ('last_refreshed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='qb_account',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),

        # Per-User CSI category → GL account mapping.
        migrations.CreateModel(
            name='QBGLMapping',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(max_length=50)),
                ('gl_account_number', models.CharField(max_length=20)),
                ('gl_account_name', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='qb_gl_mappings',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['category'],
                'unique_together': {('user', 'category')},
            },
        ),

        # New per-User QBSyncLog with idempotency + retry tracking.
        migrations.CreateModel(
            name='QBSyncLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sync_type', models.CharField(max_length=20)),
                ('object_id', models.CharField(max_length=50)),
                ('object_type', models.CharField(max_length=20)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('syncing', 'Syncing'),
                        ('success', 'Success'),
                        ('failed', 'Failed'),
                    ],
                    max_length=20,
                )),
                ('attempt_count', models.IntegerField(default=0)),
                ('qb_transaction_id', models.CharField(blank=True, max_length=100, null=True)),
                ('idempotency_key', models.CharField(max_length=100, unique=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('error_code', models.CharField(blank=True, max_length=50, null=True)),
                ('last_attempted_at', models.DateTimeField(blank=True, null=True)),
                ('synced_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='qb_sync_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='qbsynclog',
            index=models.Index(fields=['user', 'status'], name='api_qbsync_user_id_status_idx'),
        ),
        migrations.AddIndex(
            model_name='qbsynclog',
            index=models.Index(fields=['idempotency_key'], name='api_qbsync_idempot_idx'),
        ),
    ]
