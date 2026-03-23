# TimesTable Dojo — Django Backend

A full-stack Django web application for gamified multiplication table learning.
Students earn karate-style belts (White → Master), tutors coach them,
and a custom admin dashboard gives operators full visibility.

---

## Project Structure

```
timesdojo_django/
│
├── manage.py                        # Django CLI entry point
├── requirements.txt                 # pip dependencies
├── Procfile                         # Heroku/Railway/Render deployment
├── .env.example                     # Environment variable template
├── .gitignore
│
├── timesdojo/                       # Django PROJECT (config package)
│   ├── __init__.py
│   ├── settings.py                  # All settings, env-aware
│   ├── urls.py                      # Root URL config — delegates to dojo/urls.py
│   ├── wsgi.py                      # Production WSGI entry point
│   └── asgi.py                      # Async entry point (future use)
│
└── dojo/                            # Django APP (all business logic)
    ├── __init__.py
    ├── apps.py                      # AppConfig — wires up signals
    ├── models.py                    # All ORM models (7 models)
    ├── views.py                     # All views — page views + JSON API
    ├── urls.py                      # All URL patterns (named, namespaced)
    ├── admin.py                     # Django admin registrations
    ├── signals.py                   # post_save: auto-creates belt rows on register
    │
    ├── migrations/
    │   ├── __init__.py
    │   └── 0001_initial.py          # Full initial schema migration
    │
    ├── management/
    │   └── commands/
    │       └── seed.py              # python manage.py seed [--with-students N]
    │
    ├── templates/
    │   └── dojo/
    │       ├── student_app.html     # Student SPA (full HTML/CSS/JS)
    │       └── admin_app.html       # Admin SPA (full HTML/CSS/JS)
    │
    └── static/
        └── dojo/
            ├── css/
            │   └── base.css         # Shared CSS design tokens
            └── js/
                └── csrf.js          # Auto-attaches CSRF token to fetch()
```

---

## How It Works

### Architecture Pattern
This is a **"thin template, fat JS"** architecture:

1. Django renders a single HTML file per section (student app, admin app).
2. The HTML file contains all CSS and JavaScript inline — it is a full SPA.
3. The JS calls Django JSON API endpoints (`/api/...`) for all data.
4. Django handles auth via **server-side sessions** (stored in the DB).
5. The CSRF token is auto-attached by `csrf.js` to every non-GET `fetch()`.

This means:
- No page reloads after the initial load.
- Django is the source of truth for all data and auth.
- The frontend is completely decoupled from the template engine
  (no `{{ variable }}` in the SPA — just `{% load static %}` at the top).

### Models

| Model | Purpose |
|---|---|
| `User` | Extends `AbstractUser`. Adds `role`, `county`, `school`, `spec`, `is_paid`. |
| `BeltProgress` | One row per (user, belt). 9 rows auto-created on student register via signal. |
| `FactMemory` | Per-fact accuracy + timing data. Max 400 rows per student (20×20 grid). |
| `TrainingSession` | One row per completed game session. Powers all analytics. |
| `UserBadge` | Junction table for earned badges. |
| `Streak` | One row per student. Updated on every session completion. |
| `TutorRequest` | Student → Tutor connection request with status lifecycle. |

### Views

All views live in `dojo/views.py`. Two types:

**Page views** (class-based, return HTML):
- `StudentAppView` → `GET /` → renders `student_app.html`
- `AdminAppView` → `GET /admin/` → renders `admin_app.html`

**API views** (function-based, return JSON):
- Protected by `@require_role("student")`, `@require_role("tutor")`, or `@admin_only`
- Consume JSON body via `json_body(request)`
- Return `ok(...)` or `err(...)` helper responses

### URL Namespacing
All URLs are in the `dojo` namespace. Reference them with:
```python
from django.urls import reverse
reverse("dojo:api-student-profile")   # → /api/student/profile/
reverse("dojo:home")                   # → /
```

---

## Local Development Setup

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd timesdojo_django

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment (optional for local dev — defaults are fine)
cp .env.example .env
# Edit .env if you want custom settings

