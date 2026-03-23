"""
timesdojo/wsgi.py
-----------------
WSGI entry point for production deployment.
Used by:  gunicorn timesdojo.wsgi:application
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timesdojo.settings")
application = get_wsgi_application()
