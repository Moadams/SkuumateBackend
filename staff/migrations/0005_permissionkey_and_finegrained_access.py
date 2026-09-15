from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0004_remove_staffprofile_positions_staffprofile_role_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissionKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(max_length=100, unique=True)),
                ('label', models.CharField(max_length=150)),
                ('module', models.CharField(max_length=50)),
                ('description', models.TextField(blank=True)),
                ('is_system', models.BooleanField(default=True, help_text='System registry keys cannot be deleted.')),
            ],
            options={
                'verbose_name': 'Permission Key',
                'ordering': ['module', 'key'],
            },
        ),
        migrations.RenameField(
            model_name='staffposition',
            old_name='permissions',
            new_name='legacy_permissions',
        ),
        migrations.AddField(
            model_name='staffposition',
            name='permissions',
            field=models.ManyToManyField(
                blank=True,
                help_text='Permission keys granted by this position.',
                related_name='positions',
                to='staff.permissionkey',
            ),
        ),
        migrations.AddField(
            model_name='staffprofile',
            name='permission_grants',
            field=models.ManyToManyField(
                blank=True,
                help_text='Individual permission keys granted beyond positions.',
                related_name='granted_to_staff',
                to='staff.permissionkey',
            ),
        ),
        migrations.AddField(
            model_name='staffprofile',
            name='permission_revokes',
            field=models.ManyToManyField(
                blank=True,
                help_text='Individual permission keys revoked from this staff member.',
                related_name='revoked_from_staff',
                to='staff.permissionkey',
            ),
        ),
        migrations.AddField(
            model_name='staffprofile',
            name='positions',
            field=models.ManyToManyField(
                blank=True,
                help_text='Position bundles assigned to this staff member.',
                related_name='staff_members',
                to='staff.staffposition',
            ),
        ),
    ]