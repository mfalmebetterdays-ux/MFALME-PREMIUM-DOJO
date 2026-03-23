"""
dojo/admin.py
-------------
Registers all models with Django's built-in admin (at /django-admin/).
This exists as a safety net for superusers — the real custom admin
dashboard lives at /admin/ and is served by AdminAppView.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, BeltProgress, FactMemory,
    TrainingSession, UserBadge, Streak, TutorRequest,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ["email", "get_full_name", "role", "county", "school", "is_paid", "is_active", "date_joined"]
    list_filter   = ["role", "is_paid", "is_active", "county"]
    search_fields = ["email", "first_name", "last_name", "school"]
    ordering      = ["-date_joined"]

    # Add our custom fields to the fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Dojo Profile", {
            "fields": ("role", "county", "school", "spec", "is_paid"),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Dojo Profile", {
            "fields": ("role", "county", "school", "spec", "is_paid"),
        }),
    )


@admin.register(BeltProgress)
class BeltProgressAdmin(admin.ModelAdmin):
    list_display  = ["user", "belt_id", "status", "passed", "attempts", "best_acc", "updated_at"]
    list_filter   = ["belt_id", "status", "passed"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    raw_id_fields = ["user"]


@admin.register(FactMemory)
class FactMemoryAdmin(admin.ModelAdmin):
    list_display  = ["user", "a", "b", "seen", "correct", "accuracy_pct", "avg_time_ms"]
    list_filter   = ["a"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]

    @admin.display(description="Accuracy %")
    def accuracy_pct(self, obj):
        return f"{obj.accuracy_pct}%"

    @admin.display(description="Avg Time (ms)")
    def avg_time_ms(self, obj):
        return round(obj.avg_time_ms)


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display  = ["user", "belt_id", "passed", "accuracy_pct", "time_display", "correct", "total_q", "created_at"]
    list_filter   = ["belt_id", "passed"]
    search_fields = ["user__email", "user__first_name"]
    raw_id_fields = ["user"]

    @admin.display(description="Accuracy %")
    def accuracy_pct(self, obj):
        return f"{obj.accuracy_pct}%"

    @admin.display(description="Time Used")
    def time_display(self, obj):
        return obj.time_display


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display  = ["user", "badge_id", "earned_at"]
    list_filter   = ["badge_id"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]


@admin.register(Streak)
class StreakAdmin(admin.ModelAdmin):
    list_display  = ["user", "count", "last_date"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]


@admin.register(TutorRequest)
class TutorRequestAdmin(admin.ModelAdmin):
    list_display  = ["student", "tutor", "status", "created_at"]
    list_filter   = ["status"]
    search_fields = ["student__email", "tutor__email"]
    raw_id_fields = ["student", "tutor"]
