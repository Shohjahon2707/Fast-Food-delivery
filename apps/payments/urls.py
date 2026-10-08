from django.urls import path

from . import views

urlpatterns = [
    path("pay/card/<int:order_id>/", views.unavailable_card, name="pay_with_card"),
    path("confirm/", views.unavailable_card, name="confirm_payment"),
    path("cash/success/<int:order_id>/", views.cash_payment_success, name="cash_success"),
]
