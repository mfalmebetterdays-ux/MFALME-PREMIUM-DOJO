# Generated migration for TimesTable Dojo initial schema
# Run: python manage.py migrate

import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.db.models.expressions
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # ── USER ──────────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("username", models.CharField(
                    error_messages={"unique": "A user with that username already exists."},
                    max_length=150, unique=True,
                    validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                )),
                ("first_name", models.CharField(blank=True, max_length=150)),
                ("last_name",  models.CharField(blank=True, max_length=150)),
                ("email",      models.EmailField(blank=True, max_length=254)),
                ("is_staff",   models.BooleanField(default=False)),
                ("is_active",  models.BooleanField(default=True)),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now)),
                # Custom fields
                ("role",    models.CharField(choices=[("student","Student"),("tutor","Tutor"),("admin","Admin")], default="student", max_length=10, db_index=True)),
                ("county",  models.CharField(blank=True, max_length=100)),
                ("school",  models.CharField(blank=True, max_length=200)),
                ("spec",    models.CharField(blank=True, choices=[("primary","Primary (Grades 1–4)"),("junior","Junior (Grades 5–7)"),("senior","Senior (Grades 8–10)"),("all","All Levels")], max_length=20)),
                ("is_paid", models.BooleanField(default=False, db_index=True)),
                # M2M
                ("groups", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
                "ordering": ["-date_joined"],
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),

        # ── BELT PROGRESS ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="BeltProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="belt_progress", to=settings.AUTH_USER_MODEL)),
                ("belt_id", models.CharField(choices=[("white","White Belt"),("yellow","Yellow Belt"),("blue","Blue Belt"),("red","Red Belt"),("black","Black Belt"),("brown","Brown Belt"),("purple","Purple Belt"),("gold","Gold Belt"),("master","Master Belt")], max_length=10, db_index=True)),
                ("status", models.CharField(choices=[("locked","Locked"),("active","Active"),("passed","Passed")], default="locked", max_length=10)),
                ("passed",      models.BooleanField(default=False)),
                ("attempts",    models.PositiveIntegerField(default=0)),
                ("best_acc",    models.FloatField(default=0.0)),
                ("levels_done", models.JSONField(default=list)),
                ("updated_at",  models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Belt Progress",
                "verbose_name_plural": "Belt Progress",
            },
        ),
        migrations.AddConstraint(
            model_name="beltprogress",
            constraint=models.UniqueConstraint(fields=["user", "belt_id"], name="unique_user_belt"),
        ),

        # ── FACT MEMORY ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="FactMemory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fact_memory", to=settings.AUTH_USER_MODEL)),
                ("a",             models.PositiveSmallIntegerField()),
                ("b",             models.PositiveSmallIntegerField()),
                ("seen",          models.PositiveIntegerField(default=0)),
                ("correct",       models.PositiveIntegerField(default=0)),
                ("total_time_ms", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Fact Memory",
                "verbose_name_plural": "Fact Memory",
            },
        ),
        migrations.AddConstraint(
            model_name="factmemory",
            constraint=models.UniqueConstraint(fields=["user", "a", "b"], name="unique_user_fact"),
        ),

        # ── TRAINING SESSION ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="TrainingSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="training_sessions", to=settings.AUTH_USER_MODEL)),
                ("belt_id",   models.CharField(choices=[("white","White Belt"),("yellow","Yellow Belt"),("blue","Blue Belt"),("red","Red Belt"),("black","Black Belt"),("brown","Brown Belt"),("purple","Purple Belt"),("gold","Gold Belt"),("master","Master Belt")], max_length=10)),
                ("passed",    models.BooleanField(default=False)),
                ("accuracy",  models.FloatField(default=0.0)),
                ("time_used", models.PositiveIntegerField(default=0)),
                ("correct",   models.PositiveIntegerField(default=0)),
                ("total_q",   models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Training Session",
                "verbose_name_plural": "Training Sessions",
                "ordering": ["-created_at"],
            },
        ),

        # ── USER BADGE ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="UserBadge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="badges", to=settings.AUTH_USER_MODEL)),
                ("badge_id",  models.CharField(max_length=30)),
                ("earned_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "User Badge",
                "verbose_name_plural": "User Badges",
                "ordering": ["earned_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="userbadge",
            constraint=models.UniqueConstraint(fields=["user", "badge_id"], name="unique_user_badge"),
        ),

        # ── STREAK ────────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Streak",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="streak", to=settings.AUTH_USER_MODEL)),
                ("count",     models.PositiveIntegerField(default=0)),
                ("last_date", models.DateField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Streak",
                "verbose_name_plural": "Streaks",
            },
        ),

        # ── TUTOR REQUEST ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="TutorRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tutor_requests_sent",     to=settings.AUTH_USER_MODEL)),
                ("tutor",   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tutor_requests_received", to=settings.AUTH_USER_MODEL)),
                ("status",     models.CharField(choices=[("pending","Pending"),("accepted","Accepted"),("rejected","Rejected")], default="pending", max_length=10, db_index=True)),
                ("message",    models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tutor Request",
                "verbose_name_plural": "Tutor Requests",
                "ordering": ["-created_at"],
            },
        ),
    ]
