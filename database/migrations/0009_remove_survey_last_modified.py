# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2018-04-18 17:02
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0008_auto_20180418_1701'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='survey',
            name='last_modified',
        ),
    ]