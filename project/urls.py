from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.common.health import readiness
from apps.menu.views import home, restaurant_detail, smart_lunch
from apps.orders import analytics, kitchen, operations, partner

admin.site.site_header = "Тёпло · управление"
admin.site.site_title = "Тёпло"
admin.site.index_title = "Данные ресторана"
urlpatterns = [
    path("healthz/", readiness, name="readiness"),
    path("kitchen/", kitchen.board, name="kitchen"),
    path("kitchen/login/", kitchen.KitchenLoginView.as_view(), name="kitchen_login"),
    path("kitchen/<int:pk>/", kitchen.action, name="kitchen_action"),
    path("admin/", admin.site.urls),
    path("partner/login/", partner.PartnerLoginView.as_view(), name="partner_login"),
    path("partner/", partner.dashboard, name="partner_dashboard"),
    path("partner/menu/new/", partner.edit_dish, name="partner_add_dish"),
    path("partner/menu/<int:pk>/", partner.edit_dish, name="partner_edit_dish"),
    path("", home, name="home"),
    path("restaurants/<int:pk>/", restaurant_detail, name="restaurant_detail"),
    path("smart-lunch/", smart_lunch, name="smart_lunch"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("menu/", include("apps.menu.urls")),
    path("cart/", include("apps.cart.urls")),
    path("orders/", include("apps.orders.urls")),
    path("users/", include("apps.users.urls")),
    path("couriers/", include("apps.courier.urls")),
    path("payments/", include("apps.payments.urls")),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("operations/alerts/", operations.alerts, name="operations_alerts"),
    path("operations/", operations.dashboard, name="operations"),
    path("operations/analytics/", analytics.dashboard, name="order_analytics"),
    path("operations/order/<int:pk>/", operations.action, name="operation_action"),
    path("operations/courier/<int:pk>/", operations.approve_courier, name="approve_courier"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
