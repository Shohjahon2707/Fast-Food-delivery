web: gunicorn project.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile -

worker: python manage.py dispatch_orders --loop
