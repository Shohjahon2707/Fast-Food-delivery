# apps/users/urls.py
from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    # Регистрация
    path("register/", views.register_user, name="register_user"),
    path("register-courier/", views.register_courier, name="register_courier"),

    # Логин
    path("login/", LoginView.as_view(template_name="users/login.html"), name="login"),

    # Logout через POST, перенаправление на home
    path("logout/", LogoutView.as_view(next_page="home"), name="logout"),
]
