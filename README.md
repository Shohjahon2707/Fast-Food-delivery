# Fast-Food-delivery
Django project for a Fast-Food delivery service

## Local development

Use Python 3.12 and run these commands from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

SQLite data is stored locally in `db.sqlite3`. Uploaded category and menu images
are stored in `media/`; preserve them together with the database.

## Static files and deployment

`staticfiles/` is generated output and is excluded from Git. Generate it during
deployment:

```bash
python manage.py collectstatic --noinput
```

The `Procfile` starts Gunicorn. Production hosting must also serve collected
static files and uploaded media. The current settings are for development and
need a separate production configuration before public deployment.

## Validation

```bash
python manage.py check
python manage.py test
```

The regression tests cover courier registration, cart ownership, cash checkout,
courier payment confirmation, home routing, and saved order prices. For a basic
smoke check, start the server and check `/`, `/menu/`, `/users/login/`, and
`/users/register/`.
