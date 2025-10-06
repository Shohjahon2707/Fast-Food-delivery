from django.urls import path
from .views import (
    CourierListView,
    CourierCreateView,
    CourierUpdateView,
    CourierDeleteView,
)

urlpatterns = [
    path("", CourierListView.as_view(), name="courier_list"),
    path("create/", CourierCreateView.as_view(), name="courier_create"),
    path("<int:pk>/update/", CourierUpdateView.as_view(), name="courier_update"),
    path("<int:pk>/delete/", CourierDeleteView.as_view(), name="courier_delete"),
]
