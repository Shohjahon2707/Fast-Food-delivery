# Развёртывание

## Настройки

Для production экспортируйте:

```text
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<случайная строка минимум 50 символов>
DJANGO_ALLOWED_HOSTS=food.example.com
CSRF_TRUSTED_ORIGINS=https://food.example.com
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
MEDIA_ROOT=/var/lib/delivery/media
REDIS_URL=redis://127.0.0.1:6379/1
```

Сгенерировать ключ можно командой `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` и сохранить в менеджере секретов хостинга. При выключенном DEBUG приложение не запустится с локальным ключом.

Используйте PostgreSQL для нескольких процессов и конкурентных заказов. SQLite предназначена для простого локального запуска. Redis делает ограничение попыток входа общим для всех процессов; без `REDIS_URL` кэш локален одному процессу. Планируйте резервное копирование БД и media. Диск media должен переживать перезапуск и новую сборку приложения.

SMTP для восстановления пароля:

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<SMTP server>
EMAIL_PORT=587
EMAIL_HOST_USER=<username>
EMAIL_HOST_PASSWORD=<secret>
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=<verified sender>
```

Локальный backend выводит письмо в консоль. Он не доставляет письма в реальный ящик. Секреты не коммитить.

## Сборка и запуск

С установленными production-переменными:

```bash
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy --fail-level WARNING
python manage.py seed_menu  # только если нужен стартовый каталог
python manage.py createsuperuser
gunicorn project.wsgi:application --bind 127.0.0.1:8000 --workers 2 --access-logfile -
```

Procfile читает порт из `$PORT` для платформенных хостингов. HTTPS завершается на reverse proxy. Если вы контролируете proxy и он **перезаписывает** `X-Forwarded-Proto`, установите `TRUST_PROXY_SSL=true`. Иначе оставьте выключенным. Cookies сессии и CSRF в production требуют HTTPS.

Пример расположений внутри TLS-сервера Nginx:

```nginx
location /media/ {
    alias /var/lib/delivery/media/;
    autoindex off;
    expires 7d;
    add_header X-Content-Type-Options nosniff always;
}
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Nginx раздаёт media, а WhiteNoise — собранную статику. Не направляйте media в интерпретаторы скриптов. Для reverse proxy настройте ограничение запросов на страницы входа и восстановления пароля. Встроенное ограничение входа учитывает `REMOTE_ADDR`, поэтому при proxy без отдельного ограничения все пользователи могут разделять один лимит.

## Перед приёмом заказов

Проверьте каталог, реальные цены, фото/состав, зону доставки и тарифы; назначьте сотрудника, который обрабатывает рабочую панель; одобрите курьеров; выполните тестовый заказ до конца и проверьте восстановление пароля через SMTP. Кнопка подтверждения возврата — запись результата реального возврата, не банковский перевод.

Онлайн-эквайринг не включён. Для добавления провайдера потребуются реальные реквизиты мерчанта, серверная проверка суммы/валюты и подписей, идемпотентный webhook и обработка отмены/возврата. Не собирайте реквизиты карты в Django-формах.
