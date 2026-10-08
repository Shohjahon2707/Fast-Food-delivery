from django.urls import path

from . import views

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path("create/", views.create_order, name="create_order"),
    path("<int:order_id>/status/", views.live_status, name="order_status"),
    path("<int:order_id>/", views.order_detail, name="order_detail"),
    path("success/<int:order_id>/", views.order_success, name="order_success"),
    path("<int:order_id>/cancel/", views.cancel, name="cancel_order"),
]
