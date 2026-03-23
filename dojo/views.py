"""
All views for TimesTable Dojo.
"""

import json
import logging
import requests
import mimetypes
import time
import hashlib
from datetime import date, timedelta
from functools import wraps
from decimal import Decimal
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    BELT_ORDER,
    BELT_DETAILS,
    BELT_CHOICES,
    BeltProgress,
    FactMemory,
    Streak,
    TrainingSession,
    TutorRequest,
    User,
    UserBadge,
    Assignment,
    AssignmentSubmission,
    ChatMessage,
    Note,
    PaymentSubscription, 
    PaymentTransaction,   
    TutorInterest,
)

logger = logging.getLogger("dojo")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def json_body(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def ok(data=None, **kwargs):
    payload = {"ok": True}
    if data:
        payload.update(data)
    payload.update(kwargs)
    return JsonResponse(payload)


def err(message, status=400):
    return JsonResponse({"error": message}, status=status)


def user_json(user):
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "county": user.county,
        "school": user.school,
        "spec": user.spec,
        "is_paid": user.is_paid,
        "date_joined": user.date_joined.isoformat(),
    }


def belt_progress_json(bp_qs):
    result = {}
    for bp in bp_qs:
        result[bp.belt_id] = {
            "belt_id": bp.belt_id,
            "status": bp.status,
            "passed": bp.passed,
            "attempts": bp.attempts,
            "best_acc": bp.best_acc,
            "levels_done": bp.levels_done,
        }
    return result


