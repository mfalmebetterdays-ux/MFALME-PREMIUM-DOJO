"""
dojo/models.py
--------------
All database models for TimesTable Dojo.

Model hierarchy:
  User  (extends AbstractUser — so we get auth, permissions, is_staff for free)
    ├── BeltProgress   (one per belt per user — 9 rows created on register)
    ├── FactMemory     (one per multiplication fact per user — up to 400 rows)
    ├── TrainingSession (one per completed game session)
    ├── UserBadge      (junction: user × badge)
    ├── Streak         (one row per user, updated daily)
    └── TutorRequest   (student → tutor connection request)

Run after changes:
    python manage.py makemigrations
    python manage.py migrate
"""

import json
from datetime import date, timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — belt ordering used across the whole codebase
# ─────────────────────────────────────────────────────────────────────────────
BELT_CHOICES = [
    ("white",  "White Belt"),
    ("yellow", "Yellow Belt"),
    ("blue",   "Blue Belt"),
    ("red",    "Red Belt"),
    ("black",  "Black Belt"),
    ("brown",  "Brown Belt"),
    ("purple", "Purple Belt"),
    ("gold",   "Gold Belt"),
    ("master", "Master Belt"),
]

BELT_ORDER = [b[0] for b in BELT_CHOICES]   # ['white', 'yellow', ...]

# Belt details including tables and time limits
BELT_DETAILS = {
    "white":  {"tables": [2, 5, 10, 11], "minutes": 5, "emoji": "⬜", "color": "#d0d0d0", "textColor": "#1a2638"},
    "yellow": {"tables": [2, 3, 4, 5, 10, 11], "minutes": 7, "emoji": "🟡", "color": "#f9a825", "textColor": "#1a2638"},
    "blue":   {"tables": [2, 3, 4, 5, 6, 7, 10, 11], "minutes": 9, "emoji": "🔵", "color": "#1565c0", "textColor": "#ffffff"},
    "red":    {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11], "minutes": 11, "emoji": "🔴", "color": "#c62828", "textColor": "#ffffff"},
    "black":  {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], "minutes": 13, "emoji": "⚫", "color": "#1a1a1a", "textColor": "#ffffff"},
    "brown":  {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], "minutes": 15, "emoji": "🟤", "color": "#4e342e", "textColor": "#ffffff"},
    "purple": {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17], "minutes": 17, "emoji": "🟣", "color": "#6a1b9a", "textColor": "#ffffff"},
    "gold":   {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], "minutes": 19, "emoji": "🏅", "color": "#b8860b", "textColor": "#ffffff"},
    "master": {"tables": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], "minutes": 21, "emoji": "👑", "color": "#1a237e", "textColor": "#ffffff"},
}

ROLE_CHOICES = [
    ("student", "Student"),
    ("tutor",   "Tutor"),
    ("admin",   "Admin"),
]

TUTOR_SPEC_CHOICES = [
    ("primary", "Primary (Grades 1–4)"),
    ("junior",  "Junior (Grades 5–7)"),
    ("senior",  "Senior (Grades 8–10)"),
    ("all",     "All Levels"),
]


