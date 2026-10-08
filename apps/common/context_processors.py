from django.conf import settings
from django.db.models import Sum

from apps.cart.models import CartItem


def site_context(request):
    count = 0
    if request.user.is_authenticated and request.user.is_customer:
        count = (
            CartItem.objects.filter(cart__user=request.user).aggregate(n=Sum("quantity"))["n"] or 0
        )
    preference = request.get_signed_cookie("food_preferences", default="", salt="food-preferences")
    parts = preference.split(":")
    return {
        "cart_count": count,
        "delivery_fee": settings.DELIVERY_FEE,
        "free_delivery_from": settings.FREE_DELIVERY_FROM,
        "preferences_saved": bool(preference),
        "preferred_diet": parts[0] if parts and parts[0] in ("all", "vegetarian") else "all",
        "reduce_motion": len(parts) > 1 and parts[1] == "reduce",
        "can_operate": request.user.is_authenticated
        and request.user.is_staff
        and request.user.has_perm("orders.change_order"),
    }
