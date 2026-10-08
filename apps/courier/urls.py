from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="courier_orders"), name="courier_home"),
    path("orders/", views.orders, name="courier_orders"),
    path("orders/take/<int:pk>/", views.take, name="take_order"),
    path("orders/complete/<int:pk>/", views.complete, name="confirm_cash_payment"),
    path("orders/problem/<int:pk>/", views.problem, name="courier_problem"),
    path("shift/", views.shift, name="courier_shift"),
    path("register/", views.register, name="courier_register"),
    path("login/", views.CourierLoginView.as_view(), name="courier_login"),
]
