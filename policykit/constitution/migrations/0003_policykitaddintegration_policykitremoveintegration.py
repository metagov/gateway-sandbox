# Generated by Django 3.2.2 on 2021-11-10 14:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('constitution', '0002_auto_20210909_1512'),
    ]

    operations = [
        migrations.CreateModel(
            name='PolicykitAddIntegration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'permissions': [('can_add_integration', 'Can add platform integration')],
                'managed': False,
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='PolicykitRemoveIntegration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'permissions': [('can_remove_integration', 'Can remove platform integration')],
                'managed': False,
                'default_permissions': (),
            },
        ),
    ]
