# Procfile — used by Heroku, Railway, Render, and most PaaS platforms
# Runs the Django app with Gunicorn in production.
# Install gunicorn:  pip install gunicorn   (already in requirements.txt)

web: gunicorn timesdojo.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 60
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