# ─────────────────────────────────────────────────────────────────────────────
# USER — extends Django's AbstractUser
# ─────────────────────────────────────────────────────────────────────────────
class User(AbstractUser):
    """
    Custom user model. We extend AbstractUser to keep all auth machinery.
    """

    role    = models.CharField(max_length=10, choices=ROLE_CHOICES, default="student", db_index=True)
    county  = models.CharField(max_length=100, blank=True)
    school  = models.CharField(max_length=200, blank=True)
    spec    = models.CharField(max_length=20, choices=TUTOR_SPEC_CHOICES, blank=True)
    is_paid = models.BooleanField(default=False, db_index=True)
    
    # NEW FIELD: Track current belt index for quick access
    current_belt_idx = models.IntegerField(default=0, db_index=True)
    
    # Trial tracking
    trial_used = models.BooleanField(default=False)
    trial_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def get_current_belt_idx(self):
        """Get the index of the current active belt (next belt to train)"""
        # If we have a stored value, use it
        if hasattr(self, '_current_belt_idx_cache'):
            return self._current_belt_idx_cache
        
        # Otherwise calculate from passed belts
        passed = self.belt_progress.filter(passed=True).values_list("belt_id", flat=True)
        passed_set = set(passed)
        
        for idx, belt_id in enumerate(BELT_ORDER):
            if belt_id not in passed_set:
                self._current_belt_idx_cache = idx
                # Update stored field
                if self.current_belt_idx != idx:
                    self.current_belt_idx = idx
                    self.save(update_fields=['current_belt_idx'])
                return idx
        
        # All belts passed
        idx = len(BELT_ORDER) - 1
        self._current_belt_idx_cache = idx
        if self.current_belt_idx != idx:
            self.current_belt_idx = idx
            self.save(update_fields=['current_belt_idx'])
        return idx

    def update_current_belt(self):
        """Update the current belt index based on passed belts"""
        passed = self.belt_progress.filter(passed=True).values_list("belt_id", flat=True)
        passed_set = set(passed)
        
        for idx, belt_id in enumerate(BELT_ORDER):
            if belt_id not in passed_set:
                self.current_belt_idx = idx
                self.save(update_fields=['current_belt_idx'])
                return idx
        
        self.current_belt_idx = len(BELT_ORDER) - 1
        self.save(update_fields=['current_belt_idx'])
        return len(BELT_ORDER) - 1

    @property
    def active_belt_id(self):
        """Get the ID of the current active belt"""
        idx = self.get_current_belt_idx()
        return BELT_ORDER[idx] if idx < len(BELT_ORDER) else BELT_ORDER[-1]
    
    @property
    def active_belt_details(self):
        """Get details of the active belt"""
        return BELT_DETAILS.get(self.active_belt_id, BELT_DETAILS["white"])

    def get_leaderboard_score(self):
        return self.training_sessions.aggregate(
            total=models.Sum("correct")
        )["total"] or 0
    
    def get_total_correct(self):
        return self.training_sessions.aggregate(
            total=models.Sum("correct")
        )["total"] or 0
    
    def get_total_questions(self):
        return self.training_sessions.aggregate(
            total=models.Sum("total_q")
        )["total"] or 0
    
    def get_avg_accuracy(self):
        return self.training_sessions.aggregate(
            avg=models.Avg("accuracy")
        )["avg"] or 0
    
    # =========================================================================
    # SUBSCRIPTION METHODS
    # =========================================================================
    
    def get_subscription(self):
        """Get or create user subscription"""
        subscription, created = PaymentSubscription.objects.get_or_create(
            user=self,
            defaults={
                'status': 'trial',
                'start_date': timezone.now(),
                'trial_ends': timezone.now() + timedelta(days=7)
            }
        )
        return subscription
    
    def has_active_subscription(self):
        """Check if user has active paid subscription"""
        subscription = self.get_subscription()
        return subscription.is_active() and subscription.status == 'active'
    
    def is_in_trial(self):
        """Check if user is in trial period"""
        subscription = self.get_subscription()
        return subscription.status == 'trial' and subscription.is_active()
    
    def can_access_belt(self, belt_id):
        """Check if user can access a specific belt"""
        # White belt is always free
        if belt_id == 'white':
            return True
        
        # Check subscription status for higher belts
        subscription = self.get_subscription()
        return subscription.is_active()


