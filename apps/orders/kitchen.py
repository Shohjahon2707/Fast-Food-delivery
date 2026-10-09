from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.access import kitchen_required
from apps.users.views import RoleBasedLoginView

from .models import Order
from .services import advance_order


class KitchenLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.has_perm("orders.work_kitchen") or not (
            user.role == "kitchen" or user.is_staff
        ):
            raise ValidationError("Этот вход только для команды кухни.")


class KitchenLoginView(RoleBasedLoginView):
    template_name = "kitchen/login.html"
    authentication_form = KitchenLoginForm

    def get_success_url(self):
        from django.urls import reverse

        return reverse("kitchen")


@kitchen_required
def board(request):
    return render(
        request,
        "kitchen/board.html",
        {
            "orders": Order.objects.filter(status__in=["new", "cooking", "ready"])
            .prefetch_related("items", "issues")
            .order_by("created_at")[:60]
        },
    )


@kitchen_required
@require_POST
def action(request, pk):
    get_object_or_404(Order, pk=pk)
    try:
        advance_order(pk, request.user, request.POST.get("action"))
        messages.success(request, "Кухня обновлена. Курьер назначается автоматически.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("kitchen")
