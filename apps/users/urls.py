from django.contrib.auth import views as auth
from django.urls import path

from apps.courier.views import register

from . import views

urlpatterns = [
    path("", views.home_view, name="user_home"),
    path("register/", views.register_user, name="register_user"),
    path("register-courier/", register, name="register_courier"),
    path("login/", views.RoleBasedLoginView.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="user_logout"),
    path("profile/", views.profile, name="profile"),
    path("preferences/", views.preferences, name="preferences"),
    path("preferences/save/", views.save_preferences, name="save_preferences"),
    path("password/reset/", auth.PasswordResetView.as_view(), name="password_reset"),
    path("password/reset/sent/", auth.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password/reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