# ─────────────────────────────────────────────────────────────────────────────
# BELT PROGRESS
# ─────────────────────────────────────────────────────────────────────────────
class BeltProgress(models.Model):
    """
    One row per (user, belt) pair — 9 rows created automatically on student registration.
    """

    STATUS_CHOICES = [
        ("locked", "Locked"),
        ("active", "Active"),
        ("passed", "Passed"),
    ]

    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name="belt_progress")
    belt_id     = models.CharField(max_length=10, choices=BELT_CHOICES, db_index=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default="locked")
    passed      = models.BooleanField(default=False)
    attempts    = models.PositiveIntegerField(default=0)
    best_acc    = models.FloatField(default=0.0)
    levels_done = models.JSONField(default=list)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "belt_id")]
        ordering = ["user", models.Case(
            *[models.When(belt_id=bid, then=i) for i, bid in enumerate(BELT_ORDER)],
            output_field=models.IntegerField()
        )]
        verbose_name = "Belt Progress"
        verbose_name_plural = "Belt Progress"

    def __str__(self):
        return f"{self.user.display_name} — {self.get_belt_id_display()} ({self.status})"

    @property
    def belt_index(self):
        return BELT_ORDER.index(self.belt_id) if self.belt_id in BELT_ORDER else 0
    
    @property
    def belt_details(self):
        return BELT_DETAILS.get(self.belt_id, BELT_DETAILS["white"])
    
    @property
    def tables_cleared_count(self):
        return len(self.levels_done)
    
    @property
    def tables_total_count(self):
        return len(self.belt_details["tables"])
    
    @property
    def progress_percentage(self):
        if self.tables_total_count == 0:
            return 0
        return (self.tables_cleared_count / self.tables_total_count) * 100
    
    def add_level_done(self, table):
        if table not in self.levels_done:
            self.levels_done.append(table)
            self.save()
            return True
        return False
    
    def is_level_complete(self, table):
        return table in self.levels_done
    
    def mark_passed(self):
        """Mark this belt as passed and unlock next belt"""
        self.passed = True
        self.status = "passed"
        self.save()
        
        # Update user's current belt
        self.user.update_current_belt()
        
        # Unlock next belt
        idx = self.belt_index
        if idx + 1 < len(BELT_ORDER):
            next_id = BELT_ORDER[idx + 1]
            next_belt, _ = BeltProgress.objects.get_or_create(
                user=self.user, belt_id=next_id,
                defaults={"status": "locked"}
            )
            if next_belt.status == "locked":
                next_belt.status = "active"
                next_belt.save()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# FACT MEMORY
# ─────────────────────────────────────────────────────────────────────────────
class FactMemory(models.Model):
    """
    Tracks a user's history with every individual multiplication fact.
    """

    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fact_memory")
    a             = models.PositiveSmallIntegerField()
    b             = models.PositiveSmallIntegerField()
    seen          = models.PositiveIntegerField(default=0)
    correct       = models.PositiveIntegerField(default=0)
    total_time_ms = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = [("user", "a", "b")]
        verbose_name = "Fact Memory"
        verbose_name_plural = "Fact Memory"
        indexes = [
            models.Index(fields=["user", "a", "b"]),
            models.Index(fields=["user", "seen"]),
        ]

    def __str__(self):
        return f"{self.user.display_name}: {self.a}×{self.b} ({self.accuracy_pct}%)"

    @property
    def accuracy(self):
        return self.correct / self.seen if self.seen else 0.0

    @property
    def accuracy_pct(self):
        return round(self.accuracy * 100)

    @property
    def avg_time_ms(self):
        return self.total_time_ms / self.seen if self.seen else 0

    @property
    def avg_time_seconds(self):
        return self.avg_time_ms / 1000 if self.seen else 0

    @property
    def performance_class(self):
        if not self.seen:
            return "unseen"
        if self.accuracy < 0.5:
            return "weak"
        if self.accuracy < 0.8:
            return "slow"
        if self.avg_time_ms > 8000:
            return "good"
        return "fast"
    
    def add_attempt(self, correct_answer, time_ms):
        self.seen += 1
        if correct_answer:
            self.correct += 1
        self.total_time_ms += time_ms
        self.save()


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING SESSION
# ─────────────────────────────────────────────────────────────────────────────
class TrainingSession(models.Model):
    """
    One row per completed training session.
    """

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="training_sessions")
    belt_id    = models.CharField(max_length=10, choices=BELT_CHOICES)
    passed     = models.BooleanField(default=False)
    accuracy   = models.FloatField(default=0.0)
    time_used  = models.PositiveIntegerField(default=0)
    correct    = models.PositiveIntegerField(default=0)
    total_q    = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Training Session"
        verbose_name_plural = "Training Sessions"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["belt_id", "created_at"]),
        ]

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{self.user.display_name} — {self.get_belt_id_display()} [{status}] {self.accuracy_pct}%"

    @property
    def accuracy_pct(self):
        return round(self.accuracy * 100)

    @property
    def time_display(self):
        m, s = divmod(self.time_used, 60)
        return f"{m}:{s:02d}"
    
    @property
    def belt_details(self):
        return BELT_DETAILS.get(self.belt_id, BELT_DETAILS["white"])


