from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0007_alter_reportscheme_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='studentreportsubjectscore',
            name='grade',
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