def require_role(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return err("Unauthorized", 401)
            if request.user.role not in roles:
                return err("Forbidden", 403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def admin_only(view_func):
    return require_role("admin")(view_func)


def award_badge_if_new(user, badge_id):
    badge, created = UserBadge.objects.get_or_create(user=user, badge_id=badge_id)
    return created


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_unread_notifications_count(request):
    """Get count of unread notifications for student"""
    user = request.user
    unread_chats = ChatMessage.objects.filter(recipient=user, is_read=False).count()
    return ok(count=unread_chats)


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_student_assignments(request):
    """Get assignments for the logged-in student"""
    user = request.user
    assignments = Assignment.objects.filter(
        Q(student=user) | Q(student__isnull=True),
        status='published'
    ).select_related('tutor').order_by('-created_at')
    
    data = []
    for a in assignments:
        submission = AssignmentSubmission.objects.filter(assignment=a, student=user).first()
        data.append({
            'id': a.id,
            'title': a.title,
            'description': a.description,
            'tutor_name': a.tutor.get_full_name(),
            'tutor_id': a.tutor.id,
            'time_limit': a.time_limit,
            'points': a.points,
            'due_date': a.due_date.isoformat() if a.due_date else None,
            'questions': a.questions,
            'questions_count': len(a.questions),
            'submission': {
                'status': submission.status if submission else 'pending',
                'score': submission.score if submission else 0,
                'submitted_at': submission.submitted_at.isoformat() if submission and submission.submitted_at else None,
                'feedback': submission.feedback if submission else '',
            } if submission else None,
            'created_at': a.created_at.isoformat(),
        })
    
    return ok(assignments=data)


@require_GET
@require_role("student")
def api_student_assignment_detail(request, assignment_id):
    """Get single assignment details for student"""
    user = request.user
    try:
        assignment = Assignment.objects.get(
            Q(id=assignment_id),
            Q(student=user) | Q(student__isnull=True),
            status='published'
        )
    except Assignment.DoesNotExist:
        return err("Assignment not found", 404)
    
    submission = AssignmentSubmission.objects.filter(assignment=assignment, student=user).first()
    
    return ok(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        tutor_name=assignment.tutor.get_full_name(),
        tutor_id=assignment.tutor.id,
        time_limit=assignment.time_limit,
        points=assignment.points,
        due_date=assignment.due_date.isoformat() if assignment.due_date else None,
        questions=assignment.questions,
        submission={
            'id': submission.id if submission else None,
            'status': submission.status if submission else 'pending',
            'answers': submission.answers if submission else [],
            'score': submission.score if submission else 0,
            'feedback': submission.feedback if submission else '',
            'submitted_at': submission.submitted_at.isoformat() if submission and submission.submitted_at else None,
        } if submission else None,
    )


@csrf_exempt
@require_POST
@require_role("student")
def api_student_submit_assignment(request, assignment_id):
    """Submit answers for an assignment"""
    user = request.user
    data = json_body(request)
    
    try:
        assignment = Assignment.objects.get(
            Q(id=assignment_id),
            Q(student=user) | Q(student__isnull=True),
            status='published'
        )
    except Assignment.DoesNotExist:
        return err("Assignment not found", 404)
    
    # Check if already submitted
    existing = AssignmentSubmission.objects.filter(assignment=assignment, student=user).first()
    if existing and existing.status in ['submitted', 'graded']:
        return err("You have already submitted this assignment", 400)
    
    answers = data.get('answers', [])
    # Auto-grade if assignment has correct answers
    total_points = 0
    graded_answers = []
    for i, q in enumerate(assignment.questions):
        user_answer = answers[i] if i < len(answers) else ''
        correct_answer = q.get('correct_answer', '')
        is_correct = str(user_answer).strip().lower() == str(correct_answer).strip().lower() if correct_answer else False
        points_earned = q.get('points', assignment.points // len(assignment.questions)) if is_correct else 0
        total_points += points_earned
        graded_answers.append({
            'question_id': i,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'points_earned': points_earned,
            'max_points': q.get('points', assignment.points // len(assignment.questions))
        })
    
    submission, created = AssignmentSubmission.objects.update_or_create(
        assignment=assignment,
        student=user,
        defaults={
            'answers': graded_answers,
            'score': total_points,
            'status': 'submitted',
            'submitted_at': timezone.now(),
        }
    )
    
    return ok(
        submission_id=submission.id,
        score=total_points,
        total_points=assignment.points,
        answers=graded_answers
    )


@require_GET
@require_role("tutor")
def api_tutor_assignments(request):
    """Get assignments created by tutor"""
    user = request.user
    assignments = Assignment.objects.filter(tutor=user).select_related('student').order_by('-created_at')
    
    data = []
    for a in assignments:
        submission_count = AssignmentSubmission.objects.filter(assignment=a).count()
        completed_count = AssignmentSubmission.objects.filter(assignment=a, status='graded').count()
        data.append({
            'id': a.id,
            'title': a.title,
            'student_name': a.student.get_full_name() if a.student else 'All Students',
            'student_id': a.student.id if a.student else None,
            'description': a.description,
            'questions_count': len(a.questions),
            'points': a.points,
            'due_date': a.due_date.isoformat() if a.due_date else None,
            'status': a.status,
            'submissions_count': submission_count,
            'completed_count': completed_count,
            'created_at': a.created_at.isoformat(),
        })
    
    return ok(assignments=data)


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_create_assignment(request):
    """Create a new assignment"""
    data = json_body(request)
    user = request.user
    
    assignment = Assignment.objects.create(
        tutor=user,
        student_id=data.get('student_id') if data.get('student_id') else None,
        title=data.get('title', 'Untitled Assignment'),
        description=data.get('description', ''),
        questions=data.get('questions', []),
        time_limit=data.get('time_limit', 0),
        points=data.get('points', 100),
        due_date=data.get('due_date'),
        status=data.get('status', 'published'),
    )
    
    return ok(assignment_id=assignment.id, title=assignment.title)


@require_GET
@require_role("tutor")
def api_tutor_submissions(request, assignment_id):
    """Get all submissions for an assignment"""
    try:
        assignment = Assignment.objects.get(id=assignment_id, tutor=request.user)
    except Assignment.DoesNotExist:
        return err("Assignment not found", 404)
    
    submissions = AssignmentSubmission.objects.filter(assignment=assignment).select_related('student')
    
    data = []
    for s in submissions:
        data.append({
            'id': s.id,
            'student_id': s.student.id,
            'student_name': s.student.get_full_name(),
            'score': s.score,
            'total_points': assignment.points,
            'answers': s.answers,
            'feedback': s.feedback,
            'status': s.status,
            'submitted_at': s.submitted_at.isoformat() if s.submitted_at else None,
        })
    
    return ok(submissions=data)


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_grade_submission(request, submission_id):
    """Grade a student's assignment submission"""
    data = json_body(request)
    
    try:
        submission = AssignmentSubmission.objects.select_related('assignment').get(id=submission_id)
        if submission.assignment.tutor != request.user:
            return err("Not your assignment", 403)
    except AssignmentSubmission.DoesNotExist:
        return err("Submission not found", 404)
    
    score = data.get('score', submission.score)
    feedback = data.get('feedback', '')
    answers = data.get('answers', submission.answers)
    
    submission.score = score
    submission.feedback = feedback
    submission.answers = answers
    submission.status = 'graded'
    submission.graded_at = timezone.now()
    submission.save()
    
    return ok(submission_id=submission.id, score=score)


# ─────────────────────────────────────────────────────────────────────────────
# CHAT API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_student_chat(request, tutor_id):
    """Get chat messages between student and tutor"""
    user = request.user
    messages = ChatMessage.objects.filter(
        (Q(sender=user, recipient_id=tutor_id) | Q(sender_id=tutor_id, recipient=user))
    ).order_by('created_at')
    
    # Mark messages as read
    ChatMessage.objects.filter(sender_id=tutor_id, recipient=user, is_read=False).update(is_read=True)
    
    data = []
    for m in messages:
        data.append({
            'id': m.id,
            'sender_id': m.sender.id,
            'sender_name': m.sender.get_full_name(),
            'message': m.message,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat(),
        })
    
    return ok(messages=data)


@require_GET
@require_role("tutor")
def api_tutor_chat(request, student_id):
    """Get chat messages between tutor and student"""
    user = request.user
    messages = ChatMessage.objects.filter(
        (Q(sender=user, recipient_id=student_id) | Q(sender_id=student_id, recipient=user))
    ).order_by('created_at')
    
    # Mark messages as read
    ChatMessage.objects.filter(sender_id=student_id, recipient=user, is_read=False).update(is_read=True)
    
    data = []
    for m in messages:
        data.append({
            'id': m.id,
            'sender_id': m.sender.id,
            'sender_name': m.sender.get_full_name(),
            'message': m.message,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat(),
        })
    
    return ok(messages=data)


@csrf_exempt
@require_POST
@require_role("student", "tutor")
def api_send_chat(request):
    """Send a chat message"""
    data = json_body(request)
    recipient_id = data.get('recipient_id')
    message = data.get('message', '').strip()
    
    if not message:
        return err("Message cannot be empty", 400)
    
    try:
        recipient = User.objects.get(id=recipient_id, is_active=True)
    except User.DoesNotExist:
        return err("Recipient not found", 404)
    
    chat = ChatMessage.objects.create(
        sender=request.user,
        recipient=recipient,
        message=message
    )
    
    return ok(
        id=chat.id,
        sender_id=chat.sender.id,
        message=chat.message,
        created_at=chat.created_at.isoformat()
    )


@require_GET
@require_role("tutor")
def api_tutor_chat_list(request):
    """Get list of students the tutor has chatted with"""
    user = request.user
    sent_to = ChatMessage.objects.filter(sender=user).values_list('recipient_id', flat=True)
    received_from = ChatMessage.objects.filter(recipient=user).values_list('sender_id', flat=True)
    student_ids = set(list(sent_to) + list(received_from))
    
    students = User.objects.filter(id__in=student_ids, role='student')
    data = []
    for s in students:
        last_msg = ChatMessage.objects.filter(
            Q(sender=user, recipient=s) | Q(sender=s, recipient=user)
        ).order_by('-created_at').first()
        
        unread_count = ChatMessage.objects.filter(sender=s, recipient=user, is_read=False).count()
        
        data.append({
            'id': s.id,
            'name': s.get_full_name(),
            'email': s.email,
            'last_message': last_msg.message[:50] if last_msg else '',
            'last_message_time': last_msg.created_at.isoformat() if last_msg else None,
            'unread_count': unread_count,
        })
    
    return ok(students=data)


@require_GET
@require_role("student")
def api_student_chat_list(request):
    """Get list of tutors the student has chatted with"""
    user = request.user
    sent_to = ChatMessage.objects.filter(sender=user).values_list('recipient_id', flat=True)
    received_from = ChatMessage.objects.filter(recipient=user).values_list('sender_id', flat=True)
    tutor_ids = set(list(sent_to) + list(received_from))
    
    tutors = User.objects.filter(id__in=tutor_ids, role='tutor')
    data = []
    for t in tutors:
        last_msg = ChatMessage.objects.filter(
            Q(sender=user, recipient=t) | Q(sender=t, recipient=user)
        ).order_by('-created_at').first()
        
        unread_count = ChatMessage.objects.filter(sender=t, recipient=user, is_read=False).count()
        
        data.append({
            'id': t.id,
            'name': t.get_full_name(),
            'email': t.email,
            'last_message': last_msg.message[:50] if last_msg else '',
            'last_message_time': last_msg.created_at.isoformat() if last_msg else None,
            'unread_count': unread_count,
        })
    
    return ok(tutors=data)


# ─────────────────────────────────────────────────────────────────────────────
# NOTES API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_student_notes(request):
    """Get notes for student from tutors"""
    user = request.user
    notes = Note.objects.filter(student=user).select_related('tutor').order_by('-created_at')
    
    data = []
    for n in notes:
        data.append({
            'id': n.id,
            'tutor_name': n.tutor.get_full_name(),
            'content': n.content,
            'created_at': n.created_at.isoformat(),
        })
    
    return ok(notes=data)


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_create_note(request):
    """Create a note for a student"""
    data = json_body(request)
    student_id = data.get('student_id')
    content = data.get('content', '').strip()
    
    if not content:
        return err("Note content cannot be empty", 400)
    
    try:
        student = User.objects.get(id=student_id, role='student')
    except User.DoesNotExist:
        return err("Student not found", 404)
    
    note = Note.objects.create(
        tutor=request.user,
        student=student,
        content=content
    )
    
    return ok(note_id=note.id)


@require_GET
@require_role("tutor")
def api_tutor_notes(request, student_id=None):
    """Get notes for a specific student or all students"""
    user = request.user
    notes = Note.objects.filter(tutor=user)
    if student_id:
        notes = notes.filter(student_id=student_id)
    notes = notes.select_related('student').order_by('-created_at')
    
    data = []
    for n in notes:
        data.append({
            'id': n.id,
            'student_id': n.student.id,
            'student_name': n.student.get_full_name(),
            'content': n.content,
            'created_at': n.created_at.isoformat(),
        })
    
    return ok(notes=data)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class HomeView(View):
    """Landing page view - always shows home page"""
    def get(self, request):
        return render(request, 'dojo/home.html')


class LoginView(View):
    """Login page view - always shows login form"""
    def get(self, request):
        return render(request, 'dojo/login.html')


class RegisterView(View):
    """Registration page view - always shows registration form"""
    def get(self, request):
        return render(request, 'dojo/register.html')


class StudentAppView(LoginRequiredMixin, View):
    """Student game dashboard"""
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        return render(request, "dojo/game.html")


class StudentPortalView(LoginRequiredMixin, View):
    """Student learning hub portal"""
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        return render(request, "dojo/student_portal.html")


class TutorDashboardView(LoginRequiredMixin, View):
    """Tutor dashboard view"""
    def get(self, request):
        if request.user.role != 'tutor':
            return redirect('dojo:home')
        return render(request, "dojo/tutor.html")


class AdminLoginView(View):
    """Admin login page"""
    def get(self, request):
        if request.user.is_authenticated and request.user.role == 'admin':
            return redirect('dojo:admin_dashboard')
        return render(request, 'dojo/admin_login.html')


class AdminDashboardView(LoginRequiredMixin, View):
    """Admin dashboard view"""
    def get(self, request):
        if request.user.role != 'admin':
            return redirect('dojo:home')
        return render(request, "dojo/admin_dashboard.html")


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("dojo:home")


class LegacyAdminAppView(View):
    """Legacy admin view - redirect to admin login"""
    def get(self, request):
        return redirect('dojo:admin_login')


# ─────────────────────────────────────────────────────────────────────────────
# AUTH API
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_register(request):
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    role = data.get("role", "student")
    county = data.get("county", "")
    school = data.get("school", "")
    spec = data.get("spec", "")

    if not email or not password or not first_name:
        return err("Email, password, and first name are required")
    if len(password) < 6:
        return err("Password must be at least 6 characters")
    if role not in ("student", "tutor"):
        return err("Invalid role")
    if User.objects.filter(email=email).exists():
        return err("Email already registered")

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                county=county,
                school=school,
                spec=spec,
            )
            
            # Create belt progress for students
            if role == "student":
                # Use get_or_create to avoid duplicates
                for i, belt_id in enumerate(BELT_ORDER):
                    status = "active" if i == 0 else "locked"
                    BeltProgress.objects.get_or_create(
                        user=user,
                        belt_id=belt_id,
                        defaults={
                            "status": status,
                            "passed": False,
                            "attempts": 0,
                            "best_acc": 0,
                            "levels_done": []
                        }
                    )
                
                Streak.objects.get_or_create(user=user, defaults={"count": 0, "last_date": None})
                
                # Create subscription with 7-day trial
                PaymentSubscription.objects.get_or_create(
                    user=user,
                    defaults={
                        'status': 'trial',
                        'start_date': timezone.now(),
                        'trial_ends': timezone.now() + timedelta(days=settings.TRIAL_DAYS)
                    }
                )
            
            login(request, user)
            logger.info("New %s registered: %s", role, email)
            return ok(user=user_json(user))
            
    except IntegrityError as e:
        logger.error(f"Integrity error during registration: {e}")
        return err("Registration failed due to duplicate data", 400)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return err(f"Registration failed: {str(e)}", 500)

@csrf_exempt
@require_POST
def api_login(request):
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role")

    if not email or not password:
        return err("Email and password required")

    user = authenticate(request, username=email, password=password)
    if not user:
        try:
            u = User.objects.get(email=email)
            user = authenticate(request, username=u.username, password=password)
        except User.DoesNotExist:
            pass

    if not user:
        return err("Invalid email or password", 401)
    if not user.is_active:
        return err("Account is suspended", 401)
    if role and user.role != role:
        return err(f"No {role} account found with these credentials", 401)

    login(request, user)
    return ok(user=user_json(user))


@csrf_exempt
@require_POST
def api_logout(request):
    logout(request)
    return ok()


@require_GET
def api_me(request):
    if not request.user.is_authenticated:
        return err("Unauthorized", 401)
    return ok(user=user_json(request.user))


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC STATS
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
def api_public_stats(request):
    try:
        total_students = User.objects.filter(role='student', is_active=True).count()
        total_belts = BeltProgress.objects.filter(passed=True).count()
        total_questions = TrainingSession.objects.aggregate(total=Sum('total_q'))['total'] or 0
        
        return JsonResponse({
            'total_students': total_students,
            'total_belts': total_belts,
            'total_questions': total_questions
        })
    except Exception as e:
        logger.error(f"Error loading public stats: {e}")
        return JsonResponse({
            'total_students': 1247,
            'total_belts': 3892,
            'total_questions': 45231
        })


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_student_profile(request):
    user = request.user
    bp = belt_progress_json(user.belt_progress.all())
    badges = list(user.badges.values_list("badge_id", flat=True))
    facts = {
        f"{fm.a}x{fm.b}": {
            "a": fm.a, "b": fm.b,
            "seen": fm.seen, "correct": fm.correct,
            "total_time": fm.total_time_ms,
            "avg_time": fm.avg_time_ms,
            "accuracy": fm.accuracy
        }
        for fm in user.fact_memory.all()
    }
    streak_obj, _ = Streak.objects.get_or_create(user=user)
    stats = user.training_sessions.aggregate(
        total_sessions=Count("id"),
        total_correct=Sum("correct"),
        total_questions=Sum("total_q"),
        avg_accuracy=Avg("accuracy"),
    )
    
    return ok(
        user=user_json(user),
        belts=bp,
        badges=badges,
        fact_memory=facts,
        streak=streak_obj.count,
        last_date=streak_obj.last_date.isoformat() if streak_obj.last_date else None,
        stats={
            "total_sessions": stats["total_sessions"] or 0,
            "total_correct": stats["total_correct"] or 0,
            "total_questions": stats["total_questions"] or 0,
            "avg_accuracy": stats["avg_accuracy"] or 0,
        },
        current_belt_idx=user.current_belt_idx,
        current_belt_id=user.active_belt_id,
    )


@require_GET
@require_role("student")
def api_student_belts(request):
    """Get belt progress for the current student"""
    bp = belt_progress_json(request.user.belt_progress.all())
    return ok(belts=bp)


@require_GET
@require_role("student")
def api_student_belt_progress(request):
    """Get detailed belt progress including belt details"""
    user = request.user
    belt_progress_data = []
    
    for belt_id in BELT_ORDER:
        try:
            bp = BeltProgress.objects.get(user=user, belt_id=belt_id)
        except BeltProgress.DoesNotExist:
            bp = BeltProgress.objects.create(
                user=user,
                belt_id=belt_id,
                status="active" if belt_id == "white" else "locked",
                passed=False,
                attempts=0,
                best_acc=0,
                levels_done=[]
            )
        
        belt_progress_data.append({
            "belt_id": belt_id,
            "name": dict(BELT_CHOICES).get(belt_id, belt_id),
            "status": bp.status,
            "passed": bp.passed,
            "attempts": bp.attempts,
            "best_acc": round(bp.best_acc * 100, 1) if bp.best_acc else 0,
            "levels_done": bp.levels_done,
            "levels_total": len(BELT_DETAILS.get(belt_id, {}).get("tables", [])),
            "progress_percentage": bp.progress_percentage if hasattr(bp, 'progress_percentage') else 0,
            "belt_details": BELT_DETAILS.get(belt_id, {"tables": [], "minutes": 5, "emoji": "⬜"}),
            "requires_subscription": belt_id != "white"
        })
    
    active_belt_idx = user.current_belt_idx
    active_belt_id = user.active_belt_id
    
    # Check subscription status for belt access
    subscription = PaymentSubscription.objects.filter(user=user).first()
    has_active_subscription = subscription and subscription.is_active() if subscription else False
    
    return ok(
        belts=belt_progress_data,
        active_belt_id=active_belt_id,
        active_belt_idx=active_belt_idx,
        has_active_subscription=has_active_subscription,
        trial_days_remaining=subscription.days_remaining() if subscription and subscription.status == 'trial' else 0
    )


@require_GET
@require_role("student")
def api_student_belt_details(request, belt_id):
    """Get details for a specific belt"""
    if belt_id not in BELT_ORDER:
        return err("Invalid belt_id")
    
    belt_details = BELT_DETAILS.get(belt_id, {})
    belt_progress = BeltProgress.objects.filter(user=request.user, belt_id=belt_id).first()
    
    # Check if belt requires subscription
    requires_subscription = belt_id != "white"
    subscription = PaymentSubscription.objects.filter(user=request.user).first()
    has_access = not requires_subscription or (subscription and subscription.is_active())
    
    return ok(
        belt_id=belt_id,
        name=dict(BELT_CHOICES).get(belt_id, belt_id),
        tables=belt_details.get("tables", []),
        minutes=belt_details.get("minutes", 5),
        emoji=belt_details.get("emoji", "⬜"),
        requires_subscription=requires_subscription,
        has_access=has_access,
        color={
            "white": "#d0d0d0",
            "yellow": "#f9a825",
            "blue": "#1565c0",
            "red": "#c62828",
            "black": "#1a1a1a",
            "brown": "#4e342e",
            "purple": "#6a1b9a",
            "gold": "#b8860b",
            "master": "#1a237e"
        }.get(belt_id, "#d0d0d0"),
        progress={
            "passed": belt_progress.passed if belt_progress else False,
            "attempts": belt_progress.attempts if belt_progress else 0,
            "best_acc": round(belt_progress.best_acc * 100, 1) if belt_progress and belt_progress.best_acc else 0,
            "levels_done": belt_progress.levels_done if belt_progress else [],
            "status": belt_progress.status if belt_progress else "locked"
        } if belt_progress else None
    )


@csrf_exempt
def api_student_belt_update(request):
    """Update belt progress - accepts POST requests"""
    import json
    
    logger.info(f"=== BELT UPDATE CALLED ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"User: {request.user}")
    logger.info(f"Authenticated: {request.user.is_authenticated}")
    
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    if request.user.role != 'student':
        return JsonResponse({"error": "Only students can update belts"}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({"error": f"Method {request.method} not allowed. Use POST."}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    
    belt_id = data.get("belt_id", "")
    logger.info(f"Belt update: user={request.user.email}, belt_id={belt_id}, data={data}")
    
    if belt_id not in BELT_ORDER:
        return JsonResponse({"error": f"Invalid belt_id: {belt_id}"}, status=400)
    
    # Check subscription for non-white belts
    if belt_id != "white":
        subscription = PaymentSubscription.objects.filter(user=request.user).first()
        if not subscription or not subscription.is_active():
            return JsonResponse({"error": "Premium subscription required for this belt"}, status=403)

    try:
        bp, created = BeltProgress.objects.get_or_create(
            user=request.user, 
            belt_id=belt_id,
            defaults={"status": "active" if belt_id == "white" else "locked"},
        )
        
        passed = data.get("passed", False)
        status = data.get("status", bp.status)
        attempts = data.get("attempts", bp.attempts)
        best_acc = max(bp.best_acc, data.get("best_acc", 0))
        levels_done = data.get("levels_done", bp.levels_done)
        
        bp.status = status
        bp.passed = passed
        bp.attempts = attempts
        bp.best_acc = best_acc
        bp.levels_done = levels_done
        bp.save()
        
        logger.info(f"Belt saved: {belt_id}, passed={passed}, levels={levels_done}")
        
        if passed:
            idx = BELT_ORDER.index(belt_id)
            if idx + 1 < len(BELT_ORDER):
                next_id = BELT_ORDER[idx + 1]
                next_belt, _ = BeltProgress.objects.get_or_create(
                    user=request.user, 
                    belt_id=next_id,
                    defaults={"status": "locked"}
                )
                if next_belt.status == "locked":
                    next_belt.status = "active"
                    next_belt.save()
                    logger.info(f"Unlocked next belt: {next_id}")
            
            request.user.current_belt_idx = idx + 1
            request.user.save(update_fields=['current_belt_idx'])
            logger.info(f"User current belt updated to index: {request.user.current_belt_idx}")
        
        bp_all = {}
        for b in request.user.belt_progress.all():
            bp_all[b.belt_id] = {
                "belt_id": b.belt_id,
                "status": b.status,
                "passed": b.passed,
                "attempts": b.attempts,
                "best_acc": b.best_acc,
                "levels_done": b.levels_done,
            }
        
        current_belt_id = BELT_ORDER[request.user.current_belt_idx] if request.user.current_belt_idx < len(BELT_ORDER) else BELT_ORDER[-1]
        
        return JsonResponse({
            "ok": True,
            "belts": bp_all,
            "current_belt_idx": request.user.current_belt_idx,
            "current_belt_id": current_belt_id
        })
        
    except Exception as e:
        logger.error(f"Error updating belt: {e}")
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)


@csrf_exempt
@require_POST
@require_role("student")
def api_session_save(request):
    data = json_body(request)
    user = request.user
    belt_id = data.get("belt_id", "white")
    passed = bool(data.get("passed", False))
    accuracy = float(data.get("accuracy", 0))
    time_used = int(data.get("time_used", 0))
    correct = int(data.get("correct", 0))
    total_q = int(data.get("total_q", 0))

    with transaction.atomic():
        TrainingSession.objects.create(
            user=user, belt_id=belt_id, passed=passed,
            accuracy=accuracy, time_used=time_used,
            correct=correct, total_q=total_q,
        )
        
        streak_obj, _ = Streak.objects.select_for_update().get_or_create(user=user)
        new_streak = streak_obj.update()

        new_badges = []
        total_correct = user.training_sessions.aggregate(s=Sum("correct"))["s"] or 0

        def _award(bid):
            if award_badge_if_new(user, bid):
                new_badges.append(bid)

        if total_correct >= 1:
            _award("first_correct")
        
        if passed:
            _award(f"{belt_id}_belt")
            
            if accuracy >= 1.0:
                _award("perfect_belt")
            
            belt_minutes = {
                "white": 5, "yellow": 7, "blue": 9, "red": 11, 
                "black": 13, "brown": 15, "purple": 17, 
                "gold": 19, "master": 21
            }
            allowed = belt_minutes.get(belt_id, 5) * 60
            if allowed - time_used >= 120:
                _award("speed_run")
        
        if new_streak >= 7:
            _award("streak_7")
        
        if total_correct >= 100:
            _award("century")
        
        passed_belts = user.belt_progress.filter(passed=True).values_list("belt_id", flat=True)
        if len(passed_belts) == len(BELT_ORDER):
            _award("master_belt")

    return ok(streak=new_streak, new_badges=new_badges)


@require_GET
@require_role("student")
def api_facts_get(request):
    facts = {
        f"{fm.a}x{fm.b}": {
            "a": fm.a, "b": fm.b,
            "seen": fm.seen, "correct": fm.correct,
            "total_time": fm.total_time_ms,
            "avg_time": fm.avg_time_ms,
            "accuracy": fm.accuracy
        }
        for fm in request.user.fact_memory.all()
    }
    return ok(facts=facts)


@csrf_exempt
@require_POST
@require_role("student")
def api_facts_update(request):
    data = json_body(request)
    facts = data.get("facts", [])
    user = request.user

    with transaction.atomic():
        for f in facts:
            a = int(f.get("a", 0))
            b = int(f.get("b", 0))
            if not (1 <= a <= 20 and 1 <= b <= 20):
                continue
            correct_val = 1 if f.get("correct") else 0
            time_ms = int(f.get("time_ms", 0))

            fact, created = FactMemory.objects.get_or_create(
                user=user, a=a, b=b,
                defaults={"seen": 0, "correct": 0, "total_time_ms": 0}
            )
            
            fact.seen += 1
            fact.correct += correct_val
            fact.total_time_ms += time_ms
            fact.save()

    return ok()


@require_GET
@require_role("student")
def api_badges(request):
    badges = list(request.user.badges.values_list("badge_id", flat=True))
    return ok(badges=badges)


@require_GET
@require_role("student")
def api_streak(request):
    streak_obj, _ = Streak.objects.get_or_create(user=request.user)
    return ok(
        streak=streak_obj.count,
        last_date=streak_obj.last_date.isoformat() if streak_obj.last_date else None,
    )


@require_GET
@require_role("student")
def api_student_stats(request):
    """Get student statistics"""
    user = request.user
    
    stats = user.training_sessions.aggregate(
        total_sessions=Count("id"),
        total_correct=Coalesce(Sum("correct"), 0),
        total_questions=Coalesce(Sum("total_q"), 0),
        avg_accuracy=Coalesce(Avg("accuracy"), 0),
        total_passed=Count("id", filter=Q(passed=True))
    )
    
    belt_stats = user.belt_progress.aggregate(
        belts_passed=Count("id", filter=Q(passed=True)),
        belts_active=Count("id", filter=Q(status="active"))
    )
    
    badge_count = user.badges.count()
    streak = user.streak.count if hasattr(user, 'streak') and user.streak else 0
    
    return ok(
        total_sessions=stats["total_sessions"] or 0,
        total_correct=stats["total_correct"] or 0,
        total_questions=stats["total_questions"] or 0,
        avg_accuracy=round((stats["avg_accuracy"] or 0) * 100, 1),
        total_passed=stats["total_passed"] or 0,
        belts_passed=belt_stats["belts_passed"] or 0,
        belts_active=belt_stats["belts_active"] or 0,
        badges_count=badge_count,
        streak=streak
    )


@require_GET
@require_role("student")
def api_student_recent_sessions(request):
    """Get recent training sessions for the student"""
    limit = int(request.GET.get("limit", 10))
    
    sessions = TrainingSession.objects.filter(user=request.user).order_by("-created_at")[:limit]
    
    data = [
        {
            "id": s.pk,
            "belt_id": s.belt_id,
            "belt_name": dict(BELT_CHOICES).get(s.belt_id, s.belt_id),
            "passed": s.passed,
            "accuracy": round(s.accuracy * 100, 1),
            "time_used": s.time_used,
            "time_display": s.time_display,
            "correct": s.correct,
            "total_q": s.total_q,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]
    
    return ok(sessions=data)


@require_GET
@require_role("student")
def api_leaderboard(request):
    scope = request.GET.get("scope", "national")
    user = request.user

    qs = User.objects.filter(role="student", is_active=True)
    if scope == "school" and user.school:
        qs = qs.filter(school=user.school)
    elif scope == "county" and user.county:
        qs = qs.filter(county=user.county)

    qs = qs.annotate(
        score=Sum("training_sessions__correct"),
        sessions=Count("training_sessions"),
        avg_acc=Avg("training_sessions__accuracy"),
    ).order_by(F("score").desc(nulls_last=True))[:50]

    entries = []
    for u in qs:
        passed_belts = list(
            u.belt_progress.filter(passed=True)
            .values_list("belt_id", flat=True)
        )
        highest = max(
            (BELT_ORDER.index(b) for b in passed_belts if b in BELT_ORDER),
            default=-1,
        )
        entries.append({
            "id": u.pk,
            "name": u.get_full_name() or u.username,
            "school": u.school,
            "county": u.county,
            "score": u.score or 0,
            "belt_idx": highest,
            "sessions": u.sessions or 0,
            "accuracy": round((u.avg_acc or 0) * 100, 1),
        })

    return ok(entries=entries, scope=scope)


@require_GET
@require_role("student")
def api_tutors_search(request):
    name_q = request.GET.get("name", "").strip().lower()
    county_q = request.GET.get("county", "").strip().lower()
    spec_q = request.GET.get("spec", "").strip().lower()

    qs = User.objects.filter(role="tutor", is_active=True, is_paid=True)
    if name_q:
        qs = qs.filter(
            Q(first_name__icontains=name_q) | Q(last_name__icontains=name_q)
        )
    if county_q:
        qs = qs.filter(county__iexact=county_q)
    if spec_q:
        qs = qs.filter(spec__icontains=spec_q)

    tutors = []
    for t in qs[:50]:
        student_count = TutorRequest.objects.filter(
            tutor=t, status="accepted"
        ).values("student").distinct().count()
        
        tutors.append({
            "id": t.pk,
            "name": t.get_full_name(),
            "spec": t.get_spec_display(),
            "county": t.county,
            "school": t.school,
            "rating": 4.7,
            "available": True,
            "student_count": student_count,
        })
    
    return ok(tutors=tutors)


@csrf_exempt
@require_POST
@require_role("student")
def api_request_tutor(request):
    data = json_body(request)
    tutor_id = data.get("tutor_id")
    message = data.get("message", "")

    try:
        tutor = User.objects.get(pk=tutor_id, role="tutor", is_active=True)
    except User.DoesNotExist:
        return err("Tutor not found")

    existing = TutorRequest.objects.filter(
        student=request.user, tutor=tutor
    ).first()
    if existing:
        if existing.status == "pending":
            return err("You already have a pending request for this tutor")
        elif existing.status == "accepted":
            return err("You are already connected with this tutor")
        elif existing.status == "rejected":
            existing.status = "pending"
            existing.message = message
            existing.save()
            return ok(request_id=existing.pk)

    req = TutorRequest.objects.create(
        student=request.user,
        tutor=tutor,
        message=message,
        status="pending"
    )

    return ok(request_id=req.pk)


@require_GET
@require_role("student")
def api_my_requests(request):
    reqs = TutorRequest.objects.filter(
        student=request.user
    ).select_related("tutor").order_by("-created_at")

    data = [
        {
            "id": r.pk,
            "tutor_id": r.tutor.pk,
            "tutor_name": r.tutor.get_full_name(),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in reqs
    ]
    return ok(requests=data)


@csrf_exempt
@require_POST
@require_role("student")
def api_student_profile_update(request):
    data = json_body(request)
    user = request.user
    
    if "first_name" in data:
        user.first_name = data["first_name"].strip()
    if "last_name" in data:
        user.last_name = data["last_name"].strip()
    if "email" in data:
        new_email = data["email"].strip().lower()
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return err("Email already in use")
        user.email = new_email
        user.username = new_email
    if "county" in data:
        user.county = data["county"]
    if "school" in data:
        user.school = data["school"]
    
    user.save()
    return ok(user=user_json(user))


@csrf_exempt
@require_POST
@require_role("student")
def api_student_password_change(request):
    data = json_body(request)
    new_password = data.get("password", "")
    
    if len(new_password) < 6:
        return err("Password must be at least 6 characters")
    
    user = request.user
    user.set_password(new_password)
    user.save()
    
    updated_user = authenticate(username=user.username, password=new_password)
    if updated_user:
        login(request, updated_user)
    
    return ok()


# ─────────────────────────────────────────────────────────────────────────────
# TUTOR API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("tutor")
def api_tutor_profile(request):
    user = request.user
    return ok(user=user_json(user))


@require_GET
@require_role("tutor")
def api_tutor_requests(request):
    reqs = TutorRequest.objects.filter(
        tutor=request.user
    ).select_related("student").order_by("-created_at")

    data = [
        {
            "id": r.pk,
            "student_id": r.student.pk,
            "student_name": r.student.get_full_name(),
            "school": r.student.school,
            "county": r.student.county,
            "status": r.status,
            "message": r.message,
            "created_at": r.created_at.isoformat(),
        }
        for r in reqs
    ]
    return ok(requests=data)


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_request_update(request):
    data = json_body(request)
    request_id = data.get("request_id")
    status = data.get("status")

    if status not in ("accepted", "rejected"):
        return err("status must be accepted or rejected")

    updated = TutorRequest.objects.filter(
        pk=request_id, tutor=request.user
    ).update(status=status)

    if not updated:
        return err("Request not found", 404)
    return ok()


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_profile_update(request):
    data = json_body(request)
    user = request.user
    
    if "first_name" in data:
        user.first_name = data["first_name"].strip()
    if "last_name" in data:
        user.last_name = data["last_name"].strip()
    if "email" in data:
        new_email = data["email"].strip().lower()
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return err("Email already in use")
        user.email = new_email
        user.username = new_email
    if "county" in data:
        user.county = data["county"]
    if "spec" in data:
        user.spec = data["spec"]
    
    user.save()
    return ok(user=user_json(user))


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_password_change(request):
    data = json_body(request)
    new_password = data.get("password", "")
    
    if len(new_password) < 6:
        return err("Password must be at least 6 characters")
    
    user = request.user
    user.set_password(new_password)
    user.save()
    
    updated_user = authenticate(username=user.username, password=new_password)
    if updated_user:
        login(request, updated_user)
    
    return ok()


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN API
# ─────────────────────────────────────────────────────────────────────────────

# HARDCODED ADMIN CREDENTIALS
ADMIN_CREDENTIALS = {
    "mesh@timesdojo.com": "Mesh@2026",
    "antoh@timesdojo.com": "Antoh@2026",
}

# Friendly login names mapping
FRIENDLY_LOGINS = {
    "mesh": "mesh@timesdojo.com",
    "antoh": "antoh@timesdojo.com",
}


@csrf_exempt
@require_POST
def api_admin_login(request):
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    # Handle friendly login names
    login_email = email
    if email in FRIENDLY_LOGINS:
        login_email = FRIENDLY_LOGINS[email]
    elif "@" not in email and email.lower() in ["mesh", "antoh"]:
        login_email = f"{email.lower()}@timesdojo.com"
    
    # Check hardcoded credentials first
    if login_email in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[login_email] == password:
        # Get or create admin user in database
        try:
            admin_user = User.objects.get(email=login_email, role="admin")
        except User.DoesNotExist:
            # Create the admin user if doesn't exist
            admin_name = "Mesh" if "mesh" in login_email else "Antoh"
            admin_user = User.objects.create_user(
                username=login_email,
                email=login_email,
                password=password,
                first_name=admin_name,
                last_name="Admin",
                role="admin",
                is_staff=True,
                is_superuser=True,
                is_active=True
            )
            logger.info(f"Created hardcoded admin user: {login_email}")
        
        # Manually login (authenticate may fail if user was just created)
        login(request, admin_user)
        return ok(user=user_json(admin_user))
    
    # Fall back to database check for regular admin accounts
    try:
        u = User.objects.get(email=email, role="admin")
    except User.DoesNotExist:
        return err("Invalid credentials", 401)
    
    user = authenticate(request, username=u.username, password=password)
    if not user:
        return err("Invalid credentials", 401)
    
    login(request, user)
    return ok(user=user_json(user))


@require_GET
@admin_only
def api_admin_overview(request):
    total_students = User.objects.filter(role="student", is_active=True).count()
    total_tutors = User.objects.filter(role="tutor", is_active=True).count()
    paid_students = User.objects.filter(role="student", is_paid=True, is_active=True).count()
    active_schools = User.objects.filter(role="student", is_active=True).exclude(school="").values("school").distinct().count()
    total_belts = BeltProgress.objects.filter(passed=True).count()
    total_sessions = TrainingSession.objects.count()
    total_q = TrainingSession.objects.aggregate(s=Sum("total_q"))["s"] or 0
    avg_acc = TrainingSession.objects.aggregate(a=Avg("accuracy"))["a"] or 0

    return ok(
        total_students=total_students,
        total_tutors=total_tutors,
        paid_students=paid_students,
        active_schools=active_schools,
        total_belts=total_belts,
        total_sessions=total_sessions,
        total_questions=total_q,
        avg_accuracy=round(avg_acc * 100, 1),
        revenue_total=paid_students * 5,
    )


@require_GET
@require_role("student")
def api_student_chat_tutors(request):
    """Get list of tutors the student has chatted with or can chat with"""
    user = request.user
    
    accepted_requests = TutorRequest.objects.filter(
        student=user, status='accepted'
    ).values_list('tutor_id', flat=True)
    
    tutors_with_chat = set(ChatMessage.objects.filter(recipient=user).values_list('sender_id', flat=True))
    tutors_with_chat.update(ChatMessage.objects.filter(sender=user).values_list('recipient_id', flat=True))
    
    tutor_ids = set(accepted_requests) | tutors_with_chat
    
    tutors = User.objects.filter(id__in=tutor_ids, role='tutor', is_active=True)
    
    result = []
    for t in tutors:
        last_message = ChatMessage.objects.filter(
            (Q(sender=user, recipient=t) | Q(sender=t, recipient=user))
        ).order_by('-created_at').first()
        
        unread_count = ChatMessage.objects.filter(
            sender=t, recipient=user, is_read=False
        ).count()
        
        result.append({
            "id": t.id,
            "name": t.get_full_name(),
            "spec": t.get_spec_display(),
            "county": t.county,
            "rating": 4.7,
            "last_message": last_message.message[:100] if last_message else '',
            "last_message_time": last_message.created_at.isoformat() if last_message else None,
            "unread_count": unread_count,
        })
    
    return ok(tutors=result)


@require_GET
@admin_only
def api_admin_students(request):
    county = request.GET.get("county", "")
    paid = request.GET.get("paid", "")

    qs = User.objects.filter(role="student", is_active=True)
    if county:
        qs = qs.filter(county=county)
    if paid == "1":
        qs = qs.filter(is_paid=True)
    elif paid == "0":
        qs = qs.filter(is_paid=False)

    qs = qs.annotate(
        sessions=Count("training_sessions"),
        total_correct=Sum("training_sessions__correct"),
        avg_acc=Avg("training_sessions__accuracy"),
    ).prefetch_related("belt_progress", "badges")[:200]

    students = []
    for u in qs:
        passed_belts = [bp.belt_id for bp in u.belt_progress.all() if bp.passed]
        highest = max(
            (BELT_ORDER.index(b) for b in passed_belts if b in BELT_ORDER),
            default=-1,
        )
        streak_obj = Streak.objects.filter(user=u).first()
        students.append({
            **user_json(u),
            "sessions": u.sessions or 0,
            "total_correct": u.total_correct or 0,
            "accuracy": round((u.avg_acc or 0) * 100, 1),
            "belt_idx": highest,
            "belt_name": f"{BELT_ORDER[highest].title()} Belt" if highest >= 0 else "No Belt",
            "streak": streak_obj.count if streak_obj else 0,
        })

    return ok(students=students)


@require_GET
@admin_only
def api_admin_tutors(request):
    tutors = User.objects.filter(role="tutor", is_active=True).annotate(
        session_count=Count("tutor_requests_received", filter=Q(tutor_requests_received__status="accepted")),
        student_count=Count("tutor_requests_received__student", filter=Q(tutor_requests_received__status="accepted"), distinct=True),
        pending_requests=Count("tutor_requests_received", filter=Q(tutor_requests_received__status="pending")),
    )

    data = [
        {
            **user_json(t),
            "sessions": t.session_count,
            "students": t.student_count,
            "pending_requests": t.pending_requests,
            "rating": 4.7,
        }
        for t in tutors
    ]
    return ok(tutors=data)


@require_GET
@admin_only
def api_admin_belts(request):
    result = []
    for belt_id in BELT_ORDER:
        agg = TrainingSession.objects.filter(belt_id=belt_id).aggregate(
            pass_rate=Avg("passed"),
            avg_acc=Avg("accuracy"),
            avg_time=Avg("time_used"),
        )
        holders = BeltProgress.objects.filter(belt_id=belt_id, passed=True).count()
        result.append({
            "belt_id": belt_id,
            "holders": holders,
            "pass_rate": round((agg["pass_rate"] or 0) * 100, 1),
            "avg_accuracy": round((agg["avg_acc"] or 0) * 100, 1),
            "avg_time_secs": round(agg["avg_time"] or 0, 1),
        })
    return ok(belt_analytics=result)


@require_GET
@admin_only
def api_admin_knowledge(request):
    facts = FactMemory.objects.values("a", "b").annotate(
        total_seen=Sum("seen"),
        total_correct=Sum("correct"),
        avg_time=Avg("total_time_ms"),
    ).filter(total_seen__gt=0)

    data = [
        {
            "a": f["a"],
            "b": f["b"],
            "seen": f["total_seen"],
            "correct": f["total_correct"],
            "avg_time": round(f["avg_time"] or 0, 0),
            "accuracy": round((f["total_correct"] / f["total_seen"] * 100) if f["total_seen"] > 0 else 0, 1),
        }
        for f in facts
    ]
    return ok(facts=data)


@require_GET
@admin_only
def api_admin_activity(request):
    sessions = TrainingSession.objects.select_related("user").order_by("-created_at")[:80]
    data = [
        {
            "id": s.pk,
            "student_name": s.user.get_full_name(),
            "school": s.user.school,
            "county": s.user.county,
            "belt_id": s.belt_id,
            "passed": s.passed,
            "accuracy": round(s.accuracy * 100, 1),
            "time_used": s.time_used,
            "total_q": s.total_q,
            "correct": s.correct,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]
    return ok(sessions=data)


@require_GET
@admin_only
def api_admin_county(request):
    rows = (
        User.objects
        .filter(role="student", is_active=True)
        .exclude(county="")
        .values("county")
        .annotate(students=Count("id"), paid_count=Sum("is_paid"))
        .order_by("-students")
    )
    data = [
        {
            "county": r["county"],
            "students": r["students"],
            "revenue": (r["paid_count"] or 0) * 5,
        }
        for r in rows
    ]
    return ok(counties=data)


@require_GET
@admin_only
def api_admin_leaderboard(request):
    qs = (
        User.objects
        .filter(role="student", is_active=True)
        .annotate(score=Sum("training_sessions__correct"))
        .order_by(F("score").desc(nulls_last=True))[:50]
    )
    entries = [
        {
            "id": u.pk,
            "name": u.get_full_name(),
            "school": u.school,
            "county": u.county,
            "score": u.score or 0,
        }
        for u in qs
    ]
    return ok(entries=entries)


@require_GET
@admin_only
def api_admin_tutor_requests(request):
    reqs = TutorRequest.objects.select_related("student", "tutor").order_by("-created_at")
    data = [
        {
            "id": r.pk,
            "student_name": r.student.get_full_name(),
            "tutor_name": r.tutor.get_full_name(),
            "school": r.student.school,
            "county": r.student.county,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in reqs
    ]
    return ok(requests=data)


@csrf_exempt
@require_POST
@admin_only
def api_admin_suspend(request):
    data = json_body(request)
    uid = data.get("user_id")
    User.objects.filter(pk=uid).update(is_active=False)
    return ok()


@csrf_exempt
@require_POST
@admin_only
def api_admin_upgrade(request):
    data = json_body(request)
    uid = data.get("user_id")
    paid = bool(data.get("paid", True))
    User.objects.filter(pk=uid).update(is_paid=paid)
    return ok()


@csrf_exempt
@require_POST
@admin_only
def api_admin_approve_tutor(request):
    data = json_body(request)
    uid = data.get("user_id")
    User.objects.filter(pk=uid, role="tutor").update(is_paid=True)
    return ok()


# ─────────────────────────────────────────────────────────────────────────────
# FILE UPLOAD & VIDEO CALL API
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
@require_role("student", "tutor")
def api_chat_upload_file(request):
    """Upload a file attachment for chat"""
    data = request.POST
    file = request.FILES.get('file')
    recipient_id = data.get('recipient_id')
    
    if not file:
        return err("No file provided", 400)
    
    if not recipient_id:
        return err("Recipient ID required", 400)
    
    try:
        recipient = User.objects.get(id=recipient_id, is_active=True)
    except User.DoesNotExist:
        return err("Recipient not found", 404)
    
    if file.size > 10 * 1024 * 1024:
        return err("File too large. Max 10MB", 400)
    
    file_name = file.name
    mime_type, _ = mimetypes.guess_type(file_name)
    
    if mime_type and mime_type.startswith('image/'):
        attachment_type = 'image'
    elif mime_type == 'application/pdf':
        attachment_type = 'pdf'
    elif mime_type and mime_type.startswith('video/'):
        attachment_type = 'video'
    else:
        attachment_type = 'file'
    
    file_path = default_storage.save(f'chat_attachments/{file_name}', file)
    file_url = f"{settings.MEDIA_URL}{file_path}"
    
    chat = ChatMessage.objects.create(
        sender=request.user,
        recipient=recipient,
        message=f"[File: {file_name}]",
        attachment=file_path,
        attachment_name=file_name,
        attachment_size=file.size,
        attachment_type=attachment_type
    )
    
    return ok(
        id=chat.id,
        message=chat.message,
        attachment_url=file_url,
        attachment_name=file_name,
        created_at=chat.created_at.isoformat()
    )


@require_GET
@require_role("student")
def api_student_chat_with_attachments(request, tutor_id):
    """Get chat messages including attachments"""
    user = request.user
    messages = ChatMessage.objects.filter(
        (Q(sender=user, recipient_id=tutor_id) | Q(sender_id=tutor_id, recipient=user))
    ).order_by('created_at')
    
    ChatMessage.objects.filter(sender_id=tutor_id, recipient=user, is_read=False).update(is_read=True)
    
    data = []
    for m in messages:
        attachment_data = None
        if m.attachment and m.attachment.name:
            attachment_url = f"{settings.MEDIA_URL}{m.attachment.name}"
            attachment_data = {
                'url': attachment_url,
                'name': m.attachment_name,
                'size': m.attachment_size,
                'type': m.attachment_type
            }
        
        data.append({
            'id': m.id,
            'sender_id': m.sender.id,
            'sender_name': m.sender.get_full_name(),
            'message': m.message,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat(),
            'attachment': attachment_data
        })
    
    return ok(messages=data)


@csrf_exempt
@require_POST
@require_role("student", "tutor")
def api_start_video_call(request):
    """Start a video call session using Google Meet"""
    data = json_body(request)
    
    logger.info(f"Video call request: user={request.user.email}, data={data}")
    
    if request.user.role == 'student':
        recipient_id = data.get('tutor_id')
        if not recipient_id:
            return err("tutor_id required", 400)
        try:
            recipient = User.objects.get(id=recipient_id, role='tutor', is_active=True)
        except User.DoesNotExist:
            return err("Tutor not found", 404)
    else:
        recipient_id = data.get('student_id')
        if not recipient_id:
            return err("student_id required", 400)
        try:
            recipient = User.objects.get(id=recipient_id, role='student', is_active=True)
        except User.DoesNotExist:
            return err("Student not found", 404)
    
    meeting_code = hashlib.md5(f"{request.user.id}_{recipient.id}_{int(time.time())}".encode()).hexdigest()[:10]
    meeting_link = f"https://meet.google.com/{meeting_code}"
    
    chat = ChatMessage.objects.create(
        sender=request.user,
        recipient=recipient,
        message=f"📞 Video Call Started! Join here: {meeting_link}",
        is_read=False
    )
    
    return ok(
        room_name=meeting_code,
        room_url=meeting_link,
        message_id=chat.id
    )


@csrf_exempt
@require_POST
@require_role("student", "tutor")
def api_end_video_call(request):
    """End a video call session"""
    data = json_body(request)
    room_name = data.get('room_name')
    
    chat = ChatMessage.objects.filter(
        message__contains=room_name,
        sender=request.user
    ).order_by('-created_at').first()
    
    if chat:
        chat.message = chat.message.replace("Started", "Ended")
        chat.save()
    
    return ok()


def video_call_view(request, room_name):
    """Render video call page with Google Meet"""
    if not request.user.is_authenticated:
        return redirect('dojo:login')
    
    meeting_link = f"https://meet.google.com/{room_name}"
    
    return render(request, 'dojo/video_call.html', {
        'room_name': room_name,
        'meeting_link': meeting_link,
        'user': request.user
    })


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT API
# ─────────────────────────────────────────────────────────────────────────────

def get_paystack_headers():
    """Get Paystack API headers"""
    api_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }


@csrf_exempt
@require_POST
@require_role("student")
def api_initialize_payment(request):
    """Initialize Paystack payment"""
    data = json_body(request)
    plan = data.get('plan', 'monthly')
    
    if plan not in settings.SUBSCRIPTION_PRICES:
        return err("Invalid plan selected", 400)
    
    amount = settings.SUBSCRIPTION_PRICES[plan] * 100  # Paystack uses kobo/cents
    
    # Generate unique reference
    reference = f"TD-{request.user.id}-{uuid.uuid4().hex[:12].upper()}"
    
    # Get user email
    email = request.user.email
    
    # Prepare callback URL
    callback_url = request.build_absolute_uri('/payment/verify/')
    
    payload = {
        'email': email,
        'amount': int(amount),
        'reference': reference,
        'callback_url': callback_url,
        'metadata': {
            'user_id': request.user.id,
            'plan': plan,
            'custom_fields': [
                {'display_name': 'Plan', 'variable_name': 'plan', 'value': plan},
                {'display_name': 'User ID', 'variable_name': 'user_id', 'value': request.user.id},
            ]
        }
    }
    
    try:
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers=get_paystack_headers(),
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            if resp_data.get('status'):
                # Save transaction
                transaction = PaymentTransaction.objects.create(
                    user=request.user,
                    reference=reference,
                    access_code=resp_data['data']['access_code'],
                    amount=Decimal(settings.SUBSCRIPTION_PRICES[plan]),
                    plan=plan,
                    status='pending',
                    paystack_response=resp_data
                )
                
                return ok(
                    authorization_url=resp_data['data']['authorization_url'],
                    reference=reference,
                    access_code=resp_data['data']['access_code']
                )
        else:
            logger.error(f"Paystack initialization failed: {response.text}")
            return err("Payment initialization failed", 500)
            
    except Exception as e:
        logger.error(f"Paystack error: {e}")
        return err("Payment service unavailable", 500)


@csrf_exempt
def api_verify_payment(request):
    """Verify Paystack payment"""
    reference = request.GET.get('reference')
    
    if not reference:
        return err("No reference provided", 400)
    
    try:
        transaction = PaymentTransaction.objects.get(reference=reference)
    except PaymentTransaction.DoesNotExist:
        return err("Transaction not found", 404)
    
    try:
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=get_paystack_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            
            if resp_data.get('status') and resp_data['data']['status'] == 'success':
                # Update transaction
                transaction.status = 'success'
                transaction.completed_at = timezone.now()
                transaction.paystack_response = resp_data
                transaction.save()
                
                # Create or update subscription
                user = transaction.user
                plan = transaction.plan
                duration = settings.SUBSCRIPTION_DURATIONS[plan]
                
                subscription, created = PaymentSubscription.objects.get_or_create(
                    user=user,
                    defaults={
                        'plan': plan,
                        'status': 'active',
                        'start_date': timezone.now(),
                        'end_date': timezone.now() + timedelta(days=duration),
                        'last_payment_date': timezone.now(),
                        'next_payment_date': timezone.now() + timedelta(days=duration),
                        'paystack_reference': reference,
                    }
                )
                
                if not created:
                    # Update existing subscription
                    subscription.plan = plan
                    subscription.status = 'active'
                    subscription.start_date = timezone.now()
                    subscription.end_date = timezone.now() + timedelta(days=duration)
                    subscription.last_payment_date = timezone.now()
                    subscription.next_payment_date = timezone.now() + timedelta(days=duration)
                    subscription.paystack_reference = reference
                    subscription.save()
                
                # Update user's paid status
                user.is_paid = True
                user.save()
                
                # Return success page HTML or redirect
                return render(request, 'dojo/payment_success.html', {
                    'transaction': transaction,
                    'subscription': subscription
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                return render(request, 'dojo/payment_failed.html', {'reference': reference})
        else:
            return err("Verification failed", 500)
            
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return err("Verification failed", 500)


@csrf_exempt
def api_check_subscription(request):
    """Check if user has active subscription"""
    if not request.user.is_authenticated:
        return err("Not authenticated", 401)
    
    subscription = PaymentSubscription.objects.filter(user=request.user).first()
    
    if subscription and subscription.is_active():
        return ok(
            has_active_subscription=True,
            plan=subscription.plan,
            status=subscription.status,
            days_remaining=subscription.days_remaining(),
            is_trial=subscription.status == 'trial',
            trial_ends=subscription.trial_ends.isoformat() if subscription.trial_ends else None,
            expires_at=subscription.end_date.isoformat() if subscription.end_date else None,
        )
    
    # Check if user is in trial period (first 7 days after registration)
    user = request.user
    if user.date_joined and timezone.now() < user.date_joined + timedelta(days=settings.TRIAL_DAYS):
        # Create trial subscription if not exists
        trial_sub, created = PaymentSubscription.objects.get_or_create(
            user=user,
            defaults={
                'status': 'trial',
                'trial_ends': user.date_joined + timedelta(days=settings.TRIAL_DAYS),
                'plan': 'monthly'
            }
        )
        days_left = (trial_sub.trial_ends - timezone.now()).days
        return ok(
            has_active_subscription=True,
            is_trial=True,
            days_remaining=days_left,
            trial_ends=trial_sub.trial_ends.isoformat(),
        )
    
    return ok(has_active_subscription=False)


def api_get_plans(request):
    """Get available subscription plans"""
    return ok(plans=[
        {
            'id': 'monthly',
            'name': 'Monthly',
            'price': settings.SUBSCRIPTION_PRICES['monthly'],
            'duration_days': settings.SUBSCRIPTION_DURATIONS['monthly'],
            'description': 'Perfect for short-term commitment'
        },
        {
            'id': 'half_yearly',
            'name': '6 Months',
            'price': settings.SUBSCRIPTION_PRICES['half_yearly'],
            'duration_days': settings.SUBSCRIPTION_DURATIONS['half_yearly'],
            'description': 'Save $5 compared to monthly',
            'savings': 5.00
        },
        {
            'id': 'yearly',
            'name': 'Yearly',
            'price': settings.SUBSCRIPTION_PRICES['yearly'],
            'duration_days': settings.SUBSCRIPTION_DURATIONS['yearly'],
            'description': 'Best value! Save $10',
            'savings': 10.00
        }
    ])


def payment_modal_view(request):
    """Render payment modal/upgrade page"""
    if not request.user.is_authenticated:
        return redirect('dojo:login')
    
    # Check current subscription status
    subscription = PaymentSubscription.objects.filter(user=request.user).first()
    
    # Calculate trial days remaining
    trial_days_left = 0
    if subscription and subscription.status == 'trial':
        trial_days_left = (subscription.trial_ends - timezone.now()).days
    elif not subscription and request.user.date_joined:
        trial_end = request.user.date_joined + timedelta(days=settings.TRIAL_DAYS)
        if timezone.now() < trial_end:
            trial_days_left = (trial_end - timezone.now()).days
    
    return render(request, 'dojo/payment_modal.html', {
        'subscription': subscription,
        'trial_days_left': trial_days_left,
        'plans': [
            {'id': 'monthly', 'name': 'Monthly', 'price': settings.SUBSCRIPTION_PRICES['monthly']},
            {'id': 'half_yearly', 'name': '6 Months', 'price': settings.SUBSCRIPTION_PRICES['half_yearly']},
            {'id': 'yearly', 'name': 'Yearly', 'price': settings.SUBSCRIPTION_PRICES['yearly']},
        ]
    })


@csrf_exempt
def api_payment_webhook(request):
    """Paystack webhook endpoint for automatic updates"""
    import json
    import hmac
    import hashlib
    
    # Verify webhook signature
    paystack_signature = request.headers.get('x-paystack-signature')
    
    if not paystack_signature:
        return JsonResponse({'error': 'No signature'}, status=400)
    
    # Compute HMAC
    hash_object = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        request.body,
        hashlib.sha512
    )
    expected_signature = hash_object.hexdigest()
    
    if not hmac.compare_digest(paystack_signature, expected_signature):
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    # Process webhook
    data = json.loads(request.body)
    event = data.get('event')
    
    if event == 'charge.success':
        # Handle successful charge
        reference = data['data']['reference']
        
        try:
            transaction = PaymentTransaction.objects.get(reference=reference)
            if transaction.status != 'success':
                transaction.status = 'success'
                transaction.completed_at = timezone.now()
                transaction.save()
                
                # Update subscription
                subscription = transaction.user.get_subscription()
                plan = transaction.plan
                duration = settings.SUBSCRIPTION_DURATIONS.get(plan, 30)
                
                subscription.plan = plan
                subscription.status = 'active'
                subscription.end_date = timezone.now() + timedelta(days=duration)
                subscription.last_payment_date = timezone.now()
                subscription.next_payment_date = timezone.now() + timedelta(days=duration)
                subscription.save()
                
                transaction.user.is_paid = True
                transaction.user.save()
                
        except PaymentTransaction.DoesNotExist:
            pass
    
    elif event == 'subscription.disable':
        # Handle subscription cancellation
        subscription_code = data['data']['subscription_code']
        try:
            subscription = PaymentSubscription.objects.get(paystack_subscription_code=subscription_code)
            subscription.status = 'cancelled'
            subscription.cancel_at_period_end = True
            subscription.save()
        except PaymentSubscription.DoesNotExist:
            pass
    
    return JsonResponse({'status': 'success'})


def api_payment_receipts(request):
    """Get user's payment history"""
    if not request.user.is_authenticated:
        return err("Not authenticated", 401)
    
    receipts = PaymentTransaction.objects.filter(
        user=request.user,
        status='success'
    ).values(
        'reference', 'amount', 'plan', 'created_at', 'transaction_type'
    ).order_by('-created_at')
    
    return ok(receipts=list(receipts))


def payment_verify_view(request):
    """View for payment verification redirect"""
    return render(request, 'dojo/payment_verify.html', {'reference': request.GET.get('reference')})


# ─────────────────────────────────────────────────────────────────────────────
# TUTOR INTEREST API
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_tutor_interest(request):
    """Collect email from users interested in tutor features"""
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    
    if not email:
        return err("Email required")
    
    if '@' not in email or '.' not in email:
        return err("Valid email required")
    
    # Check if already exists
    if TutorInterest.objects.filter(email=email).exists():
        return ok(message="Already subscribed", exists=True)
    
    interest = TutorInterest.objects.create(email=email)
    logger.info(f"New tutor interest: {email}")
    
    return ok(message="Interest recorded", id=interest.id)


@require_GET
@admin_only
def api_admin_tutor_interests(request):
    """Get all tutor interest submissions for admin"""
    interests = TutorInterest.objects.all().order_by('-created_at')
    data = [
        {"id": i.id, "email": i.email, "created_at": i.created_at.isoformat()}
        for i in interests
    ]
    return ok(interests=data)


@csrf_exempt
@admin_only
def api_admin_tutor_interest_delete(request, interest_id):
    """Delete a specific tutor interest submission"""
    try:
        interest = TutorInterest.objects.get(id=interest_id)
        interest.delete()
        return ok()
    except TutorInterest.DoesNotExist:
        return err("Not found", 404)


@csrf_exempt
@require_POST
@admin_only
def api_admin_tutor_interests_clear_all(request):
    """Delete all tutor interest submissions"""
    count = TutorInterest.objects.all().count()
    TutorInterest.objects.all().delete()
    logger.info(f"Admin cleared {count} tutor interest submissions")
    return ok(deleted_count=count)