# ─────────────────────────────────────────────────────────────────────────────
# BADGE
# ─────────────────────────────────────────────────────────────────────────────
BADGE_CHOICES = [
    ("first_correct", "First Correct"),
    ("white_belt",    "White Belt"),
    ("yellow_belt",   "Yellow Belt"),
    ("blue_belt",     "Blue Belt"),
    ("red_belt",      "Red Belt"),
    ("black_belt",    "Black Belt"),
    ("brown_belt",    "Brown Belt"),
    ("purple_belt",   "Purple Belt"),
    ("gold_belt",     "Gold Belt"),
    ("master_belt",   "Master Belt"),
    ("perfect_belt",  "Perfect Run"),
    ("speed_run",     "Speed Run"),
    ("streak_7",      "Week Warrior"),
    ("century",       "Century"),
]

BADGE_DETAILS = {
    "first_correct": {"name": "First Correct", "icon": "✓", "color": "#1976d2", "desc": "First correct answer"},
    "white_belt":    {"name": "White Belt", "icon": "⬜", "color": "#9e9e9e", "desc": "Passed White Belt"},
    "yellow_belt":   {"name": "Yellow Belt", "icon": "🟡", "color": "#f9a825", "desc": "Passed Yellow Belt"},
    "blue_belt":     {"name": "Blue Belt", "icon": "🔵", "color": "#1565c0", "desc": "Passed Blue Belt"},
    "red_belt":      {"name": "Red Belt", "icon": "🔴", "color": "#c62828", "desc": "Passed Red Belt"},
    "black_belt":    {"name": "Black Belt", "icon": "⚫", "color": "#333", "desc": "Passed Black Belt"},
    "brown_belt":    {"name": "Brown Belt", "icon": "🟤", "color": "#4e342e", "desc": "Passed Brown Belt"},
    "purple_belt":   {"name": "Purple Belt", "icon": "🟣", "color": "#6a1b9a", "desc": "Passed Purple Belt"},
    "gold_belt":     {"name": "Gold Belt", "icon": "🏅", "color": "#b8860b", "desc": "Passed Gold Belt"},
    "master_belt":   {"name": "Master Belt", "icon": "👑", "color": "#1a237e", "desc": "Achieved Master Belt"},
    "perfect_belt":  {"name": "Perfect Run", "icon": "💯", "color": "#00b248", "desc": "100% accuracy in a belt"},
    "speed_run":     {"name": "Speed Run", "icon": "⚡", "color": "#f57f17", "desc": "Belt done with 2+ mins left"},
    "streak_7":      {"name": "Week Warrior", "icon": "🔥", "color": "#0288d1", "desc": "7-day training streak"},
    "century":       {"name": "Century", "icon": "💪", "color": "#4e342e", "desc": "100 correct answers"},
}

class UserBadge(models.Model):
    """Junction table for badges earned by users."""

    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="badges")
    badge_id  = models.CharField(max_length=30, choices=BADGE_CHOICES)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "badge_id")]
        ordering = ["earned_at"]
        verbose_name = "User Badge"
        verbose_name_plural = "User Badges"
        indexes = [
            models.Index(fields=["user", "badge_id"]),
        ]

    def __str__(self):
        return f"{self.user.display_name} — {self.get_badge_id_display()}"
    
    @property
    def details(self):
        return BADGE_DETAILS.get(self.badge_id, {"name": self.get_badge_id_display(), "icon": "🏆", "color": "#888", "desc": ""})


