from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "dojo"

urlpatterns = [
    # ── HTML PAGES ────────────────────────────────────────────────────────────
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("parent-login/", views.ParentLoginView.as_view(), name="parent_login"),
    path("game/", views.StudentAppView.as_view(), name="game"),
    path("tutor/", views.TutorDashboardView.as_view(), name="tutor_dashboard"),
    
    # ── PASSWORD RESET PAGES ───────────────────────────────────────────────────
    path("password-reset/", views.password_reset_page, name="password_reset"),
    path("password-reset-confirm/", views.password_reset_confirm_page, name="password_reset_confirm"),
    path("password-reset-complete/", views.password_reset_complete_page, name="password_reset_complete"),
    
    # Redirect /admin (no trailing slash) to /admin/ (with trailing slash)
    path("admin", RedirectView.as_view(url="/admin/", permanent=False)),
    
    # Admin routes
    path("admin/login/", views.AdminLoginView.as_view(), name="admin_login"),
    path("admin/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin/", views.LegacyAdminAppView.as_view(), name="admin"),
    
    path("logout/", views.LogoutView.as_view(), name="logout"),
    
    # ── STUDENT DASHBOARDS ─────────────────────────────────────────────────────
    path("cbc-dashboard/", views.CBCStudentDashboardView.as_view(), name="cbc_dashboard"),
    path("setup-profile/", views.SetupProfileView.as_view(), name="setup_profile"),
    path('igcse-dashboard/', views.IGCSEDashboardView.as_view(), name='igcse_dashboard'),
    path('844-dashboard/', views.EightFourFourDashboardView.as_view(), name='844_dashboard'),
    
    # ── PARENT DASHBOARD ──────────────────────────────────────────────────────
    path("parent-dashboard/", views.ParentDashboardView.as_view(), name="parent_dashboard"),
    
    # ── PUBLIC API ─────────────────────────────────────────────────────────
    path("api/public/stats/", views.api_public_stats, name="api-public-stats"),
    
    # ── PASSWORD RESET API ───────────────────────────────────────────────────
    path("api/password-reset-request/", views.api_password_reset_request, name="api_password_reset_request"),
    path("api/password-reset-confirm/", views.api_password_reset_confirm, name="api_password_reset_confirm"),
    
    # ── AUTH API ──────────────────────────────────────────────────────────────
    path("api/register/", views.api_register, name="api-register"),
    path("api/login/", views.api_login, name="api-login"),
    path("api/logout/", views.api_logout, name="api-logout"),
    path("api/me/", views.api_me, name="api-me"),
    path("api/setup-profile/", views.api_setup_profile, name="api-setup-profile"),
    
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
    path("api/leaderboard/", views.api_leaderboard, name="api-leaderboard"),
    path("api/student/tutors/", views.api_tutors_search, name="api-tutors-search"),
    path("api/student/request-tutor/", views.api_request_tutor, name="api-request-tutor"),
    path("api/student/my-requests/", views.api_my_requests, name="api-my-requests"),
    
    # ── TUTOR API ─────────────────────────────────────────────────────────────
    path("api/tutor/profile/", views.api_tutor_profile, name="api-tutor-profile"),
    path("api/tutor/profile/update/", views.api_tutor_profile_update, name="api-tutor-profile-update"),
    path("api/tutor/password/change/", views.api_tutor_password_change, name="api-tutor-password-change"),
    path("api/tutor/requests/", views.api_tutor_requests, name="api-tutor-requests"),
    path("api/tutor/request/update/", views.api_tutor_request_update, name="api-tutor-request-update"),
    
    # ── SUBSCRIPTION & PAYMENT API (NEW - REPLACES OLD PAYMENT API) ─────────────
    # Subscription status and management
    path("api/subscription/status/", views.api_subscription_status, name="api-subscription-status"),
    path("api/subscription/initiate/", views.api_initiate_subscription, name="api-initiate-subscription"),
    path("api/subscription/cancel/", views.api_cancel_subscription, name="api-cancel-subscription"),
    path("api/payment/history/", views.api_payment_history, name="api-payment-history"),
    path("api/payment/webhook/", views.api_subscription_webhook, name="api-subscription-webhook"),
    
    # Access checks
    path("api/curriculum/access/", views.api_check_curriculum_access, name="api-curriculum-access"),
    path("api/subscription/check-belt/<str:belt_id>/", views.api_check_belt_access, name="api-check-belt-access"),
    
    # Payment verification
    path("api/payment/verify/", views.api_verify_payment, name="api-payment-verify"),
    path("payment/verify/", views.payment_verify_view, name="payment-verify"),
    path("payment/subscription/verify/", views.api_verify_subscription, name="payment-subscription-verify"),
    path("payment/upgrade/", views.payment_modal_view, name="payment-upgrade"),
    path("payment/success/", views.payment_verify_view, name="payment-success"),
    path("payment/failed/", views.payment_verify_view, name="payment-failed"),
    
    # Get plans (keep for compatibility)
    path("api/payment/plans/", views.api_get_plans, name="api-payment-plans"),
    
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
    path("api/student/chat/<int:tutor_id>/", views.api_student_chat_with_attachments, name="api-student-chat"),
    path("api/student/chat/list/", views.api_student_chat_list, name="api-student-chat-list"),
    path("api/tutor/chat/<int:student_id>/", views.api_tutor_chat, name="api-tutor-chat"),
    path("api/tutor/chat/list/", views.api_tutor_chat_list, name="api-tutor-chat-list"),
    path("api/chat/send/", views.api_send_chat, name="api-send-chat"),
    path("api/chat/upload/", views.api_chat_upload_file, name="api-chat-upload"),
    
    # Video call endpoints
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
    
    # ── TUTOR INTEREST API ───────────────────────────────────────────────────
    path('api/tutor-interest/', views.api_tutor_interest, name='api_tutor_interest'),
    path('api/admin/tutor-interests/', views.api_admin_tutor_interests, name='api_admin_tutor_interests'),
    path('api/admin/tutor-interests/<int:interest_id>/delete/', views.api_admin_tutor_interest_delete, name='api_admin_tutor_interest_delete'),
    path('api/admin/tutor-interests/clear-all/', views.api_admin_tutor_interests_clear_all, name='api_admin_tutor_interests_clear_all'),
    
    # ── PARENT API ────────────────────────────────────────────────────────────
    path('api/parent/children/', views.api_parent_children, name='api_parent_children'),
    path('api/parent/link-student/', views.api_parent_link_student, name='api_parent_link_student'),
    path('api/parent/create-student/', views.api_parent_create_student, name='api_parent_create_student'),
    path('api/parent/student/progress/<int:student_id>/', views.api_parent_student_progress, name='api_parent_student_progress'),
    path('api/parent/student/activity/<int:student_id>/<int:year>/<int:month>/', views.api_parent_student_activity_calendar, name='api_parent_student_activity_calendar'),
    path('api/parent/student/billing/<int:student_id>/', views.api_parent_student_billing, name='api_parent_student_billing'),
    path('api/parent/pay-for-student/<int:student_id>/', views.api_parent_pay_for_student, name='api_parent_pay_for_student'),
    path('api/parent/notifications/', views.api_parent_notifications, name='api_parent_notifications'),
    path('api/parent/notifications/<int:notification_id>/read/', views.api_parent_mark_notification_read, name='api_parent_mark_notification_read'),
    
    # ── STUDENT ACTIVITY TRACKING ─────────────────────────────────────────────
    path('api/track-student-activity/', views.api_track_student_activity, name='api_track_student_activity'),

    # =============================================================================
    # CONTENT MANAGEMENT API (PDF to Quiz System)
    # =============================================================================
    
    # Content Management URLs
    path('api/admin/content/extract-text/', views.api_extract_text_from_pdf, name='api_extract_text'),
    path('api/admin/content/save/', views.api_save_content, name='api_save_content'),
    path('api/admin/content/', views.api_list_content, name='api_list_content'),
    path('api/admin/content/<int:content_id>/', views.api_get_content_detail, name='api_content_detail'),
    path('api/admin/content/<int:content_id>/delete/', views.api_delete_content, name='api_delete_content'),
    path('api/admin/content/<int:content_id>/status/', views.api_update_content_status, name='api_update_status'),
    
    # Curriculum Data URLs
    path('api/admin/curriculums/', views.api_list_curriculums, name='api_list_curriculums'),
    
    # =============================================================================
    # CURRICULUM MANAGEMENT FULL CRUD URLs
    # =============================================================================
    
    # Curriculum CRUD
    path('api/admin/curriculums/add/', views.api_add_curriculum, name='api_add_curriculum'),
    path('api/admin/curriculums/<int:curriculum_id>/update/', views.api_update_curriculum, name='api_update_curriculum'),
    path('api/admin/curriculums/<int:curriculum_id>/delete/', views.api_delete_curriculum, name='api_delete_curriculum'),
    path('api/admin/curriculums/<int:curriculum_id>/', views.api_get_curriculum_detail, name='api_curriculum_detail'),
    
    # Grade CRUD
    path('api/admin/grades/add/', views.api_add_grade, name='api_add_grade'),
    path('api/admin/grades/<int:grade_id>/update/', views.api_update_grade, name='api_update_grade'),
    path('api/admin/grades/<int:grade_id>/delete/', views.api_delete_grade, name='api_delete_grade'),
    
    # Subject CRUD
    path('api/admin/subjects/', views.api_list_subjects, name='api_list_subjects'),
    path('api/admin/subjects/add/', views.api_add_subject, name='api_add_subject'),
    path('api/admin/subjects/<int:subject_id>/update/', views.api_update_subject, name='api_update_subject'),
    path('api/admin/subjects/<int:subject_id>/delete/', views.api_delete_subject, name='api_delete_subject'),
    path('api/admin/subjects/<int:subject_id>/', views.api_get_subject_detail, name='api_subject_detail'),
    
    # Topic CRUD
    path('api/admin/topics/<int:subject_id>/', views.api_list_topics, name='api_list_topics'),
    path('api/admin/topics/add/', views.api_add_topic, name='api_add_topic'),
    path('api/admin/topics/<int:topic_id>/delete/', views.api_delete_topic, name='api_delete_topic'),
    
    # Question Bank URLs
    path('api/admin/questions/', views.api_list_questions, name='api_list_questions'),
    
    # Student Quiz URLs
    path('api/student/quizzes/', views.api_student_quizzes, name='api_student_quizzes'),
    path('api/student/quizzes/<int:content_id>/take/', views.api_student_take_quiz, name='api_student_take_quiz'),
    path('api/student/quizzes/<int:content_id>/submit/', views.api_student_submit_quiz, name='api_student_submit_quiz'),
    path('api/student/quizzes/<int:content_id>/results/', views.api_student_quiz_results, name='api_student_quiz_results'),

    # Admin submission views
    path('api/admin/submissions/', views.api_admin_submissions, name='api_admin_submissions'),
    path('api/admin/submissions/<int:attempt_id>/', views.api_admin_submission_detail, name='api_admin_submission_detail'),
    path('api/admin/content/<int:content_id>/submissions/', views.api_admin_content_submissions, name='api_admin_content_submissions'),

    # Attachment serving
    path('api/admin/attachment/<int:attachment_id>/serve/', views.api_admin_serve_attachment_direct, name='api_admin_serve_attachment'),
    path('api/admin/attachment/<int:attachment_id>/download/', views.api_admin_serve_attachment_direct, name='api_admin_download_attachment'),
    path('api/admin/attachments/list/', views.api_admin_list_attachments, name='api_admin_list_attachments'),
    path('api/admin/attachments/content/<int:content_id>/', views.api_admin_list_attachments, name='api_admin_attachments_by_content'),
    path('api/attachment/<int:attachment_id>/', views.api_serve_attachment, name='api_serve_attachment'),
    path('api/submission/<int:attempt_id>/file/<int:question_index>/', views.api_download_submission_file, name='api_download_submission_file'),
]