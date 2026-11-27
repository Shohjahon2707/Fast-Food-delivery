from django.urls import path

from . import views

urlpatterns = [
    path("", views.cart_detail, name="cart_detail"),
    path("add/<int:item_id>/", views.add_to_cart, name="add_to_cart"),
    path("add-lunch/", views.add_lunch, name="add_lunch"),
    path("choose-basket/", views.resolve_guest_basket, name="resolve_guest_basket"),
    path("remove/<int:cart_item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("update/<int:item_id>/", views.update_quantity, name="update_quantity"),
]
