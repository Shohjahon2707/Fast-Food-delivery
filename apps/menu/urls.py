from django.urls import path
from . import views

urlpatterns = [
    path("", views.menu_list, name="menu_list"),
    path("category/<int:category_id>/", views.category_detail, name="category_detail"),
    path("item/<int:item_id>/", views.menu_item_detail, name="menu_item_detail"),
]
