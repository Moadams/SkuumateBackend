import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0004_remove_subscription_amount_paid_and_more'),
    ]

    operations = [
        # Rename the legacy Plan model into Package (data and table are
        # preserved — this is a table rename + model rename, NOT a delete).
        migrations.RenameModel(
            old_name='Plan',
            new_name='Package',
        ),
        migrations.RenameField(
            model_name='Package',
            old_name='price_per_term',
            new_name='price',
        ),
        migrations.RenameField(
            model_name='Package',
            old_name='min_students',
            new_name='minimum_students',
        ),
        migrations.RenameField(
            model_name='Package',
            old_name='max_students',
            new_name='maximum_students',
        ),
        # plan_type becomes optional display metadata (was required+unique,
        # which hardcoded the three tiers).
        migrations.AlterField(
            model_name='Package',
            name='plan_type',
            field=models.CharField(
                blank=True,
                choices=[('lite', 'Lite'), ('advantage', 'Advantage'), ('enterprise', 'Enterprise')],
                help_text='Legacy display tier. Not used for feature gating.',
                max_length=20,
                null=True,
            ),
        ),
        # New package metadata. code is temporarily nullable so existing
        # rows can be backfilled by the data migration (0006), then made
        # non-null in 0007.
        migrations.AddField(
            model_name='Package',
            name='code',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='Package',
            name='billing_period',
            field=models.CharField(
                choices=[('TERM', 'Term'), ('MONTH', 'Month'), ('YEAR', 'Year')],
                default='TERM',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='Package',
            name='currency',
            field=models.CharField(default='GHS', max_length=3),
        ),
        migrations.AddField(
            model_name='Package',
            name='is_public',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='Package',
            name='display_order',
            field=models.PositiveIntegerField(default=0),
        ),
        # Feature registry + package entitlements/limits.
        migrations.CreateModel(
            name='Feature',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=120)),
                ('code', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(blank=True, max_length=80)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['category', 'name'],
            },
        ),
        migrations.CreateModel(
            name='PackageFeature',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_enabled', models.BooleanField(default=True)),
                ('feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='package_features', to='subscriptions.feature')),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='package_features', to='subscriptions.package')),
            ],
            options={
                'ordering': ['feature__category', 'feature__name'],
            },
        ),
        migrations.CreateModel(
            name='PackageLimit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(max_length=80)),
                ('name', models.CharField(max_length=120)),
                ('value', models.PositiveIntegerField()),
                ('description', models.TextField(blank=True)),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='package_limits', to='subscriptions.package')),
            ],
            options={
                'ordering': ['key'],
            },
        ),
        migrations.AddConstraint(
            model_name='packagefeature',
            constraint=models.UniqueConstraint(fields=('package', 'feature'), name='uniq_package_feature'),
        ),
        migrations.AddConstraint(
            model_name='packagelimit',
            constraint=models.UniqueConstraint(fields=('package', 'key'), name='uniq_package_limit_key'),
        ),
        # Drop the legacy ordering (which referenced price_per_term) so the
        # historical model state is resolvable by later (data) migrations.
        migrations.AlterModelOptions(
            name='package',
            options={'ordering': ['display_order', 'price']},
        ),
    ]