# 5. Run migrations (creates db.sqlite3)
python manage.py migrate

# 6. Seed the database
python manage.py seed                    # creates admin + 11 tutors
python manage.py seed --with-students 50 # also creates 50 demo students

# 7. Start the development server
python manage.py runserver

# 8. Open your browser
#   Student App  →  http://localhost:8000/
#   Admin Panel  →  http://localhost:8000/admin/
#   Django Admin →  http://localhost:8000/django-admin/
```

**Default credentials after seeding:**

| Role | Email | Password |
|---|---|---|
| Admin | admin@timesdojo.com | dojo2025 |
| Tutors | e.g. peter.karanja@tutors.dojo.co.ke | tutor1234 |
| Demo students | e.g. amara.osei0@students.dojo.co.ke | student1234 |

---

## API Reference

### Auth
| Method | URL | Description |
|---|---|---|
| POST | `/api/register/` | Register student or tutor |
| POST | `/api/login/` | Login (any role) |
| POST | `/api/logout/` | Logout |
| GET | `/api/me/` | Current user info |

### Student
| Method | URL | Description |
|---|---|---|
| GET | `/api/student/profile/` | Full profile: belts, badges, facts, streak, stats |
| GET | `/api/student/belts/` | Belt progress dict |
| POST | `/api/student/belts/update/` | Update one belt (pass/fail/progress) |
| POST | `/api/student/session/save/` | Save completed session, award badges |
| GET | `/api/student/facts/` | Fact memory grid |
| POST | `/api/student/facts/update/` | Bulk update fact performance |
| GET | `/api/student/badges/` | Earned badge list |
| GET | `/api/student/streak/` | Streak count + last date |
| GET | `/api/student/leaderboard/?scope=school\|county\|national` | Leaderboard |
| GET | `/api/student/tutors/?name=&county=&spec=` | Search tutors |
| POST | `/api/student/request-tutor/` | Send tutor request |
| GET | `/api/student/my-requests/` | My tutor requests |

### Tutor
| Method | URL | Description |
|---|---|---|
| GET | `/api/tutor/requests/` | Incoming student requests |
| POST | `/api/tutor/request/update/` | Accept or reject a request |

### Admin
| Method | URL | Description |
|---|---|---|
| POST | `/api/admin/login/` | Admin login |
| GET | `/api/admin/overview/` | Platform KPIs |
| GET | `/api/admin/students/` | All students with stats |
| GET | `/api/admin/tutors/` | All tutors |
| GET | `/api/admin/belts/` | Belt analytics |
| GET | `/api/admin/knowledge/` | Aggregated fact heatmap data |
| GET | `/api/admin/activity/` | Recent training sessions |
| GET | `/api/admin/county/` | Students per county |
| GET | `/api/admin/leaderboard/` | National leaderboard |
| GET | `/api/admin/tutor-requests/` | All tutor requests |
| POST | `/api/admin/user/suspend/` | Suspend a user |
| POST | `/api/admin/user/upgrade/` | Grant paid access |
| POST | `/api/admin/tutor/approve/` | Verify a tutor |

---

## Production Deployment (Railway / Render / Heroku)

```bash
# Install gunicorn (already in requirements.txt)
pip install gunicorn

# Collect static files
python manage.py collectstatic --noinput

# Set these environment variables on your platform:
DJANGO_SECRET_KEY=<generate a real key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgres://...   # your managed postgres URL

# The Procfile handles migrate + collectstatic + gunicorn automatically
```

---

## Adding Features

**New model field:**
1. Add field to `dojo/models.py`
2. `python manage.py makemigrations`
3. `python manage.py migrate`

**New API endpoint:**
1. Write the view function in `dojo/views.py`
2. Add the URL pattern to `dojo/urls.py`
3. Call it from the frontend JS in the template

**New belt:**
1. Add to `BELT_CHOICES` and `BELT_ORDER` in `dojo/models.py`
2. Add to `BELTS` array in `student_app.html` JS
3. `python manage.py makemigrations && python manage.py migrate`
