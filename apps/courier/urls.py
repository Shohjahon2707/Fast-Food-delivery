from django.urls import path
from django.views.generic import RedirectView
from .views import (
    CourierOrderListView,
    TakeOrderView,
    CourierRegisterView,
    CourierLoginView,
    ConfirmCashPaymentView,
)

urlpatterns = [

    path("", RedirectView.as_view(pattern_name='courier_login'), name='courier_home'),

    path("orders/", CourierOrderListView.as_view(), name="courier_orders"),
    path("orders/confirm-cash/<int:pk>/", ConfirmCashPaymentView.as_view(), name="confirm_cash_payment"),
    path("orders/take/<int:pk>/", TakeOrderView.as_view(), name="take_order"),
    path("register/", CourierRegisterView.as_view(), name="courier_register"),
    path("login/", CourierLoginView.as_view(), name="courier_login"),
]