# ─────────────────────────────────────────────────────────────────────────────
# STREAK
# ─────────────────────────────────────────────────────────────────────────────
class Streak(models.Model):
    """
    Tracks daily training streaks for students.
    """

    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name="streak")
    count     = models.PositiveIntegerField(default=0)
    last_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Streak"
        verbose_name_plural = "Streaks"

    def __str__(self):
        return f"{self.user.display_name} — {self.count} days"

    def update(self):
        """Call after a student completes any session."""
        today = date.today()
        if self.last_date == today:
            return self.count
        yesterday = today - timedelta(days=1)
        if self.last_date == yesterday:
            self.count += 1
        else:
            self.count = 1
        self.last_date = today
        self.save(update_fields=["count", "last_date"])
        return self.count
    
    def reset(self):
        self.count = 0
        self.last_date = None
        self.save()
    
    @property
    def is_active(self):
        if not self.last_date:
            return False
        today = date.today()
        return self.last_date >= today - timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# TUTOR REQUEST
# ─────────────────────────────────────────────────────────────────────────────
class TutorRequest(models.Model):
    """
    A student requests coaching from a tutor.
    """

    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]

    student    = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tutor_requests_sent")
    tutor      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tutor_requests_received")
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)
    message    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tutor Request"
        verbose_name_plural = "Tutor Requests"
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["tutor", "status"]),
        ]

    def __str__(self):
        return f"{self.student.display_name} → {self.tutor.display_name} ({self.status})"
    
    def accept(self):
        self.status = "accepted"
        self.save()
    
    def reject(self):
        self.status = "rejected"
        self.save()
    
    @property
    def is_pending(self):
        return self.status == "pending"
    
    @property
    def is_accepted(self):
        return self.status == "accepted"
    
    @property
    def is_rejected(self):
        return self.status == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────
class Assignment(models.Model):
    """Test/Assignment created by tutor for student(s)."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    tutor       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments_created')
    student     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments_received', null=True, blank=True)
    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    questions   = models.JSONField(default=list)
    time_limit  = models.PositiveIntegerField(default=0, help_text="Time limit in minutes, 0 for no limit")
    points      = models.PositiveIntegerField(default=100)
    due_date    = models.DateTimeField(null=True, blank=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tutor', 'status']),
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.tutor.display_name} → {self.student.display_name if self.student else 'All'}"


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT SUBMISSION
# ─────────────────────────────────────────────────────────────────────────────
class AssignmentSubmission(models.Model):
    """Student's submission for an assignment."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('late', 'Late'),
    ]
    
    assignment   = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    answers      = models.JSONField(default=list)
    score        = models.PositiveIntegerField(default=0)
    feedback     = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    started_at   = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at    = models.DateTimeField(null=True, blank=True)
    is_read      = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = [('assignment', 'student')]
    
    def __str__(self):
        return f"{self.assignment.title} - {self.student.display_name} ({self.score})"
    
    @property
    def is_late(self):
        if self.assignment.due_date and self.submitted_at:
            return self.submitted_at > self.assignment.due_date
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHAT MESSAGE
# ─────────────────────────────────────────────────────────────────────────────
class ChatMessage(models.Model):
    """Chat messages between tutor and student with file attachment support."""

    sender    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    message   = models.TextField()
    is_read   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # File attachment fields
    attachment = models.FileField(upload_to='chat_attachments/%Y/%m/%d/', null=True, blank=True)
    attachment_name = models.CharField(max_length=255, blank=True)
    attachment_size = models.PositiveIntegerField(default=0)
    attachment_type = models.CharField(max_length=50, blank=True)  # image, pdf, video, file
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.sender.display_name} → {self.recipient.display_name}: {self.message[:50]}"
    
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save()


