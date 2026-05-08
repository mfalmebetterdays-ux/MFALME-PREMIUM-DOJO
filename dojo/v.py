"""
All views for TimesTable Dojo.
"""

import json
import logging
import secrets
import requests
import mimetypes
import time
import hashlib
import PyPDF2
import io
import re
from datetime import date, timedelta
from functools import wraps
from decimal import Decimal
from django.db import models
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.hashers import make_password
from django.db import transaction, IntegrityError
from django.db.models import Avg, Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.db.models import Avg, Count, Sum, Q, F, Value, Case, When, IntegerField
from django.db.models.functions import Cast
from django.urls import reverse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db.models.functions import TruncDate, ExtractDay, ExtractMonth
from calendar import monthrange
from datetime import datetime, timedelta
import calendar
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET
from django.core.files.storage import default_storage
import mimetypes
import os
from django.core.cache import cache
import hmac


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
    TutorInterest,
    PasswordResetToken,
    ParentStudentLink,
    StudentActivityLog,
    ParentNotification,
    Curriculum,
    Grade,
    Subject,
    Topic,
    ContentItem,
    Question,
    StudentQuizAttempt,
    StudentAnswerDetail,
    StudentAnswerAttachment,
    SubscriptionPlan,
    UserSubscription,
    PaymentTransaction,
    UserTrial,
)

logger = logging.getLogger("dojo")

# Belt definitions for parent views
BELTS_LIST = [
    {'id': 'white', 'name': 'White Belt', 'color': '#d0d0d0', 'emoji': '⬜', 'tables': [2,5,10,11]},
    {'id': 'yellow', 'name': 'Yellow Belt', 'color': '#f9a825', 'emoji': '🟡', 'tables': [2,3,4,5,10,11]},
    {'id': 'blue', 'name': 'Blue Belt', 'color': '#1565c0', 'emoji': '🔵', 'tables': [2,3,4,5,6,7,10,11]},
    {'id': 'red', 'name': 'Red Belt', 'color': '#c62828', 'emoji': '🔴', 'tables': [2,3,4,5,6,7,8,9,10,11]},
    {'id': 'black', 'name': 'Black Belt', 'color': '#1a1a1a', 'emoji': '⚫', 'tables': [2,3,4,5,6,7,8,9,10,11,12,13]},
    {'id': 'brown', 'name': 'Brown Belt', 'color': '#4e342e', 'emoji': '🟤', 'tables': [2,3,4,5,6,7,8,9,10,11,12,13,14,15]},
    {'id': 'purple', 'name': 'Purple Belt', 'color': '#6a1b9a', 'emoji': '🟣', 'tables': [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17]},
    {'id': 'gold', 'name': 'Gold Belt', 'color': '#b8860b', 'emoji': '🏅', 'tables': [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19]},
    {'id': 'master', 'name': 'Master Belt', 'color': '#1a237e', 'emoji': '👑', 'tables': [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]},
]

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
        "curriculum": user.curriculum if hasattr(user, 'curriculum') else None,
        "grade": user.grade if hasattr(user, 'grade') else None,
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


def detect_questions_from_text(text):
    """Detect questions from extracted text using patterns"""
    questions = []
    
    pattern1 = re.compile(r'^(\d+)\.\s+(.+?)(?=\n\d+\.|\Z)', re.MULTILINE | re.DOTALL)
    pattern2 = re.compile(r'([^.!?]+[?])\s*', re.MULTILINE)
    
    matches = list(pattern1.finditer(text))
    
    if matches and len(matches) >= 2:
        for match in matches[:20]:
            q_num = match.group(1)
            q_text = match.group(2).strip()
            if len(q_text) > 10:
                questions.append({
                    'number': q_num,
                    'text': q_text[:500],
                    'type': 'mcq'
                })
    
    if not questions:
        matches = list(pattern2.finditer(text))
        for i, match in enumerate(matches[:20]):
            q_text = match.group(1).strip()
            if len(q_text) > 10:
                questions.append({
                    'number': str(i+1),
                    'text': q_text[:500],
                    'type': 'short_answer'
                })
    
    return questions


def get_paystack_headers():
    """Get Paystack API headers"""
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD RESET VIEWS
# ─────────────────────────────────────────────────────────────────────────────

def password_reset_page(request):
    return render(request, 'dojo/forgot_password.html')


def password_reset_confirm_page(request):
    return render(request, 'dojo/password_reset_confirm.html')


def password_reset_complete_page(request):
    return render(request, 'dojo/password_reset_complete.html')


