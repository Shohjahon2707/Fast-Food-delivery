from django.urls import path
from . import views



urlpatterns = [
    path('pay/card/<int:order_id>/', views.start_payment_card, name='pay_with_card'),
    path('confirm/', views.confirm_payment, name='confirm_payment'),
    path('cash/success/<int:order_id>/', views.cash_payment_success, name='cash_success'),
]