# ─────────────────────────────────────────────────────────────────────────────
# NOTE
# ─────────────────────────────────────────────────────────────────────────────
class Note(models.Model):
    """Notes/feedback from tutor to student."""

    tutor     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes_written')
    student   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes_received')
    content   = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note from {self.tutor.display_name} to {self.student.display_name}"


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT SUBSCRIPTION
# ─────────────────────────────────────────────────────────────────────────────
class PaymentSubscription(models.Model):
    """Track user subscriptions with enhanced trial management"""
    PLAN_CHOICES = [
        ('monthly', 'Monthly'),
        ('half_yearly', '6 Months'),
        ('yearly', 'Yearly'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('trial', 'Trial'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='monthly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    trial_ends = models.DateTimeField(null=True, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
    paystack_access_code = models.CharField(max_length=100, blank=True)
    paystack_customer_code = models.CharField(max_length=100, blank=True)
    paystack_subscription_code = models.CharField(max_length=100, blank=True)
    last_payment_date = models.DateTimeField(null=True, blank=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    cancel_at_period_end = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Payment Subscription"
        verbose_name_plural = "Payment Subscriptions"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['trial_ends']),
            models.Index(fields=['end_date']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.plan} - {self.status}"
    
    def is_active(self):
        """Check if subscription is currently active"""
        if self.status == 'trial':
            if not self.trial_ends:
                from django.utils import timezone
                self.trial_ends = self.start_date + timedelta(days=7)
                self.save(update_fields=['trial_ends'])
                return True
            from django.utils import timezone
            return timezone.now() < self.trial_ends
        if self.status == 'active':
            if not self.end_date:
                return False
            from django.utils import timezone
            return timezone.now() < self.end_date
        return False
    
    def has_active_access(self):
        """Check if user has ANY active access (trial or paid)"""
        return self.is_active()
    
    def days_remaining(self):
        """Get days remaining in trial or subscription"""
        from django.utils import timezone
        
        if self.status == 'trial' and self.trial_ends:
            return (self.trial_ends - timezone.now()).days
        
        if self.status == 'active' and self.end_date:
            return (self.end_date - timezone.now()).days
        
        return 0
    
    def get_status_display_text(self):
        """Get human-readable status with days remaining"""
        if self.status == 'trial' and self.is_active():
            days = self.days_remaining()
            return f"🎁 Trial Active - {days} days remaining"
        
        if self.status == 'active' and self.is_active():
            days = self.days_remaining()
            return f"✅ Premium Active - {days} days remaining"
        
        if self.status == 'expired':
            return "⏰ Subscription Expired - Upgrade to continue"
        
        if self.status == 'cancelled':
            return "❌ Subscription Cancelled - Renew to access"
        
        return "⚠️ Free Tier - Only White Belt Available"


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT TRANSACTION
# ─────────────────────────────────────────────────────────────────────────────
class PaymentTransaction(models.Model):
    """Track all payment transactions with enhanced fields"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    TRANSACTION_TYPE_CHOICES = [
        ('initial', 'Initial Payment'),
        ('renewal', 'Renewal'),
        ('upgrade', 'Upgrade'),
        ('refund', 'Refund'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default='initial')
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    access_code = models.CharField(max_length=100)
    authorization_code = models.CharField(max_length=100, blank=True)
    paystack_customer_code = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    plan = models.CharField(max_length=20, choices=PaymentSubscription.PLAN_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    subscription_code = models.CharField(max_length=100, blank=True)
    paystack_response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['reference']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.reference} - {self.status}"


# ─────────────────────────────────────────────────────────────────────────────
# TUTOR INTEREST
# ─────────────────────────────────────────────────────────────────────────────
class TutorInterest(models.Model):
    """Stores emails from users interested in tutor features (coming soon)"""
    email = models.EmailField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tutor Interest"
        verbose_name_plural = "Tutor Interests"
    
    def __str__(self):
        return f"{self.email} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


# ─────────────────────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create initial belt progress, streak, and subscription when a new student registers."""
    if created and instance.role == "student":
        # Create belt progress
        for i, belt_id in enumerate(BELT_ORDER):
            status = "active" if i == 0 else "locked"
            BeltProgress.objects.create(
                user=instance,
                belt_id=belt_id,
                status=status,
                passed=False,
                attempts=0,
                best_acc=0,
                levels_done=[]
            )
        # Create streak
        Streak.objects.create(user=instance, count=0, last_date=None)
        
        # Create subscription with 7-day trial
        from django.utils import timezone
        PaymentSubscription.objects.create(
            user=instance,
            status='trial',
            start_date=timezone.now(),
            trial_ends=timezone.now() + timedelta(days=7)
        )


@receiver(post_save, sender=TrainingSession)
def update_streak_on_session(sender, instance, created, **kwargs):
    """Update streak when a new training session is created."""
    if created:
        streak, _ = Streak.objects.get_or_create(user=instance.user)
        streak.update()