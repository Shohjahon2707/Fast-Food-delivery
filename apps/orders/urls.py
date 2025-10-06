from django.urls import path
from . import views

# УБЕРИТЕ app_name если он есть
# app_name = 'orders'  # ← ЗАКОММЕНТИРУЙТЕ ЭТУ СТРОЧКУ

urlpatterns = [
    path('', views.order_list, name='order_list'),
    path('<int:order_id>/', views.order_detail, name='order_detail'),
    path('create/', views.create_order, name='create_order'),
    path('success/<int:order_id>/', views.order_success, name='order_success'),
    path('mark_paid/<int:order_id>/', views.mark_as_paid, name='mark_as_paid'),
]