@csrf_exempt
@require_http_methods(["POST"])
def api_password_reset_request(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        
        if not email:
            return JsonResponse({'error': 'Email address is required'}, status=400)
        
        logger.info(f"Password reset requested for email: {email}")
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning(f"Password reset requested for non-existent email: {email}")
            return JsonResponse({'message': 'If an account exists with this email, a reset link has been sent.'}, status=200)
        
        deleted_count = PasswordResetToken.objects.filter(user=user, used=False).delete()
        logger.info(f"Deleted {deleted_count[0]} existing tokens for user {user.email}")
        
        token_string = hashlib.sha256(f"{user.id}{uuid.uuid4().hex}{time.time()}".encode()).hexdigest()
        
        token = PasswordResetToken.objects.create(
            user=user,
            token=token_string,
            expires_at=timezone.now() + timezone.timedelta(hours=24)
        )
        
        reset_url = f"{settings.SITE_URL}/password-reset-confirm/?uid={user.id}&token={token.token}"
        
        try:
            context = {'user': user, 'reset_url': reset_url}
            html_message = render_to_string('dojo/emails/password_reset_email.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject='Reset Your Revision Dojo Password',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as email_error:
            logger.error(f"Failed to send password reset email: {email_error}")
        
        return JsonResponse({'message': 'Password reset link sent to your email'}, status=200)
        
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        return JsonResponse({'error': 'An error occurred. Please try again.'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_password_reset_confirm(request):
    try:
        data = json.loads(request.body)
        uid = data.get('uid')
        token_str = data.get('token')
        new_password = data.get('new_password')
        
        if not uid or not token_str or not new_password:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        try:
            user = User.objects.get(id=int(uid))
        except (User.DoesNotExist, ValueError):
            return JsonResponse({'error': 'Invalid user'}, status=400)
        
        try:
            token = PasswordResetToken.objects.get(user=user, token=token_str, used=False)
        except PasswordResetToken.DoesNotExist:
            return JsonResponse({'error': 'Invalid or expired reset token'}, status=400)
        
        if not token.is_valid():
            return JsonResponse({'error': 'Reset link has expired. Please request a new one.'}, status=400)
        
        if len(new_password) < 6:
            return JsonResponse({'error': 'Password must be at least 6 characters'}, status=400)
        
        user.password = make_password(new_password)
        user.save()
        
        token.used = True
        token.save()
        
        return JsonResponse({'message': 'Password reset successful'}, status=200)
        
    except Exception as e:
        logger.error(f"Password reset confirm error: {e}")
        return JsonResponse({'error': 'An error occurred. Please try again.'}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class HomeView(View):
    def get(self, request):
        if request.user.is_authenticated:
            if request.user.role == 'student':
                return redirect('dojo:game')
            elif request.user.role == 'tutor':
                return redirect('dojo:tutor_dashboard')
            elif request.user.role == 'admin':
                return redirect('dojo:admin_dashboard')
        return render(request, 'dojo/home.html')


class LoginView(View):
    def get(self, request):
        return render(request, 'dojo/login.html')


class RegisterView(View):
    def get(self, request):
        return render(request, 'dojo/register.html')


class StudentAppView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        return render(request, "dojo/game.html")


class StudentPortalView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        return render(request, "dojo/student_portal.html")


class TutorDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'tutor':
            return redirect('dojo:home')
        return render(request, "dojo/tutor.html")


class AdminLoginView(View):
    def get(self, request):
        if request.user.is_authenticated and request.user.role == 'admin':
            return redirect('dojo:admin_dashboard')
        return render(request, 'dojo/admin_login.html')


class AdminDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'admin':
            return redirect('dojo:home')
        return render(request, "dojo/admin_dashboard.html")


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("dojo:home")


class LegacyAdminAppView(View):
    def get(self, request):
        return redirect('dojo:admin_login')


class ParentDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'parent':
            return redirect('dojo:home')
        return render(request, 'dojo/parent_dashboard.html')


class CBCStudentDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        if not request.user.curriculum:
            return redirect('dojo:setup_profile')
        return render(request, 'dojo/cbc_dashboard.html')


class IGCSEDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        if not request.user.curriculum:
            return redirect('dojo:setup_profile')
        return render(request, 'dojo/igcse_dashboard.html')


class EightFourFourDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        if not request.user.curriculum:
            return redirect('dojo:setup_profile')
        return render(request, 'dojo/844_dashboard.html')


class SetupProfileView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'student':
            return redirect('dojo:home')
        return render(request, 'dojo/setup_profile.html')


class ParentLoginView(View):
    def get(self, request):
        if request.user.is_authenticated and request.user.role == 'parent':
            return redirect('dojo:parent_dashboard')
        return render(request, 'dojo/parent_login.html')


# ─────────────────────────────────────────────────────────────────────────────
# AUTH API
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_register(request):
    data = json_body(request)
    
    logger.info(f"Registration request data: {data}")
    
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    role = data.get("role", "student")
    county = data.get("county", "")
    school = data.get("school", "")
    spec = data.get("spec", "")
    curriculum = data.get("curriculum", "")
    grade = data.get("grade", "")
    
    parent_email = data.get("parent_email", "").strip().lower()
    parent_phone = data.get("parent_phone", "").strip()

    if not email or not password or not first_name:
        return err("Email, password, and first name are required")
    
    if len(password) < 6:
        return err("Password must be at least 6 characters")
    
    if role not in ("student", "parent"):
        return err("Invalid role")
    
    if role == "student":
        if not parent_email:
            return err("Parent/Guardian email is required")
        
        if not parent_phone:
            return err("Parent/Guardian phone number is required")
        
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, parent_email):
            return err("Please enter a valid parent email address")
        
        phone_digits = re.sub(r'\D', '', parent_phone)
        if len(phone_digits) < 10:
            return err("Please enter a valid phone number (at least 10 digits)")
        
        if User.objects.filter(email=email).exists():
            return err("Email already registered")
    
    try:
        with transaction.atomic():
            if role == "student":
                normalized_grade = grade
                if grade:
                    grade_lower = grade.lower().strip()
                    grade_clean = grade_lower.replace('_', ' ').strip()
                    grade_clean = re.sub(r'\([^)]*\)', '', grade_clean).strip()
                    numbers = re.findall(r'\d+', grade_clean)
                    grade_number = numbers[0] if numbers else None
                    
                    if curriculum == 'cbc':
                        if grade_number:
                            normalized_grade = f"Grade {grade_number}"
                        elif 'grade' in grade_clean:
                            parts = grade_clean.split()
                            for i, part in enumerate(parts):
                                if 'grade' in part.lower():
                                    parts[i] = 'Grade'
                            normalized_grade = ' '.join(parts).title()
                        else:
                            normalized_grade = grade_clean.title()
                            if grade_number and 'grade' not in normalized_grade.lower():
                                normalized_grade = f"Grade {grade_number}"
                    elif curriculum == '844':
                        if grade_number:
                            normalized_grade = f"Form {grade_number}"
                        elif 'form' in grade_clean:
                            parts = grade_clean.split()
                            for i, part in enumerate(parts):
                                if 'form' in part.lower():
                                    parts[i] = 'Form'
                            normalized_grade = ' '.join(parts).title()
                        else:
                            normalized_grade = grade_clean.title()
                            if grade_number and 'form' not in normalized_grade.lower():
                                normalized_grade = f"Form {grade_number}"
                    elif curriculum == 'igcse':
                        if grade_number:
                            normalized_grade = f"Year {grade_number}"
                        elif 'year' in grade_clean:
                            parts = grade_clean.split()
                            for i, part in enumerate(parts):
                                if 'year' in part.lower():
                                    parts[i] = 'Year'
                            normalized_grade = ' '.join(parts).title()
                        else:
                            normalized_grade = grade_clean.title()
                            if grade_number and 'year' not in normalized_grade.lower():
                                normalized_grade = f"Year {grade_number}"
                    else:
                        normalized_grade = grade_clean.title()
                        if grade_number and 'grade' not in normalized_grade.lower() and 'form' not in normalized_grade.lower() and 'year' not in normalized_grade.lower():
                            normalized_grade = f"Grade {grade_number}"
                    
                    logger.info(f"Grade normalized: '{grade}' -> '{normalized_grade}' for curriculum '{curriculum}'")
                
                student_username = email
                counter = 1
                while User.objects.filter(username=student_username).exists():
                    student_username = f"{email.split('@')[0]}{counter}@{email.split('@')[1]}"
                    counter += 1
                
                user = User.objects.create_user(
                    username=student_username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    county=county,
                    school=school,
                    curriculum=curriculum if curriculum else None,
                    grade=normalized_grade if normalized_grade else None,
                )
                
                logger.info(f"Student account created: {user.email}")
                
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
                
                # Create subscription (inactive until paid)
                UserSubscription.objects.get_or_create(
                    user=user,
                    defaults={'status': 'inactive'}
                )
                
                # Create 7-day trial for multiplication game (Blue belt+)
                UserTrial.objects.get_or_create(
                    user=user,
                    trial_type='multiplication',
                    defaults={
                        'end_date': timezone.now() + timedelta(days=7),
                        'used': False
                    }
                )
                
                # Create 7-day trial for curriculum content (CBC/8-4-4/IGCSE)
                UserTrial.objects.get_or_create(
                    user=user,
                    trial_type='curriculum',
                    defaults={
                        'end_date': timezone.now() + timedelta(days=7),
                        'used': False
                    }
                )
                
                # Handle parent account linking
                parent_account = None
                is_new_parent = False
                
                try:
                    parent_account = User.objects.get(email=parent_email, role='parent')
                except User.DoesNotExist:
                    parent_username = parent_email
                    counter = 1
                    while User.objects.filter(username=parent_username).exists():
                        parent_username = f"{parent_email.split('@')[0]}{counter}@{parent_email.split('@')[1]}"
                        counter += 1
                    
                    parent_account = User.objects.create_user(
                        username=parent_username,
                        email=parent_email,
                        password=parent_phone,
                        first_name=f"Parent of {first_name}",
                        last_name=last_name if last_name else "Guardian",
                        role='parent',
                        county=county,
                        phone=parent_phone,
                        is_active=True
                    )
                    is_new_parent = True
                except User.MultipleObjectsReturned:
                    parent_account = User.objects.filter(email=parent_email, role='parent').first()
                
                ParentStudentLink.objects.get_or_create(
                    parent=parent_account,
                    student=user,
                    defaults={'relationship': 'guardian', 'can_pay': True, 'can_view': True}
                )
                
                try:
                    send_welcome_email(user, password, role)
                    if is_new_parent:
                        send_parent_welcome_email(parent_account, user, parent_phone)
                    else:
                        send_parent_child_linked_email(parent_account, user)
                except Exception as email_error:
                    logger.error(f"Failed to send email: {email_error}")
                
                login(request, user)
                return ok(user=user_json(user))
                
            else:
                if User.objects.filter(email=email).exists():
                    return err("Email already registered")
                
                parent_username = email
                counter = 1
                while User.objects.filter(username=parent_username).exists():
                    parent_username = f"{email.split('@')[0]}{counter}@{email.split('@')[1]}"
                    counter += 1
                
                user = User.objects.create_user(
                    username=parent_username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    county=county,
                )
                
                try:
                    send_welcome_email(user, password, role)
                except Exception as email_error:
                    logger.error(f"Failed to send welcome email: {email_error}")
                
                login(request, user)
                return ok(user=user_json(user))
                
    except IntegrityError as e:
        logger.error(f"Integrity error during registration: {e}")
        return err("Registration failed due to duplicate data", 400)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return err(f"Registration failed: {str(e)}", 500)


def send_welcome_email(user, plain_password, role):
    try:
        login_url = f"{settings.SITE_URL}/login/"
        context = {
            'user': user,
            'plain_password': plain_password,
            'role': role,
            'login_url': login_url,
            'site_url': settings.SITE_URL,
            'trial_days': 7,
        }
        html_message = render_to_string('dojo/emails/welcome_email.html', context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject=f'Welcome to Revision Dojo, {user.first_name}!',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")
        raise


def send_parent_welcome_email(parent_user, student_user, temp_password):
    try:
        login_url = f"{settings.SITE_URL}/parent-login/"
        dashboard_url = f"{settings.SITE_URL}/parent-dashboard/"
        context = {
            'parent': parent_user,
            'student': student_user,
            'temp_password': temp_password,
            'login_url': login_url,
            'dashboard_url': dashboard_url,
            'site_url': settings.SITE_URL,
        }
        html_message = render_to_string('dojo/emails/parent_welcome_email.html', context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject=f'Your Parent Account for {student_user.first_name}\'s Revision Dojo Journey',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send parent welcome email: {e}")
        raise


def send_parent_child_linked_email(parent_user, student_user):
    try:
        dashboard_url = f"{settings.SITE_URL}/parent-dashboard/"
        context = {
            'parent': parent_user,
            'student': student_user,
            'dashboard_url': dashboard_url,
            'site_url': settings.SITE_URL,
        }
        html_message = render_to_string('dojo/emails/parent_child_linked_email.html', context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject=f'New Student Linked to Your Revision Dojo Account',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send parent child linked email: {e}")
        raise


@csrf_exempt
@require_POST
def api_login(request):
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role")
    remember_me = data.get("remember_me", False)

    if not email or not password:
        return err("Email and password required")

    user = authenticate(request, username=email, password=password)
    
    if not user:
        try:
            user_obj = User.objects.filter(email=email).first()
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=password)
        except Exception as e:
            logger.error(f"Error during login: {e}")

    if not user:
        return err("Invalid email or password", 401)
    if not user.is_active:
        return err("Account is suspended", 401)
    if role and user.role != role:
        return err(f"No {role} account found with these credentials", 401)

    if user.role == 'student' and user.grade:
        old_grade = user.grade
        normalized_grade = None
        needs_normalization = False
        
        if '_' in old_grade or '(' in old_grade or ')' in old_grade:
            needs_normalization = True
        if 'igcse' in old_grade.lower() and 'year' not in old_grade.lower():
            needs_normalization = True
        if 'cbc' in old_grade.lower() and 'grade' not in old_grade.lower():
            needs_normalization = True
        if '844' in old_grade and 'form' not in old_grade.lower():
            needs_normalization = True
        
        if needs_normalization:
            grade_clean = old_grade.replace('_', ' ').strip()
            grade_clean = re.sub(r'\([^)]*\)', '', grade_clean).strip()
            grade_clean = re.sub(r'\s+', ' ', grade_clean).strip()
            numbers = re.findall(r'\d+', grade_clean)
            grade_number = numbers[0] if numbers else None
            
            if user.curriculum == 'cbc':
                if grade_number:
                    normalized_grade = f"Grade {grade_number}"
                elif 'grade' in grade_clean.lower():
                    parts = grade_clean.split()
                    for i, part in enumerate(parts):
                        if 'grade' in part.lower():
                            parts[i] = 'Grade'
                    normalized_grade = ' '.join(parts).title()
                else:
                    normalized_grade = grade_clean.title()
            elif user.curriculum == '844':
                if grade_number:
                    normalized_grade = f"Form {grade_number}"
                elif 'form' in grade_clean.lower():
                    parts = grade_clean.split()
                    for i, part in enumerate(parts):
                        if 'form' in part.lower():
                            parts[i] = 'Form'
                    normalized_grade = ' '.join(parts).title()
                else:
                    normalized_grade = grade_clean.title()
            elif user.curriculum == 'igcse':
                if grade_number:
                    normalized_grade = f"Year {grade_number}"
                elif 'year' in grade_clean.lower():
                    parts = grade_clean.split()
                    for i, part in enumerate(parts):
                        if 'year' in part.lower():
                            parts[i] = 'Year'
                    normalized_grade = ' '.join(parts).title()
                else:
                    normalized_grade = grade_clean.title()
            
            if normalized_grade and normalized_grade != old_grade:
                user.grade = normalized_grade
                user.save(update_fields=['grade'])
                logger.info(f"Grade normalized: '{old_grade}' -> '{normalized_grade}'")

    if user.role == 'parent' and user.phone:
        old_phone = user.phone
        clean_phone = re.sub(r'\D', '', old_phone)
        if clean_phone != old_phone:
            user.phone = clean_phone
            user.save(update_fields=['phone'])

    login(request, user)
    
    if remember_me:
        request.session.set_expiry(30 * 24 * 60 * 60)
    else:
        request.session.set_expiry(0)
    
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


@csrf_exempt
@require_POST
def api_setup_profile(request):
    if not request.user.is_authenticated or request.user.role != 'student':
        return err("Unauthorized", 401)
    
    data = json_body(request)
    curriculum = data.get('curriculum')
    grade = data.get('grade')
    
    if not curriculum or not grade:
        return err("Curriculum and grade are required")
    
    if curriculum not in ['cbc', '844', 'igcse']:
        return err("Invalid curriculum")
    
    user = request.user
    user.curriculum = curriculum
    user.grade = grade
    user.save()
    
    return ok(message="Profile updated successfully")


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
    bp = belt_progress_json(request.user.belt_progress.all())
    return ok(belts=bp)


@require_GET
@require_role("student")
def api_student_belt_progress(request):
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
            "requires_subscription": belt_id != "white" and belt_id != "yellow"
        })
    
    active_belt_idx = user.current_belt_idx
    active_belt_id = user.active_belt_id
    
    try:
        subscription = UserSubscription.objects.get(user=user)
        has_active_subscription = subscription.has_premium_access() and subscription.status == 'active'
    except UserSubscription.DoesNotExist:
        has_active_subscription = False
    
    return ok(
        belts=belt_progress_data,
        active_belt_id=active_belt_id,
        active_belt_idx=active_belt_idx,
        has_active_subscription=has_active_subscription,
    )


@require_GET
@require_role("student")
def api_student_belt_details(request, belt_id):
    if belt_id not in BELT_ORDER:
        return err("Invalid belt_id")
    
    belt_details = BELT_DETAILS.get(belt_id, {})
    belt_progress = BeltProgress.objects.filter(user=request.user, belt_id=belt_id).first()
    
    requires_subscription = belt_id != "white" and belt_id != "yellow"
    
    has_access = False
    if not requires_subscription:
        has_access = True
    else:
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            if subscription.has_premium_access() and subscription.status == 'active':
                has_access = True
        except UserSubscription.DoesNotExist:
            pass
        
        if not has_access:
            try:
                trial = UserTrial.objects.get(user=request.user, trial_type='multiplication')
                if trial.is_valid():
                    has_access = True
            except UserTrial.DoesNotExist:
                pass
    
    return ok(
        belt_id=belt_id,
        name=dict(BELT_CHOICES).get(belt_id, belt_id),
        tables=belt_details.get("tables", []),
        minutes=belt_details.get("minutes", 5),
        emoji=belt_details.get("emoji", "⬜"),
        requires_subscription=requires_subscription,
        has_access=has_access,
        color={
            "white": "#d0d0d0", "yellow": "#f9a825", "blue": "#1565c0",
            "red": "#c62828", "black": "#1a1a1a", "brown": "#4e342e",
            "purple": "#6a1b9a", "gold": "#b8860b", "master": "#1a237e"
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
    logger.info(f"=== BELT UPDATE CALLED ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"User: {request.user}")
    
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
    logger.info(f"Belt update: user={request.user.email}, belt_id={belt_id}")
    
    if belt_id not in BELT_ORDER:
        return JsonResponse({"error": f"Invalid belt_id: {belt_id}"}, status=400)
    
    if belt_id not in ["white", "yellow"]:
        has_access = False
        
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            if subscription.has_premium_access() and subscription.status == 'active':
                has_access = True
        except UserSubscription.DoesNotExist:
            pass
        
        if not has_access:
            try:
                trial = UserTrial.objects.get(user=request.user, trial_type='multiplication')
                if trial.is_valid():
                    has_access = True
            except UserTrial.DoesNotExist:
                pass
        
        if not has_access:
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
    user = request.user
    
    stats = user.training_sessions.aggregate(
        total_sessions=Count("id"),
        total_correct=Coalesce(Sum("correct"), 0),
        total_questions=Coalesce(Sum("total_q"), 0),
        avg_accuracy=Coalesce(Avg("accuracy"), 0.0),
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
        avg_accuracy=round(float(stats["avg_accuracy"] or 0) * 100, 1),
        total_passed=stats["total_passed"] or 0,
        belts_passed=belt_stats["belts_passed"] or 0,
        belts_active=belt_stats["belts_active"] or 0,
        badges_count=badge_count,
        streak=streak
    )


@require_GET
@require_role("student")
def api_student_recent_sessions(request):
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
        passed_belts = list(u.belt_progress.filter(passed=True).values_list("belt_id", flat=True))
        highest = max((BELT_ORDER.index(b) for b in passed_belts if b in BELT_ORDER), default=-1)
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
        qs = qs.filter(Q(first_name__icontains=name_q) | Q(last_name__icontains=name_q))
    if county_q:
        qs = qs.filter(county__iexact=county_q)
    if spec_q:
        qs = qs.filter(spec__icontains=spec_q)

    tutors = []
    for t in qs[:50]:
        student_count = TutorRequest.objects.filter(tutor=t, status="accepted").values("student").distinct().count()
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

    existing = TutorRequest.objects.filter(student=request.user, tutor=tutor).first()
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

    req = TutorRequest.objects.create(student=request.user, tutor=tutor, message=message, status="pending")
    return ok(request_id=req.pk)


@require_GET
@require_role("student")
def api_my_requests(request):
    reqs = TutorRequest.objects.filter(student=request.user).select_related("tutor").order_by("-created_at")
    data = [{"id": r.pk, "tutor_id": r.tutor.pk, "tutor_name": r.tutor.get_full_name(), "status": r.status, "created_at": r.created_at.isoformat()} for r in reqs]
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
    return ok(user=user_json(request.user))


@require_GET
@require_role("tutor")
def api_tutor_requests(request):
    reqs = TutorRequest.objects.filter(tutor=request.user).select_related("student").order_by("-created_at")
    data = [{"id": r.pk, "student_id": r.student.pk, "student_name": r.student.get_full_name(), "school": r.student.school, "county": r.student.county, "status": r.status, "message": r.message, "created_at": r.created_at.isoformat()} for r in reqs]
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

    updated = TutorRequest.objects.filter(pk=request_id, tutor=request.user).update(status=status)
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

ADMIN_CREDENTIALS = {
    "mesh@timesdojo.com": "Mesh@2026",
    "antoh@timesdojo.com": "Antoh@2026",
}

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
    
    login_email = email
    if email in FRIENDLY_LOGINS:
        login_email = FRIENDLY_LOGINS[email]
    elif "@" not in email and email.lower() in ["mesh", "antoh"]:
        login_email = f"{email.lower()}@timesdojo.com"
    
    if login_email in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[login_email] == password:
        try:
            admin_user = User.objects.get(email=login_email, role="admin")
        except User.DoesNotExist:
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
        login(request, admin_user)
        return ok(user=user_json(admin_user))
    
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

    students = []
    for u in qs:
        sessions = TrainingSession.objects.filter(user=u)
        session_count = sessions.count()
        total_correct = sessions.aggregate(total=Sum('correct'))['total'] or 0
        avg_accuracy = sessions.aggregate(avg=Avg('accuracy'))['avg'] or 0
        
        passed_belts = BeltProgress.objects.filter(user=u, passed=True).values_list('belt_id', flat=True)
        highest = -1
        for b in passed_belts:
            if b in BELT_ORDER:
                idx = BELT_ORDER.index(b)
                if idx > highest:
                    highest = idx
        
        streak_obj = Streak.objects.filter(user=u).first()
        
        students.append({
            "id": u.id,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "role": u.role,
            "county": u.county or "",
            "school": u.school or "",
            "spec": u.spec or "",
            "is_paid": u.is_paid,
            "date_joined": u.date_joined.isoformat() if u.date_joined else None,
            "created_at": u.date_joined.isoformat() if u.date_joined else None,
            "curriculum": getattr(u, 'curriculum', None),
            "grade": getattr(u, 'grade', None),
            "sessions": session_count,
            "total_correct": total_correct,
            "accuracy": round(avg_accuracy * 100, 1),
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

    data = []
    for t in tutors:
        data.append({
            "id": t.id,
            "email": t.email,
            "first_name": t.first_name,
            "last_name": t.last_name,
            "role": t.role,
            "county": t.county or "",
            "school": t.school or "",
            "spec": t.spec or "",
            "is_paid": t.is_paid,
            "date_joined": t.date_joined.isoformat() if t.date_joined else None,
            "created_at": t.date_joined.isoformat() if t.date_joined else None,
            "sessions": t.session_count,
            "students": t.student_count,
            "pending_requests": t.pending_requests,
            "rating": 4.7,
        })
    
    return ok(tutors=data)


@require_GET
@admin_only
def api_admin_belts(request):
    result = []
    for belt_id in BELT_ORDER:
        agg = TrainingSession.objects.filter(belt_id=belt_id).aggregate(
            pass_rate=Avg(Cast("passed", output_field=IntegerField())),
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
        .annotate(
            students=Count("id"), 
            paid_count=Sum(Cast("is_paid", output_field=IntegerField()))
        )
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
# CONTENT MANAGEMENT API (PDF to Quiz System)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_role("admin")
def api_extract_text_from_pdf(request):
    """Extract text from uploaded PDF and detect questions"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    pdf_file = request.FILES.get('pdf')
    if not pdf_file:
        return JsonResponse({'error': 'No PDF file provided'}, status=400)
    
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        full_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        questions = detect_questions_from_text(full_text)
        
        return JsonResponse({
            'success': True,
            'extracted_text': full_text[:5000],
            'detected_questions': questions,
            'question_count': len(questions),
            'full_text_length': len(full_text)
        })
        
    except Exception as e:
        logger.error(f"PDF processing failed: {e}")
        return JsonResponse({'error': f'PDF processing failed: {str(e)}'}, status=500)


@csrf_exempt
@require_role("admin")
def api_save_content(request):
    """Save content with questions"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        title = request.POST.get('title')
        content_type = request.POST.get('content_type', 'quiz')
        curriculum_id = request.POST.get('curriculum')
        grade_id = request.POST.get('grade')
        subject_id = request.POST.get('subject')
        topic_id = request.POST.get('topic')
        difficulty = request.POST.get('difficulty', 1)
        time_limit = request.POST.get('time_limit', 0)
        status = request.POST.get('status', 'draft')
        questions_json = request.POST.get('questions', '[]')
        
        if not title:
            return JsonResponse({'error': 'Title required'}, status=400)
        
        with transaction.atomic():
            content = ContentItem.objects.create(
                title=title,
                content_type=content_type,
                difficulty=int(difficulty),
                time_limit_minutes=int(time_limit),
                status=status,
                created_by=request.user,
            )
            
            if curriculum_id and curriculum_id != '':
                content.curriculum_id = int(curriculum_id)
            if grade_id and grade_id != '':
                content.grade_id = int(grade_id)
            if subject_id and subject_id != '':
                content.subject_id = int(subject_id)
            if topic_id and topic_id != '':
                content.topic_id = int(topic_id)
            
            pdf_file = request.FILES.get('pdf')
            if pdf_file:
                content.source_pdf = pdf_file
                try:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    full_text = ""
                    for page in pdf_reader.pages:
                        text = page.extract_text()
                        if text:
                            full_text += text + "\n"
                    content.extracted_text = full_text[:10000]
                except:
                    pass
            
            content.save()
            
            questions = json.loads(questions_json)
            total_marks = 0
            
            for i, q_data in enumerate(questions):
                q_type = q_data.get('type', 'mcq')
                options = q_data.get('options', ['', '', '', ''])
                marks = int(q_data.get('marks', 1))
                total_marks += marks
                
                Question.objects.create(
                    content_item=content,
                    question_text=q_data.get('text', ''),
                    question_type=q_type,
                    option_a=options[0] if len(options) > 0 else '',
                    option_b=options[1] if len(options) > 1 else '',
                    option_c=options[2] if len(options) > 2 else '',
                    option_d=options[3] if len(options) > 3 else '',
                    correct_answer=q_data.get('correct', ''),
                    marks=marks,
                    explanation=q_data.get('explanation', ''),
                    order=i,
                    requires_manual_grading=(q_type == 'essay'),
                    difficulty=int(q_data.get('difficulty', difficulty)),
                    requires_upload=q_data.get('requires_upload', False),
                )
            
            content.total_marks = total_marks
            content.save(update_fields=['total_marks'])
            
            if status == 'published':
                content.published_at = timezone.now()
                content.save(update_fields=['published_at'])
        
        return JsonResponse({
            'success': True,
            'content_id': content.id,
            'message': 'Content saved successfully',
            'question_count': len(questions)
        })
        
    except Exception as e:
        logger.error(f"Error saving content: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
@require_role("admin")
def api_list_content(request):
    """List all content with filters"""
    content = ContentItem.objects.select_related('curriculum', 'grade', 'subject').all()
    
    curriculum = request.GET.get('curriculum')
    if curriculum and curriculum != '':
        content = content.filter(curriculum_id=int(curriculum))
    
    grade = request.GET.get('grade')
    if grade and grade != '':
        content = content.filter(grade_id=int(grade))
    
    subject = request.GET.get('subject')
    if subject and subject != '':
        content = content.filter(subject_id=int(subject))
    
    content_type = request.GET.get('content_type')
    if content_type and content_type != '':
        content = content.filter(content_type=content_type)
    
    status = request.GET.get('status')
    if status and status != '':
        content = content.filter(status=status)
    
    content = content.annotate(question_count=Count('questions'))
    
    items = []
    for c in content:
        items.append({
            'id': c.id,
            'title': c.title,
            'content_type': c.content_type,
            'content_type_display': c.get_content_type_display(),
            'curriculum': c.curriculum.name if c.curriculum else None,
            'grade': c.grade.name if c.grade else None,
            'subject': c.subject.name if c.subject else None,
            'question_count': c.question_count,
            'attempt_count': c.attempt_count,
            'status': c.status,
            'status_display': c.get_status_display(),
            'created_at': c.created_at.isoformat(),
        })
    
    return JsonResponse({'items': items})


@require_GET
@require_role("admin")
def api_get_content_detail(request, content_id):
    """Get content details including all questions"""
    content = get_object_or_404(ContentItem, id=content_id)
    
    questions = []
    for q in content.questions.all():
        questions.append({
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'options': q.get_options_list(),
            'correct_answer': q.correct_answer,
            'marks': q.marks,
            'explanation': q.explanation,
            'order': q.order,
            'times_answered': q.times_answered,
            'accuracy': q.get_accuracy(),
            'requires_upload': getattr(q, 'requires_upload', False),
        })
    
    return JsonResponse({
        'id': content.id,
        'title': content.title,
        'description': content.description,
        'content_type': content.content_type,
        'curriculum_id': content.curriculum_id,
        'grade_id': content.grade_id,
        'subject_id': content.subject_id,
        'topic_id': content.topic_id,
        'difficulty': content.difficulty,
        'time_limit': content.time_limit_minutes,
        'total_marks': content.total_marks,
        'status': content.status,
        'questions': questions,
        'created_at': content.created_at.isoformat(),
    })


@csrf_exempt
@require_role("admin")
def api_delete_content(request, content_id):
    """Delete content and all associated questions"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    
    content = get_object_or_404(ContentItem, id=content_id)
    content.delete()
    
    return JsonResponse({'success': True})


@csrf_exempt
@require_role("admin")
def api_update_content_status(request, content_id):
    """Update content status (publish/unpublish)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json_body(request)
    content = get_object_or_404(ContentItem, id=content_id)
    new_status = data.get('status')
    
    if new_status not in ['draft', 'published', 'archived']:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    content.status = new_status
    if new_status == 'published' and not content.published_at:
        content.published_at = timezone.now()
    content.save()
    
    return JsonResponse({'success': True, 'status': content.status})


# =============================================================================
# CURRICULUM DATA API VIEWS
# =============================================================================

@require_GET
@require_role("admin")
def api_list_curriculums(request):
    """List all curriculums with grades"""
    curriculums = Curriculum.objects.filter(is_active=True).prefetch_related('grades')
    
    data = []
    for c in curriculums:
        data.append({
            'id': c.id,
            'name': c.name,
            'code': c.code,
            'description': c.description,
            'is_active': c.is_active,
            'grades': [{'id': g.id, 'name': g.name, 'level_order': g.level_order} 
                      for g in c.grades.filter(is_active=True).order_by('level_order')],
        })
    
    return JsonResponse({'curriculums': data})


@require_GET
@require_role("admin")
def api_list_subjects(request):
    """List all subjects with topics"""
    subjects = Subject.objects.filter(is_active=True).prefetch_related('topics')
    
    data = [{
        'id': s.id, 
        'name': s.name, 
        'code': s.code,
        'description': s.description,
        'topics': [{'id': t.id, 'name': t.name, 'order': t.order} for t in s.topics.filter(is_active=True)]
    } for s in subjects]
    
    return JsonResponse({'subjects': data})


@require_GET
@require_role("admin")
def api_list_topics(request, subject_id):
    """List topics for a subject"""
    topics = Topic.objects.filter(subject_id=subject_id, is_active=True)
    
    data = [{'id': t.id, 'name': t.name, 'order': t.order} for t in topics]
    
    return JsonResponse({'topics': data})


# =============================================================================
# CURRICULUM MANAGEMENT FULL CRUD API
# =============================================================================

@csrf_exempt
@require_role("admin")
def api_add_curriculum(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json_body(request)
    name = data.get('name', '').strip()
    code = data.get('code', '').strip().upper()
    description = data.get('description', '')
    
    if not name or not code:
        return err("Name and code are required", 400)
    
    if Curriculum.objects.filter(code=code).exists():
        return err(f"Curriculum with code '{code}' already exists", 400)
    
    curriculum = Curriculum.objects.create(
        name=name,
        code=code,
        description=description,
        is_active=True
    )
    
    return JsonResponse({
        'id': curriculum.id,
        'name': curriculum.name,
        'code': curriculum.code,
        'description': curriculum.description,
        'is_active': curriculum.is_active
    })


@csrf_exempt
@require_role("admin")
def api_update_curriculum(request, curriculum_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
    except Curriculum.DoesNotExist:
        return err("Curriculum not found", 404)
    
    data = json_body(request)
    
    if 'name' in data:
        curriculum.name = data['name'].strip()
    if 'code' in data:
        curriculum.code = data['code'].strip().upper()
    if 'description' in data:
        curriculum.description = data['description']
    if 'is_active' in data:
        curriculum.is_active = data['is_active']
    
    curriculum.save()
    
    return JsonResponse({
        'id': curriculum.id,
        'name': curriculum.name,
        'code': curriculum.code,
        'description': curriculum.description,
        'is_active': curriculum.is_active
    })


@csrf_exempt
@require_role("admin")
def api_delete_curriculum(request, curriculum_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
        curriculum.delete()
        return JsonResponse({'ok': True, 'message': 'Curriculum deleted successfully'})
    except Curriculum.DoesNotExist:
        return err("Curriculum not found", 404)


@csrf_exempt
@require_role("admin")
def api_get_curriculum_detail(request, curriculum_id):
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
        grades = Grade.objects.filter(curriculum=curriculum, is_active=True)
        
        return JsonResponse({
            'id': curriculum.id,
            'name': curriculum.name,
            'code': curriculum.code,
            'description': curriculum.description,
            'is_active': curriculum.is_active,
            'grades': [{
                'id': g.id,
                'name': g.name,
                'level_order': g.level_order
            } for g in grades]
        })
    except Curriculum.DoesNotExist:
        return err("Curriculum not found", 404)


@csrf_exempt
@require_role("admin")
def api_add_grade(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json_body(request)
    curriculum_id = data.get('curriculum_id')
    name = data.get('name', '').strip()
    level_order = data.get('level_order', 0)
    
    if not curriculum_id or not name:
        return err("Curriculum ID and name are required", 400)
    
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
    except Curriculum.DoesNotExist:
        return err("Curriculum not found", 404)
    
    grade = Grade.objects.create(
        curriculum=curriculum,
        name=name,
        level_order=level_order,
        is_active=True
    )
    
    return JsonResponse({
        'id': grade.id,
        'name': grade.name,
        'level_order': grade.level_order,
        'curriculum_id': grade.curriculum_id
    })


@csrf_exempt
@require_role("admin")
def api_update_grade(request, grade_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        grade = Grade.objects.get(id=grade_id)
    except Grade.DoesNotExist:
        return err("Grade not found", 404)
    
    data = json_body(request)
    
    if 'name' in data:
        grade.name = data['name'].strip()
    if 'level_order' in data:
        grade.level_order = data['level_order']
    if 'is_active' in data:
        grade.is_active = data['is_active']
    
    grade.save()
    
    return JsonResponse({
        'id': grade.id,
        'name': grade.name,
        'level_order': grade.level_order,
        'curriculum_id': grade.curriculum_id
    })


@csrf_exempt
@require_role("admin")
def api_delete_grade(request, grade_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    
    try:
        grade = Grade.objects.get(id=grade_id)
        grade.delete()
        return JsonResponse({'ok': True, 'message': 'Grade deleted successfully'})
    except Grade.DoesNotExist:
        return err("Grade not found", 404)


@csrf_exempt
@require_role("admin")
def api_add_subject(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json_body(request)
    name = data.get('name', '').strip()
    code = data.get('code', '').strip().upper()
    description = data.get('description', '')
    
    if not name or not code:
        return err("Name and code are required", 400)
    
    if Subject.objects.filter(code=code).exists():
        return err(f"Subject with code '{code}' already exists", 400)
    
    subject = Subject.objects.create(
        name=name,
        code=code,
        description=description,
        is_active=True
    )
    
    return JsonResponse({
        'id': subject.id,
        'name': subject.name,
        'code': subject.code,
        'description': subject.description
    })


@csrf_exempt
@require_role("admin")
def api_update_subject(request, subject_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        return err("Subject not found", 404)
    
    data = json_body(request)
    
    if 'name' in data:
        subject.name = data['name'].strip()
    if 'code' in data:
        subject.code = data['code'].strip().upper()
    if 'description' in data:
        subject.description = data['description']
    if 'is_active' in data:
        subject.is_active = data['is_active']
    
    subject.save()
    
    return JsonResponse({
        'id': subject.id,
        'name': subject.name,
        'code': subject.code,
        'description': subject.description
    })


@csrf_exempt
@require_role("admin")
def api_delete_subject(request, subject_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    
    try:
        subject = Subject.objects.get(id=subject_id)
        subject.delete()
        return JsonResponse({'ok': True, 'message': 'Subject deleted successfully'})
    except Subject.DoesNotExist:
        return err("Subject not found", 404)


@csrf_exempt
@require_role("admin")
def api_get_subject_detail(request, subject_id):
    try:
        subject = Subject.objects.get(id=subject_id)
        topics = Topic.objects.filter(subject=subject, is_active=True)
        
        return JsonResponse({
            'id': subject.id,
            'name': subject.name,
            'code': subject.code,
            'description': subject.description,
            'topics': [{
                'id': t.id,
                'name': t.name,
                'order': t.order
            } for t in topics]
        })
    except Subject.DoesNotExist:
        return err("Subject not found", 404)


@csrf_exempt
@require_role("admin")
def api_add_topic(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json_body(request)
    subject_id = data.get('subject_id')
    name = data.get('name', '').strip()
    order = data.get('order', 0)
    
    if not subject_id or not name:
        return err("Subject ID and name are required", 400)
    
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        return err("Subject not found", 404)
    
    topic = Topic.objects.create(
        subject=subject,
        name=name,
        order=order,
        is_active=True
    )
    
    return JsonResponse({
        'id': topic.id,
        'name': topic.name,
        'order': topic.order,
        'subject_id': topic.subject_id
    })


@csrf_exempt
@require_role("admin")
def api_delete_topic(request, topic_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    
    try:
        topic = Topic.objects.get(id=topic_id)
        topic.delete()
        return JsonResponse({'ok': True, 'message': 'Topic deleted successfully'})
    except Topic.DoesNotExist:
        return err("Topic not found", 404)


# =============================================================================
# QUESTION BANK API VIEWS
# =============================================================================

@require_GET
@require_role("admin")
def api_list_questions(request):
    questions = Question.objects.select_related('content_item', 'content_item__subject').all()
    
    subject = request.GET.get('subject')
    if subject and subject != '':
        questions = questions.filter(content_item__subject_id=int(subject))
    
    difficulty = request.GET.get('difficulty')
    if difficulty and difficulty != '':
        questions = questions.filter(difficulty=int(difficulty))
    
    search = request.GET.get('search')
    if search:
        questions = questions.filter(question_text__icontains=search)
    
    questions = questions.order_by('-id')[:200]
    
    data = []
    for q in questions:
        data.append({
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'subject': q.content_item.subject.name if q.content_item.subject else None,
            'difficulty': q.difficulty,
            'marks': q.marks,
            'correct_answer': q.correct_answer[:100],
            'usage_count': q.times_answered,
            'accuracy': q.get_accuracy(),
            'requires_upload': getattr(q, 'requires_upload', False),
        })
    
    return JsonResponse({'questions': data})


# =============================================================================
# STUDENT QUIZ TAKING API VIEWS
# =============================================================================

@require_GET
@require_role("student")
def api_student_quizzes(request):
    user = request.user
    
    has_curriculum_access = False
    try:
        trial = UserTrial.objects.get(user=user, trial_type='curriculum')
        if trial.is_valid():
            has_curriculum_access = True
    except UserTrial.DoesNotExist:
        pass
    
    if not has_curriculum_access:
        try:
            subscription = UserSubscription.objects.get(user=user)
            if subscription.has_premium_access() and subscription.status == 'active':
                has_curriculum_access = True
        except UserSubscription.DoesNotExist:
            pass
    
    if not has_curriculum_access:
        return JsonResponse({'quizzes': [], 'requires_subscription': True})
    
    content = ContentItem.objects.filter(status='published')
    
    if user.curriculum:
        content = content.filter(
            Q(curriculum__code__iexact=user.curriculum) |
            Q(curriculum__code__iexact=user.curriculum.upper()) |
            Q(curriculum__code__iexact=user.curriculum.lower()) |
            Q(curriculum__name__iexact=user.curriculum) |
            Q(curriculum__name__icontains=user.curriculum)
        )
    
    if user.grade:
        student_grade_raw = user.grade
        student_grade_variations = []
        student_grade_variations.append(student_grade_raw)
        student_grade_variations.append(student_grade_raw.lower())
        student_grade_variations.append(student_grade_raw.replace('_', ' '))
        student_grade_variations.append(student_grade_raw.replace('_', ''))
        student_grade_variations.append(student_grade_raw.replace('_', ' ').title())
        
        numbers = re.findall(r'\d+', student_grade_raw)
        if numbers:
            student_grade_variations.append(numbers[0])
        
        student_grade_variations.append(student_grade_raw.replace('(igcse)', '').replace('_', ' ').strip())
        student_grade_variations.append(student_grade_raw.replace('_', ' ').replace('(igcse)', '').strip().title())
        
        if 'grade' in student_grade_raw.lower():
            grade_num = re.findall(r'\d+', student_grade_raw)
            if grade_num:
                student_grade_variations.append(f"Grade {grade_num[0]}")
                student_grade_variations.append(f"grade_{grade_num[0]}")
        
        if 'form' in student_grade_raw.lower():
            form_num = re.findall(r'\d+', student_grade_raw)
            if form_num:
                student_grade_variations.append(f"Form {form_num[0]}")
                student_grade_variations.append(f"form_{form_num[0]}")
        
        student_grade_variations = list(set([v for v in student_grade_variations if v]))
        
        grade_filter = Q(grade__isnull=True)
        for variation in student_grade_variations:
            grade_filter |= Q(grade__name__iexact=variation)
            grade_filter |= Q(grade__name__icontains=variation)
        
        content = content.filter(grade_filter)
    
    content = content.select_related('curriculum', 'grade', 'subject', 'topic')
    content = content.annotate(question_count=Count('questions'))
    
    data = []
    for c in content:
        attempt = StudentQuizAttempt.objects.filter(user=user, content_item=c).first()
        
        data.append({
            'id': c.id,
            'title': c.title,
            'description': c.description,
            'content_type': c.content_type,
            'content_type_display': c.get_content_type_display(),
            'curriculum': c.curriculum.name if c.curriculum else None,
            'grade': c.grade.name if c.grade else None,
            'subject': c.subject.name if c.subject else None,
            'topic': c.topic.name if c.topic else None,
            'difficulty': dict(ContentItem.DIFFICULTY_CHOICES).get(c.difficulty, 'Easy'),
            'time_limit': c.time_limit_minutes,
            'total_marks': c.total_marks,
            'question_count': c.question_count,
            'attempted': attempt is not None,
            'last_score': attempt.percentage if attempt else None,
            'attempts_count': StudentQuizAttempt.objects.filter(user=user, content_item=c).count(),
        })
    
    return JsonResponse({'quizzes': data, 'requires_subscription': False})


@require_GET
@require_role("student")
def api_student_take_quiz(request, content_id):
    has_curriculum_access = False
    user = request.user
    
    try:
        trial = UserTrial.objects.get(user=user, trial_type='curriculum')
        if trial.is_valid():
            has_curriculum_access = True
    except UserTrial.DoesNotExist:
        pass
    
    if not has_curriculum_access:
        try:
            subscription = UserSubscription.objects.get(user=user)
            if subscription.has_premium_access() and subscription.status == 'active':
                has_curriculum_access = True
        except UserSubscription.DoesNotExist:
            pass
    
    if not has_curriculum_access:
        return JsonResponse({'error': 'Premium subscription required to access curriculum content'}, status=403)
    
    content = get_object_or_404(ContentItem, id=content_id, status='published')
    
    if user.curriculum and content.curriculum:
        if content.curriculum.code != user.curriculum:
            return JsonResponse({'error': 'This quiz is not for your curriculum'}, status=403)
    
    content.view_count += 1
    content.save(update_fields=['view_count'])
    
    attempt, created = StudentQuizAttempt.objects.get_or_create(
        user=user,
        content_item=content,
        defaults={
            'max_score': content.total_marks,
            'started_at': timezone.now(),
        }
    )
    
    questions = []
    for q in content.questions.all():
        question_data = {
            'id': q.id,
            'text': q.question_text,
            'type': q.question_type,
            'marks': q.marks,
            'order': q.order,
            'requires_upload': getattr(q, 'requires_upload', False),
        }
        
        if q.question_type == 'mcq':
            question_data['options'] = q.get_options_list()
        
        questions.append(question_data)
    
    return JsonResponse({
        'quiz': {
            'id': content.id,
            'title': content.title,
            'description': content.description,
            'time_limit': content.time_limit_minutes,
            'total_marks': content.total_marks,
            'questions_count': len(questions),
        },
        'questions': questions,
        'attempt': {
            'id': attempt.id,
            'started_at': attempt.started_at.isoformat(),
            'time_remaining': content.time_limit_minutes * 60 if content.time_limit_minutes > 0 else None,
        }
    })


@csrf_exempt
@require_POST
@require_role("student")
def api_student_submit_quiz(request, content_id):
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import os
    
    user = request.user
    content = get_object_or_404(ContentItem, id=content_id, status='published')
    
    answers_json = request.POST.get('answers', '[]')
    time_taken = int(request.POST.get('time_taken', 0))
    
    try:
        answers = json.loads(answers_json)
    except json.JSONDecodeError:
        answers = []
    
    attempt = StudentQuizAttempt.objects.filter(user=user, content_item=content, completed=True).first()
    if attempt:
        return JsonResponse({'error': 'You have already completed this quiz'}, status=400)
    
    questions = list(content.questions.all())
    questions_dict = {q.id: q for q in questions}
    
    for q in questions:
        if q.requires_upload:
            file_key = f'file_q_{q.id}'
            if file_key not in request.FILES:
                return JsonResponse({
                    'error': f'Question "{q.question_text[:50]}" requires a file upload'
                }, status=400)
    
    with transaction.atomic():
        attempt, created = StudentQuizAttempt.objects.get_or_create(
            user=user,
            content_item=content,
            defaults={'max_score': content.total_marks}
        )
        
        total_score = 0
        
        for answer_data in answers:
            question_id = answer_data.get('question_id')
            user_answer = answer_data.get('answer', '')
            time_ms = answer_data.get('time_ms', 0)
            
            question = questions_dict.get(question_id)
            if not question:
                continue
            
            is_correct = False
            if question.question_type == 'mcq':
                is_correct = user_answer.strip().upper() == question.correct_answer.strip().upper()
            elif question.question_type == 'short_answer':
                is_correct = user_answer.strip().lower() == question.correct_answer.strip().lower()
            else:
                is_correct = False
                question.requires_manual_grading = True
                question.save(update_fields=['requires_manual_grading'])
            
            score_earned = question.marks if is_correct else 0
            total_score += score_earned
            
            question.times_answered += 1
            if is_correct:
                question.times_correct += 1
            question.save(update_fields=['times_answered', 'times_correct'])
            
            answer_detail = StudentAnswerDetail.objects.create(
                attempt=attempt,
                question=question,
                user_answer=user_answer,
                is_correct=is_correct,
                score_earned=score_earned,
                time_taken_ms=time_ms
            )
            
            file_key = f'file_q_{question.id}'
            if file_key in request.FILES:
                uploaded_file = request.FILES[file_key]
                ext = os.path.splitext(uploaded_file.name)[1]
                unique_filename = f"user_{user.id}_quiz_{content.id}_q_{question.id}_{timezone.now().timestamp()}{ext}"
                file_path = default_storage.save(f'quiz_attachments/{unique_filename}', uploaded_file)
                
                StudentAnswerAttachment.objects.create(
                    answer_detail=answer_detail,
                    file=file_path,
                    original_filename=uploaded_file.name,
                    file_size=uploaded_file.size,
                    file_type=uploaded_file.content_type
                )
        
        attempt.score = total_score
        attempt.percentage = (total_score / content.total_marks * 100) if content.total_marks > 0 else 0
        attempt.time_taken_seconds = time_taken
        attempt.completed = True
        attempt.completed_at = timezone.now()
        attempt.answers = answers
        attempt.save()
        
        content.attempt_count += 1
        all_attempts = StudentQuizAttempt.objects.filter(content_item=content, completed=True)
        avg_score = all_attempts.aggregate(avg=models.Avg('percentage'))['avg'] or 0
        content.average_score = avg_score
        content.save(update_fields=['attempt_count', 'average_score'])
    
    return JsonResponse({
        'success': True,
        'score': total_score,
        'max_score': content.total_marks,
        'percentage': attempt.percentage,
        'message': f'You scored {total_score} out of {content.total_marks} ({attempt.percentage:.0f}%)'
    })


@require_GET
@require_role("student")
def api_student_quiz_results(request, content_id):
    user = request.user
    content = get_object_or_404(ContentItem, id=content_id)
    
    attempt = StudentQuizAttempt.objects.filter(user=user, content_item=content, completed=True).first()
    
    if not attempt:
        return JsonResponse({'error': 'No completed attempt found'}, status=404)
    
    answers = []
    for detail in attempt.answer_details.select_related('question').all():
        attachments = []
        for att in detail.attachments.all():
            attachments.append({
                'id': att.id,
                'filename': att.original_filename,
                'size': att.file_size,
                'url': att.file.url if att.file else None,
            })
        
        answers.append({
            'question_text': detail.question.question_text,
            'user_answer': detail.user_answer,
            'correct_answer': detail.question.correct_answer,
            'is_correct': detail.is_correct,
            'score_earned': detail.score_earned,
            'max_score': detail.question.marks,
            'explanation': detail.question.explanation,
            'attachments': attachments,
        })
    
    return JsonResponse({
        'quiz': {
            'id': content.id,
            'title': content.title,
        },
        'attempt': {
            'id': attempt.id,
            'score': attempt.score,
            'max_score': attempt.max_score,
            'percentage': attempt.percentage,
            'time_taken': attempt.time_taken_seconds,
            'time_display': f"{attempt.time_taken_seconds // 60}:{attempt.time_taken_seconds % 60:02d}",
            'completed_at': attempt.completed_at.isoformat(),
        },
        'answers': answers,
    })


# ─────────────────────────────────────────────────────────────────────────────
# OTHER API ENDPOINTS (Chat, Notes, etc.)
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_unread_notifications_count(request):
    user = request.user
    unread_chats = ChatMessage.objects.filter(recipient=user, is_read=False).count()
    return ok(count=unread_chats)


@require_GET
@require_role("student")
def api_student_notes(request):
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


@require_GET
@require_role("student")
def api_student_chat_tutors(request):
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


@csrf_exempt
@require_POST
@require_role("tutor")
def api_tutor_create_note(request):
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


@require_GET
@require_role("student")
def api_student_chat_list(request):
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


@require_GET
@require_role("tutor")
def api_tutor_chat_list(request):
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
def api_student_chat(request, tutor_id):
    user = request.user
    messages = ChatMessage.objects.filter(
        (Q(sender=user, recipient_id=tutor_id) | Q(sender_id=tutor_id, recipient=user))
    ).order_by('created_at')
    
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
    user = request.user
    messages = ChatMessage.objects.filter(
        (Q(sender=user, recipient_id=student_id) | Q(sender_id=student_id, recipient=user))
    ).order_by('created_at')
    
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
def api_student_chat_with_attachments(request, tutor_id):
    if not request.user.is_authenticated or request.user.role != 'student':
        return err("Unauthorized", 401)
    
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
def api_chat_upload_file(request):
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


@csrf_exempt
@require_POST
@require_role("student", "tutor")
def api_start_video_call(request):
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
    if not request.user.is_authenticated:
        return redirect('dojo:login')
    
    meeting_link = f"https://meet.google.com/{room_name}"
    
    return render(request, 'dojo/video_call.html', {
        'room_name': room_name,
        'meeting_link': meeting_link,
        'user': request.user
    })


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_student_assignments(request):
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
    
    existing = AssignmentSubmission.objects.filter(assignment=assignment, student=user).first()
    if existing and existing.status in ['submitted', 'graded']:
        return err("You have already submitted this assignment", 400)
    
    answers = data.get('answers', [])
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
# PAYMENT API (Subscription)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_verify_payment(request):
    reference = request.GET.get('reference')
    
    if not reference:
        return err("No reference provided", 400)
    
    try:
        transaction_obj = PaymentTransaction.objects.get(reference=reference)
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
                transaction_obj.status = 'success'
                transaction_obj.completed_at = timezone.now()
                transaction_obj.paystack_response = resp_data
                transaction_obj.save()
                
                user = transaction_obj.user
                plan = transaction_obj.plan
                duration = transaction_obj.duration_days
                
                subscription, created = UserSubscription.objects.get_or_create(
                    user=user,
                    defaults={
                        'plan': plan,
                        'status': 'active',
                        'start_date': timezone.now(),
                        'end_date': timezone.now() + timedelta(days=duration),
                        'last_payment_date': timezone.now(),
                        'next_payment_date': timezone.now() + timedelta(days=duration),
                    }
                )
                
                if not created:
                    subscription.plan = plan
                    subscription.status = 'active'
                    subscription.end_date = timezone.now() + timedelta(days=duration)
                    subscription.last_payment_date = timezone.now()
                    subscription.next_payment_date = subscription.end_date
                    subscription.cancel_at_period_end = False
                    subscription.save()
                
                # Mark trials as used since user now has paid subscription
                UserTrial.objects.filter(user=user, used=False).update(used=True)
                
                user.is_paid = True
                user.save()
                
                return render(request, 'dojo/payment_success.html', {
                    'transaction': transaction_obj,
                    'subscription': subscription
                })
            else:
                transaction_obj.status = 'failed'
                transaction_obj.save()
                return render(request, 'dojo/payment_failed.html', {'reference': reference})
        else:
            return err("Verification failed", 500)
            
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return err("Verification failed", 500)


def payment_modal_view(request):
    if not request.user.is_authenticated:
        return redirect('dojo:login')
    
    subscription = UserSubscription.objects.filter(user=request.user).first()
    
    trial_days_left = 0
    try:
        trial = UserTrial.objects.get(user=request.user, trial_type='curriculum')
        if trial.is_valid():
            trial_days_left = trial.days_remaining()
    except UserTrial.DoesNotExist:
        pass
    
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    return render(request, 'dojo/payment_modal.html', {
        'subscription': subscription,
        'trial_days_left': trial_days_left,
        'plans': [
            {'id': plan.id, 'name': plan.get_name_display(), 'price': int(plan.price_kes), 'duration_days': plan.duration_days}
            for plan in plans
        ]
    })


def payment_verify_view(request):
    return render(request, 'dojo/payment_verify.html', {'reference': request.GET.get('reference')})


# ─────────────────────────────────────────────────────────────────────────────
# TUTOR INTEREST API
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_tutor_interest(request):
    data = json_body(request)
    email = data.get("email", "").strip().lower()
    
    if not email:
        return err("Email required")
    
    if '@' not in email or '.' not in email:
        return err("Valid email required")
    
    if TutorInterest.objects.filter(email=email).exists():
        return ok(message="Already subscribed", exists=True)
    
    interest = TutorInterest.objects.create(email=email)
    logger.info(f"New tutor interest: {email}")
    
    return ok(message="Interest recorded", id=interest.id)


@require_GET
@admin_only
def api_admin_tutor_interests(request):
    interests = TutorInterest.objects.all().order_by('-created_at')
    data = [{"id": i.id, "email": i.email, "created_at": i.created_at.isoformat()} for i in interests]
    return ok(interests=data)


@csrf_exempt
@admin_only
def api_admin_tutor_interest_delete(request, interest_id):
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
    count = TutorInterest.objects.all().count()
    TutorInterest.objects.all().delete()
    logger.info(f"Admin cleared {count} tutor interest submissions")
    return ok(deleted_count=count)


# ─────────────────────────────────────────────────────────────────────────────
# PARENT/STUDENT LINKING API
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("parent")
def api_parent_children(request):
    parent = request.user
    links = ParentStudentLink.objects.filter(parent=parent).select_related('student')
    
    children_data = []
    for link in links:
        student = link.student
        belt_progress = BeltProgress.objects.filter(user=student, passed=True).count()
        total_belts = BeltProgress.objects.filter(user=student).count()
        last_activity = StudentActivityLog.objects.filter(student=student).order_by('-activity_date').first()
        
        children_data.append({
            'id': student.id,
            'name': student.get_full_name() or student.username,
            'email': student.email,
            'belt_progress': belt_progress,
            'total_belts': total_belts,
            'relationship': link.relationship,
            'can_pay': link.can_pay,
            'can_view': link.can_view,
            'last_active': last_activity.activity_date.isoformat() if last_activity else None,
            'avatar': student.first_name[0].upper() if student.first_name else 'S'
        })
    
    return ok(children=children_data)


@csrf_exempt
@require_POST
@require_role("parent")
def api_parent_link_student(request):
    data = json_body(request)
    student_email = data.get('student_email', '').strip().lower()
    relationship = data.get('relationship', 'guardian')
    
    if not student_email:
        return err("Student email is required")
    
    try:
        student = User.objects.get(email=student_email, role='student', is_active=True)
    except User.DoesNotExist:
        return err("No student account found with this email")
    
    if ParentStudentLink.objects.filter(parent=request.user, student=student).exists():
        return err("This student is already linked to your account")
    
    ParentStudentLink.objects.create(
        parent=request.user,
        student=student,
        relationship=relationship
    )
    
    return ok(
        message=f"Successfully linked to {student.get_full_name()}",
        student={
            'id': student.id,
            'name': student.get_full_name(),
            'email': student.email
        }
    )


@csrf_exempt
@require_POST
@require_role("parent")
def api_parent_create_student(request):
    data = json_body(request)
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    relationship = data.get('relationship', 'guardian')
    
    if not first_name or not email or not password:
        return err("First name, email, and password are required")
    
    if len(password) < 6:
        return err("Password must be at least 6 characters")
    
    if User.objects.filter(email=email).exists():
        return err("Email already registered")
    
    try:
        with transaction.atomic():
            student = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role='student'
            )
            
            for i, belt_id in enumerate(BELT_ORDER):
                status = "active" if i == 0 else "locked"
                BeltProgress.objects.get_or_create(
                    user=student,
                    belt_id=belt_id,
                    defaults={
                        "status": status,
                        "passed": False,
                        "attempts": 0,
                        "best_acc": 0,
                        "levels_done": []
                    }
                )
            
            Streak.objects.get_or_create(user=student, defaults={"count": 0, "last_date": None})
            
            UserSubscription.objects.get_or_create(
                user=student,
                defaults={'status': 'inactive'}
            )
            
            # Create 7-day trials
            UserTrial.objects.get_or_create(
                user=student,
                trial_type='multiplication',
                defaults={'end_date': timezone.now() + timedelta(days=7), 'used': False}
            )
            
            UserTrial.objects.get_or_create(
                user=student,
                trial_type='curriculum',
                defaults={'end_date': timezone.now() + timedelta(days=7), 'used': False}
            )
            
            ParentStudentLink.objects.create(
                parent=request.user,
                student=student,
                relationship=relationship,
                can_pay=True,
                can_view=True
            )
            
            return ok(
                message=f"Student account created for {first_name} {last_name}",
                student={
                    'id': student.id,
                    'name': student.get_full_name(),
                    'email': student.email,
                    'password': password
                }
            )
            
    except Exception as e:
        logger.error(f"Error creating student from parent: {e}")
        return err(f"Failed to create student: {str(e)}", 500)


@require_GET
@require_role("parent")
def api_parent_student_progress(request, student_id):
    parent = request.user
    try:
        link = ParentStudentLink.objects.get(parent=parent, student_id=student_id, can_view=True)
        student = link.student
    except ParentStudentLink.DoesNotExist:
        return err("You don't have access to this student", 403)
    
    belt_progress = []
    for belt in BELTS_LIST:
        bp = BeltProgress.objects.filter(user=student, belt_id=belt['id']).first()
        progress_percentage = 0
        if bp and bp.levels_done:
            total_tables = len(belt['tables'])
            done_tables = len(bp.levels_done)
            progress_percentage = (done_tables / total_tables * 100) if total_tables > 0 else 0
        
        belt_progress.append({
            'belt_id': belt['id'],
            'name': belt['name'],
            'color': belt['color'],
            'emoji': belt['emoji'],
            'passed': bp.passed if bp else False,
            'progress': progress_percentage
        })
    
    fact_memory = FactMemory.objects.filter(user=student, seen__gt=3)
    weak_points = []
    for fm in fact_memory:
        accuracy = (fm.correct / fm.seen * 100) if fm.seen > 0 else 100
        if accuracy < 70:
            weak_points.append({
                'fact': f"{fm.a} × {fm.b}",
                'accuracy': round(accuracy, 1),
                'message': f"Only {round(accuracy,1)}% correct. Practice this fact!",
                'type': 'fact'
            })
    
    for bp in belt_progress:
        if not bp['passed'] and bp['progress'] < 50 and bp['belt_id'] not in ['white', 'yellow']:
            weak_points.append({
                'belt': bp['name'],
                'accuracy': round(bp['progress'], 1),
                'message': f"{bp['name']} needs attention. Only {round(bp['progress'],1)}% completed.",
                'type': 'belt'
            })
    
    recent_sessions_check = TrainingSession.objects.filter(user=student, accuracy__lt=0.6).count()
    if recent_sessions_check > 3:
        weak_points.append({
            'fact': 'Recent Performance',
            'accuracy': 60,
            'message': f"Multiple low-scoring sessions recently. Review weak areas.",
            'type': 'warning'
        })
    
    weak_points = weak_points[:8]
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    activity_logs = StudentActivityLog.objects.filter(
        student=student,
        activity_date__gte=start_date,
        activity_date__lte=end_date
    ).order_by('activity_date')
    
    calendar_data = {}
    total_minutes = 0
    for log in activity_logs:
        mins = log.session_duration // 60
        total_minutes += mins
        calendar_data[log.activity_date.isoformat()] = {
            'duration': log.session_duration,
            'duration_minutes': mins,
            'questions': log.questions_answered,
            'sessions': log.sessions_completed,
            'belts': log.belts_earned,
            'login_time': log.login_time.isoformat() if log.login_time else None,
            'logout_time': log.logout_time.isoformat() if log.logout_time else None
        }
    
    stats = student.training_sessions.aggregate(
        total_sessions=Count('id'),
        total_correct=Sum('correct'),
        total_questions=Sum('total_q'),
        avg_accuracy=Avg('accuracy')
    )
    
    recent_sessions = TrainingSession.objects.filter(user=student).order_by('-created_at')[:15]
    sessions_data = []
    for s in recent_sessions:
        sessions_data.append({
            'date': s.created_at.strftime('%Y-%m-%d'),
            'time': s.created_at.strftime('%H:%M'),
            'belt': s.belt_id,
            'belt_name': dict(BELT_CHOICES).get(s.belt_id, s.belt_id),
            'accuracy': round(s.accuracy * 100, 1),
            'time_used': s.time_used,
            'time_display': f"{s.time_used // 60}:{str(s.time_used % 60).zfill(2)}",
            'passed': s.passed,
            'correct': s.correct,
            'total_q': s.total_q
        })
    
    return ok(
        student={
            'id': student.id,
            'name': student.get_full_name(),
            'email': student.email,
            'joined': student.date_joined.isoformat()
        },
        belt_progress=belt_progress,
        calendar=calendar_data,
        weak_points=weak_points,
        stats={
            'total_sessions': stats['total_sessions'] or 0,
            'total_correct': stats['total_correct'] or 0,
            'total_questions': stats['total_questions'] or 0,
            'avg_accuracy': round((stats['avg_accuracy'] or 0) * 100, 1)
        },
        recent_sessions=sessions_data,
        total_minutes=total_minutes
    )


@require_GET
@require_role("parent")
def api_parent_student_activity_calendar(request, student_id, year, month):
    parent = request.user
    try:
        link = ParentStudentLink.objects.get(parent=parent, student_id=student_id, can_view=True)
        student = link.student
    except ParentStudentLink.DoesNotExist:
        return err("You don't have access to this student", 403)
    
    num_days = monthrange(year, month)[1]
    start_date = datetime(year, month, 1).date()
    end_date = datetime(year, month, num_days).date()
    
    activity_logs = StudentActivityLog.objects.filter(
        student=student,
        activity_date__gte=start_date,
        activity_date__lte=end_date
    ).order_by('activity_date')
    
    training_sessions = TrainingSession.objects.filter(
        user=student,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).order_by('created_at')
    
    sessions_by_date = {}
    for ts in training_sessions:
        date_key = ts.created_at.date().isoformat()
        if date_key not in sessions_by_date:
            sessions_by_date[date_key] = []
        sessions_by_date[date_key].append({
            'belt': ts.belt_id,
            'accuracy': round(ts.accuracy * 100, 1),
            'passed': ts.passed,
            'time': ts.created_at.strftime('%H:%M')
        })
    
    calendar_data = []
    for day in range(1, num_days + 1):
        current_date = datetime(year, month, day).date()
        log = next((l for l in activity_logs if l.activity_date == current_date), None)
        day_sessions = sessions_by_date.get(current_date.isoformat(), [])
        
        if log:
            calendar_data.append({
                'date': current_date.isoformat(),
                'day': day,
                'has_activity': True,
                'duration': log.session_duration,
                'duration_minutes': round(log.session_duration / 60),
                'questions': log.questions_answered,
                'sessions': log.sessions_completed,
                'belts': log.belts_earned,
                'login_time': log.login_time.strftime('%I:%M %p') if log.login_time else None,
                'logout_time': log.logout_time.strftime('%I:%M %p') if log.logout_time else None,
                'session_details': day_sessions
            })
        else:
            calendar_data.append({
                'date': current_date.isoformat(),
                'day': day,
                'has_activity': False,
                'duration': 0,
                'duration_minutes': 0,
                'questions': 0,
                'sessions': 0,
                'belts': 0,
                'login_time': None,
                'logout_time': None,
                'session_details': []
            })
    
    streak = 0
    current_streak = 0
    for day_data in calendar_data:
        if day_data['has_activity']:
            current_streak += 1
            streak = max(streak, current_streak)
        else:
            current_streak = 0
    
    return ok(
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        days=calendar_data,
        total_duration=sum(d['duration'] for d in calendar_data),
        total_minutes=sum(d['duration_minutes'] for d in calendar_data),
        total_questions=sum(d['questions'] for d in calendar_data),
        active_days=sum(1 for d in calendar_data if d['has_activity']),
        streak=streak,
        total_sessions=sum(d['sessions'] for d in calendar_data)
    )


@require_GET
@require_role("parent")
def api_parent_student_billing(request, student_id):
    parent = request.user
    try:
        link = ParentStudentLink.objects.get(parent=parent, student_id=student_id, can_pay=True)
        student = link.student
    except ParentStudentLink.DoesNotExist:
        return err("You don't have payment access for this student", 403)
    
    subscription = UserSubscription.objects.filter(user=student).first()
    transactions = PaymentTransaction.objects.filter(user=student, status='success').order_by('-created_at')[:20]
    
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    return ok(
        student={
            'id': student.id,
            'name': student.get_full_name()
        },
        subscription={
            'has_active': subscription and subscription.is_active() if subscription else False,
            'plan': subscription.plan.get_name_display() if subscription and subscription.plan else None,
            'status': subscription.status if subscription else 'inactive',
            'start_date': subscription.start_date.isoformat() if subscription and subscription.start_date else None,
            'end_date': subscription.end_date.isoformat() if subscription and subscription.end_date else None,
            'days_remaining': subscription.days_remaining() if subscription and subscription.is_active() else 0
        } if subscription else None,
        transactions=[{
            'reference': t.reference,
            'amount': float(t.amount_kes),
            'plan': t.plan.get_name_display() if t.plan else 'N/A',
            'status': t.status,
            'date': t.created_at.isoformat()
        } for t in transactions],
        plans=[{'id': p.id, 'name': p.get_name_display(), 'price': int(p.price_kes), 'duration': p.duration_days} for p in plans]
    )


@csrf_exempt
@require_POST
@require_role("parent")
def api_parent_pay_for_student(request, student_id):
    parent = request.user
    data = json_body(request)
    plan_id = data.get('plan_id')
    
    try:
        link = ParentStudentLink.objects.get(parent=parent, student_id=student_id, can_pay=True)
        student = link.student
    except ParentStudentLink.DoesNotExist:
        return err("You don't have payment access for this student", 403)
    
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return err("Invalid plan selected", 400)
    
    amount_kes = plan.price_kes
    amount_in_smallest_unit = int(amount_kes * 100)
    
    reference = f"PARENT-{parent.id}-{student.id}-{uuid.uuid4().hex[:12].upper()}"
    
    payload = {
        'email': parent.email,
        'amount': amount_in_smallest_unit,
        'currency': 'KES',
        'reference': reference,
        'metadata': {
            'parent_id': parent.id,
            'student_id': student.id,
            'plan_id': plan.id,
            'plan_name': plan.get_name_display(),
            'payment_for': 'student',
            'student_email': student.email,
            'custom_fields': [
                {'display_name': 'Parent', 'variable_name': 'parent', 'value': parent.email},
                {'display_name': 'Student', 'variable_name': 'student', 'value': student.email},
                {'display_name': 'Plan', 'variable_name': 'plan', 'value': plan.get_name_display()},
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
                PaymentTransaction.objects.create(
                    user=student,
                    reference=reference,
                    access_code=resp_data['data']['access_code'],
                    amount_usd=plan.price_usd,
                    amount_kes=plan.price_kes,
                    plan=plan,
                    duration_days=plan.duration_days,
                    status='pending',
                    paystack_response=resp_data
                )
                
                return ok(
                    authorization_url=resp_data['data']['authorization_url'],
                    reference=reference
                )
        return err("Payment initialization failed", 500)
        
    except Exception as e:
        logger.error(f"Parent payment error: {e}")
        return err("Payment service unavailable", 500)


@require_GET
@require_role("parent")
def api_parent_notifications(request):
    parent = request.user
    notifications = ParentNotification.objects.filter(parent=parent, is_read=False).order_by('-created_at')[:50]
    
    return ok(notifications=[{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'student_name': n.student.get_full_name() if n.student else None,
        'type': n.notification_type,
        'created_at': n.created_at.isoformat()
    } for n in notifications])


@csrf_exempt
@require_POST
@require_role("parent")
def api_parent_mark_notification_read(request, notification_id):
    try:
        notification = ParentNotification.objects.get(id=notification_id, parent=request.user)
        notification.is_read = True
        notification.save()
        return ok()
    except ParentNotification.DoesNotExist:
        return err("Notification not found", 404)


@csrf_exempt
@require_POST
def api_track_student_activity(request):
    if not request.user.is_authenticated or request.user.role != 'student':
        return err("Unauthorized", 401)
    
    data = json_body(request)
    action = data.get('action', 'login')
    
    if action == 'login':
        StudentActivityLog.objects.create(
            student=request.user,
            login_time=timezone.now(),
            activity_date=timezone.now().date()
        )
    elif action == 'logout':
        latest_log = StudentActivityLog.objects.filter(
            student=request.user,
            logout_time__isnull=True
        ).order_by('-login_time').first()
        
        if latest_log:
            latest_log.logout_time = timezone.now()
            latest_log.session_duration = int((latest_log.logout_time - latest_log.login_time).total_seconds())
            latest_log.save()
    
    return ok()


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN SUBMISSION & ATTACHMENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@admin_only
def api_admin_submissions(request):
    submissions = []
    attempts = StudentQuizAttempt.objects.filter(completed=True).select_related('user', 'content_item').order_by('-completed_at')
    
    for attempt in attempts:
        file_count = StudentAnswerAttachment.objects.filter(answer_detail__attempt=attempt).count()
        submissions.append({
            'attempt_id': attempt.id,
            'student_id': attempt.user.id,
            'student_name': attempt.user.get_full_name() or attempt.user.email,
            'student_email': attempt.user.email,
            'content_id': attempt.content_item.id,
            'content_title': attempt.content_item.title,
            'score': attempt.score,
            'max_score': attempt.max_score,
            'percentage': attempt.percentage,
            'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
            'files_count': file_count,
        })
    
    return JsonResponse({'submissions': submissions})


@require_GET
@admin_only
def api_admin_submission_detail(request, attempt_id):
    attempt = get_object_or_404(StudentQuizAttempt, id=attempt_id, completed=True)
    
    answers = []
    for detail in attempt.answer_details.select_related('question').all():
        attachments = []
        for att in detail.attachments.all():
            attachments.append({
                'id': att.id,
                'filename': att.original_filename,
                'size': att.file_size,
                'type': att.file_type,
                'url': att.file.url if att.file else None,
                'is_image': att.file_type and att.file_type.startswith('image/'),
                'is_pdf': att.file_type == 'application/pdf',
            })
        
        answers.append({
            'question_text': detail.question.question_text,
            'user_answer': detail.user_answer,
            'is_correct': detail.is_correct,
            'score_earned': detail.score_earned,
            'attachments': attachments,
        })
    
    return JsonResponse({
        'submission': {
            'id': attempt.id,
            'student_name': attempt.user.get_full_name() or attempt.user.email,
            'student_email': attempt.user.email,
            'content_title': attempt.content_item.title,
            'score': attempt.score,
            'max_score': attempt.max_score,
            'percentage': attempt.percentage,
            'completed_at': attempt.completed_at.isoformat(),
            'answers': answers,
        }
    })


@require_GET
@admin_only
def api_admin_content_submissions(request, content_id):
    content = get_object_or_404(ContentItem, id=content_id)
    
    attempts = StudentQuizAttempt.objects.filter(
        content_item=content,
        completed=True
    ).select_related('user').order_by('-completed_at')
    
    submissions = []
    for attempt in attempts:
        file_count = StudentAnswerAttachment.objects.filter(answer_detail__attempt=attempt).count()
        submissions.append({
            'id': attempt.id,
            'student_id': attempt.user.id,
            'student_name': attempt.user.get_full_name() or attempt.user.email,
            'score': attempt.score,
            'max_score': attempt.max_score,
            'percentage': attempt.percentage,
            'completed_at': attempt.completed_at.isoformat(),
            'files_count': file_count,
        })
    
    return JsonResponse({'submissions': submissions, 'content_title': content.title})


@require_GET
def api_serve_attachment(request, attachment_id):
    try:
        attachment = StudentAnswerAttachment.objects.select_related('answer_detail__attempt').get(id=attachment_id)
        
        if request.user.is_authenticated:
            is_admin = request.user.role == 'admin'
            is_owner = attachment.answer_detail.attempt.user == request.user
            if not (is_admin or is_owner):
                return err("Access denied", 403)
        else:
            return err("Authentication required", 401)
        
        file_path = attachment.file.name if attachment.file else None
        if not file_path or not default_storage.exists(file_path):
            return err("File not found", 404)
        
        file_handle = default_storage.open(file_path, 'rb')
        content_type = attachment.file_type or mimetypes.guess_type(attachment.original_filename)[0] or 'application/octet-stream'
        
        response = FileResponse(file_handle, content_type=content_type)
        
        if content_type == 'application/pdf' or (content_type and content_type.startswith('image/')):
            response['Content-Disposition'] = f'inline; filename="{attachment.original_filename}"'
        else:
            response['Content-Disposition'] = f'attachment; filename="{attachment.original_filename}"'
        
        return response
        
    except StudentAnswerAttachment.DoesNotExist:
        return err("Attachment not found", 404)
    except Exception as e:
        logger.error(f"Error serving attachment: {e}")
        return err(f"Error serving file: {str(e)}", 500)


@require_GET
def api_download_submission_file(request, attempt_id, question_index):
    try:
        attempt = StudentQuizAttempt.objects.get(id=attempt_id)
        
        if request.user.is_authenticated:
            is_admin = request.user.role == 'admin'
            is_owner = attempt.user == request.user
            if not (is_admin or is_owner):
                return err("Access denied", 403)
        else:
            return err("Authentication required", 401)
        
        answer_details = list(attempt.answer_details.select_related('question').all())
        
        if question_index >= len(answer_details):
            return err("Question not found", 404)
        
        answer_detail = answer_details[question_index]
        attachment = answer_detail.attachments.first()
        
        if not attachment:
            return err("No attachment for this question", 404)
        
        file_path = attachment.file.name if attachment.file else None
        if not file_path or not default_storage.exists(file_path):
            return err("File not found", 404)
        
        file_handle = default_storage.open(file_path, 'rb')
        content_type = attachment.file_type or mimetypes.guess_type(attachment.original_filename)[0] or 'application/octet-stream'
        
        response = FileResponse(file_handle, content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{attachment.original_filename}"'
        
        return response
        
    except StudentQuizAttempt.DoesNotExist:
        return err("Submission not found", 404)
    except Exception as e:
        logger.error(f"Error: {e}")
        return err(str(e), 500)


@require_GET
def api_admin_list_attachments(request, content_id=None):
    if not request.user.is_authenticated or request.user.role != 'admin':
        return err("Unauthorized", 401)
    
    attachments = StudentAnswerAttachment.objects.select_related(
        'answer_detail__attempt__user',
        'answer_detail__question'
    ).all()
    
    if content_id:
        attachments = attachments.filter(answer_detail__attempt__content_item_id=content_id)
    
    data = []
    for att in attachments[:200]:
        data.append({
            'id': att.id,
            'filename': att.original_filename,
            'file_size': att.file_size,
            'file_type': att.file_type,
            'student': att.answer_detail.attempt.user.email,
            'student_name': att.answer_detail.attempt.user.get_full_name(),
            'quiz_title': att.answer_detail.attempt.content_item.title,
            'question_text': att.answer_detail.question.question_text[:100],
            'url': f'/api/admin/attachment/{att.id}/serve/',
            'download_url': f'/api/admin/attachment/{att.id}/download/',
        })
    
    return JsonResponse({'attachments': data, 'count': len(data)})


@require_GET
def api_admin_serve_attachment_direct(request, attachment_id):
    try:
        if not request.user.is_authenticated or request.user.role != 'admin':
            return err("Admin access required", 403)
        
        attachment = StudentAnswerAttachment.objects.get(id=attachment_id)
        file_path = attachment.file.name if attachment.file else None
        
        if not file_path or not default_storage.exists(file_path):
            possible_paths = [
                file_path,
                f'quiz_attachments/{os.path.basename(file_path)}' if file_path else None,
                attachment.file.name if attachment.file else None,
            ]
            
            found = False
            for path in possible_paths:
                if path and default_storage.exists(path):
                    file_path = path
                    found = True
                    break
            
            if not found:
                return JsonResponse({
                    'error': 'File not found on server',
                    'stored_path': attachment.file.name,
                    'id': attachment.id,
                    'filename': attachment.original_filename
                }, status=404)
        
        file_handle = default_storage.open(file_path, 'rb')
        content_type = attachment.file_type or mimetypes.guess_type(attachment.original_filename)[0] or 'application/octet-stream'
        
        response = FileResponse(file_handle, content_type=content_type)
        
        if content_type == 'application/pdf' or (content_type and content_type.startswith('image/')):
            response['Content-Disposition'] = f'inline; filename="{attachment.original_filename}"'
        else:
            response['Content-Disposition'] = f'attachment; filename="{attachment.original_filename}"'
        
        return response
        
    except StudentAnswerAttachment.DoesNotExist:
        return err("Attachment not found", 404)
    except Exception as e:
        logger.error(f"Error: {e}")
        return err(str(e), 500)


def payment_modal_view(request):
    if not request.user.is_authenticated:
        return redirect('dojo:login')
    
    subscription = UserSubscription.objects.filter(user=request.user).first()
    
    trial_days_left = 0
    try:
        trial = UserTrial.objects.get(user=request.user, trial_type='curriculum')
        if trial.is_valid():
            trial_days_left = trial.days_remaining()
    except UserTrial.DoesNotExist:
        pass
    
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    return render(request, 'dojo/payment_modal.html', {
        'subscription': subscription,
        'trial_days_left': trial_days_left,
        'plans': [
            {'id': plan.id, 'name': plan.get_name_display(), 'price': int(plan.price_kes), 'duration_days': plan.duration_days}
            for plan in plans
        ]
    })


def payment_verify_view(request):
    return render(request, 'dojo/payment_verify.html', {'reference': request.GET.get('reference')})



# ─────────────────────────────────────────────────────────────────────────────
# SUBSCRIPTION & PAYMENT API (ADD THESE FUNCTIONS)
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@require_role("student")
def api_subscription_status(request):
    """Get current subscription status for the user"""
    user = request.user
    
    # Get or create subscription
    subscription, created = UserSubscription.objects.get_or_create(
        user=user,
        defaults={'status': 'inactive'}
    )
    
    # Check and auto-expire if needed
    if subscription.status == 'active' and subscription.end_date:
        if timezone.now() >= subscription.end_date:
            subscription.status = 'expired'
            subscription.save()
            user.is_paid = False
            user.save(update_fields=['is_paid'])
    
    # Get all available plans
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    # Check trial status for curriculum content
    curriculum_trial = None
    try:
        trial = UserTrial.objects.get(user=user, trial_type='curriculum')
        if trial.is_valid():
            curriculum_trial = {
                'days_remaining': trial.days_remaining(),
                'end_date': trial.end_date.isoformat(),
                'is_active': True
            }
    except UserTrial.DoesNotExist:
        pass
    
    # Check multiplication trial
    multiplication_trial = None
    try:
        trial = UserTrial.objects.get(user=user, trial_type='multiplication')
        if trial.is_valid():
            multiplication_trial = {
                'days_remaining': trial.days_remaining(),
                'end_date': trial.end_date.isoformat(),
                'is_active': True
            }
    except UserTrial.DoesNotExist:
        pass
    
    cache_key = f'subscription_status_{user.id}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return JsonResponse(cached_data)
    
    response_data = {
        'has_active_subscription': subscription.is_active() if hasattr(subscription, 'is_active') else False,
        'status': subscription.status,
        'plan': {
            'id': subscription.plan.id if subscription.plan else None,
            'name': subscription.plan.get_name_display() if subscription.plan else None,
            'price_usd': float(subscription.plan.price_usd) if subscription.plan else None,
            'price_kes': float(subscription.plan.price_kes) if subscription.plan else None,
        } if subscription.plan else None,
        'start_date': subscription.start_date.isoformat() if subscription.start_date else None,
        'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
        'days_remaining': subscription.days_remaining() if hasattr(subscription, 'days_remaining') else 0,
        'status_text': subscription.get_status_display_text() if hasattr(subscription, 'get_status_display_text') else 'No active subscription',
        'auto_renew': getattr(subscription, 'auto_renew', False),
        'cancel_at_period_end': getattr(subscription, 'cancel_at_period_end', False),
        'curriculum_trial': curriculum_trial,
        'multiplication_trial': multiplication_trial,
        'available_plans': [
            {
                'id': plan.id,
                'name': plan.get_name_display(),
                'price_usd': float(plan.price_usd),
                'price_kes': float(plan.price_kes),
                'duration_days': plan.duration_days,
                'savings_usd': float(plan.savings_usd),
                'savings_kes': float(plan.savings_kes),
            }
            for plan in plans
        ]
    }
    
    cache.set(cache_key, response_data, 300)
    return JsonResponse(response_data)


@csrf_exempt
@require_POST
@require_role("student")
def api_initiate_subscription(request):
    """Initialize a new subscription payment"""
    data = json_body(request)
    plan_id = data.get('plan_id')
    
    if not plan_id:
        return err("Plan ID required", 400)
    
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return err("Invalid plan selected", 400)
    
    user = request.user
    
    # Get or create subscription
    subscription, _ = UserSubscription.objects.get_or_create(
        user=user,
        defaults={'status': 'inactive'}
    )
    
    # Generate unique reference
    reference = f"SUB-{user.id}-{uuid.uuid4().hex[:12].upper()}"
    amount_kes = plan.price_kes
    amount_in_smallest_unit = int(amount_kes * 100)
    
    # Determine transaction type
    transaction_type = 'initial'
    if subscription.status == 'active' and subscription.end_date and subscription.end_date > timezone.now():
        transaction_type = 'renewal'
    
    callback_url = request.build_absolute_uri('/payment/subscription/verify/')
    
    payload = {
        'email': user.email,
        'amount': amount_in_smallest_unit,
        'currency': 'KES',
        'reference': reference,
        'callback_url': callback_url,
        'metadata': {
            'user_id': user.id,
            'subscription_id': subscription.id,
            'plan_id': plan.id,
            'plan_name': plan.get_name_display(),
            'duration_days': plan.duration_days,
            'transaction_type': transaction_type,
            'custom_fields': [
                {'display_name': 'Plan', 'variable_name': 'plan', 'value': plan.get_name_display()},
                {'display_name': 'User', 'variable_name': 'user', 'value': user.email},
                {'display_name': 'Duration', 'variable_name': 'duration', 'value': f'{plan.duration_days} days'},
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
                PaymentTransaction.objects.create(
                    user=user,
                    subscription=subscription,
                    transaction_type=transaction_type,
                    reference=reference,
                    access_code=resp_data['data']['access_code'],
                    amount_usd=plan.price_usd,
                    amount_kes=plan.price_kes,
                    plan=plan,
                    duration_days=plan.duration_days,
                    status='pending',
                    paystack_response=resp_data
                )
                
                return JsonResponse({
                    'authorization_url': resp_data['data']['authorization_url'],
                    'reference': reference,
                    'access_code': resp_data['data']['access_code']
                })
        
        return err("Payment initialization failed", 500)
        
    except Exception as e:
        logger.error(f"Subscription payment error: {e}")
        return err("Payment service unavailable", 500)


@csrf_exempt
@require_POST
@require_role("student")
def api_cancel_subscription(request):
    """Cancel auto-renewal of subscription"""
    try:
        subscription = UserSubscription.objects.get(user=request.user, status='active')
        subscription.auto_renew = False
        subscription.cancel_at_period_end = True
        subscription.save()
        
        cache.delete(f'subscription_status_{request.user.id}')
        
        end_date_str = subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'expiry date'
        
        return JsonResponse({
            'success': True,
            'message': f'Auto-renewal cancelled. Your subscription will expire on {end_date_str}'
        })
    except UserSubscription.DoesNotExist:
        return err("No active subscription found", 404)


@require_GET
@require_role("student")
def api_payment_history(request):
    """Get user's payment history with receipts"""
    user = request.user
    
    transactions = PaymentTransaction.objects.filter(
        user=user,
        status='success'
    ).select_related('plan').order_by('-created_at')
    
    data = []
    for t in transactions:
        data.append({
            'id': t.id,
            'reference': t.reference,
            'amount_usd': float(t.amount_usd),
            'amount_kes': float(t.amount_kes),
            'plan_name': t.plan.get_name_display() if t.plan else 'N/A',
            'duration_days': t.duration_days,
            'transaction_type': t.get_transaction_type_display(),
            'status': t.status,
            'date': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_at': t.completed_at.strftime('%Y-%m-%d %H:%M:%S') if t.completed_at else None,
        })
    
    return JsonResponse({'transactions': data})


@csrf_exempt
def api_subscription_webhook(request):
    """Handle Paystack webhooks for auto-renewal"""
    paystack_signature = request.headers.get('x-paystack-signature')
    
    if not paystack_signature:
        return JsonResponse({'error': 'No signature'}, status=400)
    
    hash_object = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        request.body,
        hashlib.sha512
    )
    expected_signature = hash_object.hexdigest()
    
    if not hmac.compare_digest(paystack_signature, expected_signature):
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    
    event = data.get('event')
    logger.info(f"Webhook received event: {event}")
    
    if event == 'charge.success':
        reference = data['data']['reference']
        
        try:
            transaction = PaymentTransaction.objects.get(reference=reference)
            
            if transaction.status != 'success':
                transaction.status = 'success'
                transaction.completed_at = timezone.now()
                transaction.save()
                
                subscription = transaction.subscription
                plan = transaction.plan
                
                if subscription:
                    if subscription.end_date and subscription.end_date > timezone.now():
                        subscription.end_date = subscription.end_date + timedelta(days=plan.duration_days)
                    else:
                        subscription.end_date = timezone.now() + timedelta(days=plan.duration_days)
                    
                    subscription.status = 'active'
                    subscription.plan = plan
                    subscription.last_payment_date = timezone.now()
                    subscription.next_payment_date = subscription.end_date
                    subscription.cancel_at_period_end = False
                    subscription.save()
                    
                    transaction.user.is_paid = True
                    transaction.user.save(update_fields=['is_paid'])
                    
                    cache.delete(f'subscription_status_{transaction.user.id}')
                    logger.info(f"Webhook: Successfully renewed subscription for {transaction.user.email}")
                    
        except PaymentTransaction.DoesNotExist:
            logger.warning(f"Webhook: Transaction not found for reference {reference}")
    
    elif event == 'subscription.disable':
        subscription_code = data['data']['subscription_code']
        try:
            subscription = UserSubscription.objects.get(paystack_subscription_code=subscription_code)
            subscription.auto_renew = False
            subscription.cancel_at_period_end = True
            subscription.save()
        except UserSubscription.DoesNotExist:
            pass
    
    return JsonResponse({'status': 'success'})


@require_GET
@require_role("student")
def api_check_curriculum_access(request):
    """Check if user has access to curriculum content (CBC/8-4-4/IGCSE)"""
    user = request.user
    
    has_access = False
    trial_info = None
    
    # Check subscription first
    try:
        subscription = UserSubscription.objects.get(user=user)
        if subscription.is_active() and subscription.status == 'active':
            has_access = True
    except UserSubscription.DoesNotExist:
        pass
    
    # Check trial period (7 days)
    if not has_access:
        try:
            trial = UserTrial.objects.get(user=user, trial_type='curriculum')
            if trial.is_valid():
                has_access = True
                trial_info = {
                    'days_remaining': trial.days_remaining(),
                    'end_date': trial.end_date.isoformat(),
                    'is_active': True
                }
        except UserTrial.DoesNotExist:
            pass
    
    return JsonResponse({
        'has_access': has_access,
        'trial': trial_info,
        'requires_subscription': not has_access
    })


@require_GET
@require_role("student")
def api_check_belt_access(request, belt_id):
    """Check if user has access to a specific belt"""
    user = request.user
    
    # White and Yellow belts are always free
    if belt_id in ['white', 'yellow']:
        return JsonResponse({'has_access': True, 'belt_id': belt_id})
    
    has_access = False
    trial_info = None
    
    # Check subscription
    try:
        subscription = UserSubscription.objects.get(user=user)
        if subscription.is_active() and subscription.status == 'active':
            has_access = True
    except UserSubscription.DoesNotExist:
        pass
    
    # Check trial period (7 days for multiplication)
    if not has_access:
        try:
            trial = UserTrial.objects.get(user=user, trial_type='multiplication')
            if trial.is_valid():
                has_access = True
                trial_info = {
                    'days_remaining': trial.days_remaining(),
                    'end_date': trial.end_date.isoformat(),
                    'is_active': True
                }
        except UserTrial.DoesNotExist:
            pass
    
    return JsonResponse({
        'has_access': has_access,
        'belt_id': belt_id,
        'requires_subscription': not has_access,
        'trial': trial_info,
        'status_text': 'Premium subscription required for this belt' if not has_access else None
    })


def api_verify_subscription(request):
    """Verify subscription payment and activate subscription"""
    reference = request.GET.get('reference')
    
    if not reference:
        return redirect('/payment/failed/?error=no_reference')
    
    try:
        transaction = PaymentTransaction.objects.get(reference=reference)
    except PaymentTransaction.DoesNotExist:
        return redirect('/payment/failed/?error=transaction_not_found')
    
    try:
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=get_paystack_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            
            if resp_data.get('status') and resp_data['data']['status'] == 'success':
                transaction.status = 'success'
                transaction.completed_at = timezone.now()
                transaction.save()
                
                subscription = transaction.subscription
                plan = transaction.plan
                
                if transaction.transaction_type == 'initial':
                    subscription.plan = plan
                    subscription.status = 'active'
                    subscription.start_date = timezone.now()
                    subscription.end_date = timezone.now() + timedelta(days=plan.duration_days)
                    subscription.last_payment_date = timezone.now()
                    subscription.next_payment_date = timezone.now() + timedelta(days=plan.duration_days)
                    
                    data = resp_data['data']
                    if 'authorization' in data and 'authorization_code' in data['authorization']:
                        subscription.paystack_authorization_code = data['authorization']['authorization_code']
                    if 'customer' in data and 'customer_code' in data['customer']:
                        subscription.paystack_customer_code = data['customer']['customer_code']
                else:
                    # Renewal - extend existing subscription
                    if subscription.end_date and subscription.end_date > timezone.now():
                        subscription.end_date = subscription.end_date + timedelta(days=plan.duration_days)
                    else:
                        subscription.end_date = timezone.now() + timedelta(days=plan.duration_days)
                    
                    subscription.status = 'active'
                    subscription.last_payment_date = timezone.now()
                    subscription.next_payment_date = subscription.end_date
                    subscription.cancel_at_period_end = False
                
                subscription.save()
                
                # Mark trials as used since user now has paid subscription
                UserTrial.objects.filter(user=transaction.user, used=False).update(used=True)
                
                transaction.user.is_paid = True
                transaction.user.save(update_fields=['is_paid'])
                
                cache.delete(f'subscription_status_{transaction.user.id}')
                
                return render(request, 'dojo/payment_success.html', {
                    'transaction': transaction,
                    'subscription': subscription,
                    'message': f'Successfully subscribed to {plan.get_name_display()} plan!'
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                return render(request, 'dojo/payment_failed.html', {
                    'reference': reference,
                    'error': resp_data.get('message', 'Payment verification failed')
                })
        
        return redirect(f'/payment/failed/?reference={reference}')
        
    except Exception as e:
        logger.error(f"Subscription verification error: {e}")
        return redirect(f'/payment/failed/?reference={reference}&error=verification_error')


def api_get_plans(request):
    """Get available subscription plans"""
    plans = SubscriptionPlan.objects.filter(is_active=True)
    return JsonResponse({'plans': [
        {
            'id': plan.id,
            'name': plan.get_name_display(),
            'price_usd': float(plan.price_usd),
            'price_kes': int(plan.price_kes),
            'duration_days': plan.duration_days,
            'savings_usd': float(plan.savings_usd),
            'savings_kes': int(plan.savings_kes),
        }
        for plan in plans
    ]})    