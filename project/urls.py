from django.contrib import admin
from django.urls import path, include
from apps.menu import views as menu_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
urlpatterns = [
    path("admin/", admin.site.urls),
    path("couriers/", include("apps.courier.urls")),
    path("", menu_views.home, name="home"),
    path("menu/", include("apps.menu.urls")),
    path("cart/", include("apps.cart.urls")),
    path("orders/", include("apps.orders.urls")),
    path("users/", include("apps.users.urls")),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("payments/", include("apps.payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)