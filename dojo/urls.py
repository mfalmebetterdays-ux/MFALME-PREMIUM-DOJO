from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "dojo"

urlpatterns = [
    # ── HTML PAGES ────────────────────────────────────────────────────────────
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("game/", views.StudentAppView.as_view(), name="game"),
    path("tutor/", views.TutorDashboardView.as_view(), name="tutor_dashboard"),
    
    # Redirect /admin (no trailing slash) to /admin/ (with trailing slash)
    path("admin", RedirectView.as_view(url="/admin/", permanent=False)),
    
    # Admin routes
    path("admin/login/", views.AdminLoginView.as_view(), name="admin_login"),
    path("admin/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin/", views.LegacyAdminAppView.as_view(), name="admin"),
    
    path("logout/", views.LogoutView.as_view(), name="logout"),

    # ── PUBLIC API ─────────────────────────────────────────────────────────
    path("api/public/stats/", views.api_public_stats, name="api-public-stats"),

    # ── AUTH API ──────────────────────────────────────────────────────────────
    path("api/register/", views.api_register, name="api-register"),
    path("api/login/", views.api_login, name="api-login"),
    path("api/logout/", views.api_logout, name="api-logout"),
    path("api/me/", views.api_me, name="api-me"),

    # ── STUDENT API ───────────────────────────────────────────────────────────
    path("api/student/profile/", views.api_student_profile, name="api-student-profile"),
    path("api/student/profile/update/", views.api_student_profile_update, name="api-student-profile-update"),
    path("api/student/password/change/", views.api_student_password_change, name="api-student-password-change"),
    
    # BELTS - ORDER MATTERS! Put specific paths BEFORE dynamic ones
    path("api/student/belts/update/", views.api_student_belt_update, name="api-student-belt-update"),
    path("api/student/belts/progress/", views.api_student_belt_progress, name="api-student-belt-progress"),
    path("api/student/belts/", views.api_student_belts, name="api-student-belts"),
    path("api/student/belts/<str:belt_id>/", views.api_student_belt_details, name="api-student-belt-details"),
    
    path("api/student/session/save/", views.api_session_save, name="api-session-save"),
    path("api/student/facts/", views.api_facts_get, name="api-facts-get"),
    path("api/student/facts/update/", views.api_facts_update, name="api-facts-update"),
    path("api/student/badges/", views.api_badges, name="api-badges"),
    path("api/student/streak/", views.api_streak, name="api-streak"),
    path("api/student/stats/", views.api_student_stats, name="api-student-stats"),
    path("api/student/sessions/recent/", views.api_student_recent_sessions, name="api-student-recent-sessions"),
    path("api/student/leaderboard/", views.api_leaderboard, name="api-leaderboard"),
    path("api/student/tutors/", views.api_tutors_search, name="api-tutors-search"),
    path("api/student/request-tutor/", views.api_request_tutor, name="api-request-tutor"),
    path("api/student/my-requests/", views.api_my_requests, name="api-my-requests"),
    
    # ── TUTOR API ─────────────────────────────────────────────────────────────
    path("api/tutor/profile/", views.api_tutor_profile, name="api-tutor-profile"),
    path("api/tutor/profile/update/", views.api_tutor_profile_update, name="api-tutor-profile-update"),
    path("api/tutor/password/change/", views.api_tutor_password_change, name="api-tutor-password-change"),
    path("api/tutor/requests/", views.api_tutor_requests, name="api-tutor-requests"),
    path("api/tutor/request/update/", views.api_tutor_request_update, name="api-tutor-request-update"),
    
    # ── ADMIN API ─────────────────────────────────────────────────────────────
    path("api/admin/login/", views.api_admin_login, name="api-admin-login"),
    path("api/admin/overview/", views.api_admin_overview, name="api-admin-overview"),
    path("api/admin/students/", views.api_admin_students, name="api-admin-students"),
    path("api/admin/tutors/", views.api_admin_tutors, name="api-admin-tutors"),
    path("api/admin/belts/", views.api_admin_belts, name="api-admin-belts"),
    path("api/admin/knowledge/", views.api_admin_knowledge, name="api-admin-knowledge"),
    path("api/admin/activity/", views.api_admin_activity, name="api-admin-activity"),
    path("api/admin/county/", views.api_admin_county, name="api-admin-county"),
    path("api/admin/leaderboard/", views.api_admin_leaderboard, name="api-admin-leaderboard"),
    path("api/admin/tutor-requests/", views.api_admin_tutor_requests, name="api-admin-tutor-requests"),
    path("api/admin/user/suspend/", views.api_admin_suspend, name="api-admin-suspend"),
    path("api/admin/user/upgrade/", views.api_admin_upgrade, name="api-admin-upgrade"),
    path("api/admin/tutor/approve/", views.api_admin_approve_tutor, name="api-admin-approve-tutor"),
    
    # ── ASSIGNMENT API ────────────────────────────────────────────────────────
    path("api/student/assignments/", views.api_student_assignments, name="api-student-assignments"),
    path("api/student/assignments/<int:assignment_id>/", views.api_student_assignment_detail, name="api-student-assignment-detail"),
    path("api/student/assignments/<int:assignment_id>/submit/", views.api_student_submit_assignment, name="api-student-submit-assignment"),
    
    path("api/tutor/assignments/", views.api_tutor_assignments, name="api-tutor-assignments"),
    path("api/tutor/assignments/create/", views.api_tutor_create_assignment, name="api-tutor-create-assignment"),
    path("api/tutor/assignments/<int:assignment_id>/submissions/", views.api_tutor_submissions, name="api-tutor-submissions"),
    path("api/tutor/submissions/<int:submission_id>/grade/", views.api_tutor_grade_submission, name="api-tutor-grade-submission"),
    
    # ── CHAT API ──────────────────────────────────────────────────────────────
    # Student chat endpoints (with attachments support)
    path("api/student/chat/<int:tutor_id>/", views.api_student_chat_with_attachments, name="api-student-chat"),
    path("api/student/chat/list/", views.api_student_chat_list, name="api-student-chat-list"),
    path("api/tutor/chat/<int:student_id>/", views.api_tutor_chat, name="api-tutor-chat"),
    path("api/tutor/chat/list/", views.api_tutor_chat_list, name="api-tutor-chat-list"),
    path("api/chat/send/", views.api_send_chat, name="api-send-chat"),
    
    # File upload endpoint
    path("api/chat/upload/", views.api_chat_upload_file, name="api-chat-upload"),
    
    # Video call endpoints (Google Meet)
    path("api/chat/start-call/", views.api_start_video_call, name="api-start-call"),
    path("api/chat/end-call/", views.api_end_video_call, name="api-end-call"),
    path("video-call/<str:room_name>/", views.video_call_view, name="video-call"),
    
    # ── NOTES API ─────────────────────────────────────────────────────────────
    path("api/student/notes/", views.api_student_notes, name="api-student-notes"),
    path("api/tutor/notes/", views.api_tutor_notes, name="api-tutor-notes"),
    path("api/tutor/notes/create/", views.api_tutor_create_note, name="api-tutor-create-note"),
    
    # ── PORTAL & NOTIFICATIONS ────────────────────────────────────────────────
    path("student-portal/", views.StudentPortalView.as_view(), name="student_portal"),
    path("api/student/notifications/unread-count/", views.api_unread_notifications_count, name="api-unread-notifications"),
    path("api/student/chat/tutors/", views.api_student_chat_tutors, name="api-student-chat-tutors"),

    # ── PAYMENT API ──────────────────────────────────────────────────────────
    path("api/payment/initialize/", views.api_initialize_payment, name="api-payment-initialize"),
    path("api/payment/verify/", views.api_verify_payment, name="api-payment-verify"),
    path("api/payment/check/", views.api_check_subscription, name="api-payment-check"),
    path("api/payment/plans/", views.api_get_plans, name="api-payment-plans"),
    path("api/payment/receipts/", views.api_payment_receipts, name="api-payment-receipts"),
    path("api/payment/webhook/", views.api_payment_webhook, name="api-payment-webhook"),
    
    # Payment pages
    path("payment/upgrade/", views.payment_modal_view, name="payment-upgrade"),
    path("payment/verify/", views.payment_verify_view, name="payment-verify"),
    path("payment/success/", views.payment_verify_view, name="payment-success"),
    
    # ── TUTOR INTEREST API ───────────────────────────────────────────────────
    path('api/tutor-interest/', views.api_tutor_interest, name='api_tutor_interest'),
    path('api/admin/tutor-interests/', views.api_admin_tutor_interests, name='api_admin_tutor_interests'),
    path('api/admin/tutor-interests/<int:interest_id>/delete/', views.api_admin_tutor_interest_delete, name='api_admin_tutor_interest_delete'),
    path('api/admin/tutor-interests/clear-all/', views.api_admin_tutor_interests_clear_all, name='api_admin_tutor_interests_clear_all'),
]