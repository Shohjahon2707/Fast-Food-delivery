from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    register_user,
    register_courier,
    RoleBasedLoginView,
    home_view
)

urlpatterns = [
    path("", home_view, name="home"),
    path("register/", register_user, name="register_user"),
    path("register-courier/", register_courier, name="register_courier"),
    path("login/", RoleBasedLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
]
