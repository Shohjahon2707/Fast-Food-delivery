from django.urls import path

from . import payme, views

urlpatterns = [
    path("payme/callback/", payme.callback, name="payme_callback"),
    path("payme/<int:order_id>/", views.start_payme, name="start_payme"),
    path("pay/card/<int:order_id>/", views.unavailable_card, name="pay_with_card"),
    path("confirm/", views.unavailable_card, name="confirm_payment"),
    path("cash/success/<int:order_id>/", views.cash_payment_success, name="cash_success"),
]
