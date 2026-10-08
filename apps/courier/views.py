from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.access import courier_required
from apps.orders import services
from apps.orders.models import Order
from apps.users.views import RoleBasedLoginView, landing

from .forms import CourierLoginForm, CourierRegistrationForm
from .models import Courier


class CourierLoginView(RoleBasedLoginView):
    template_name = "couriers/login.html"
    authentication_form = CourierLoginForm


def register(request):
    if request.user.is_authenticated:
        return redirect(landing(request.user))
    form = CourierRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Заявка отправлена! После одобрения можно будет выйти на смену.")
        return redirect("courier_orders")
    return render(request, "couriers/register.html", {"form": form})


@courier_required
def orders(request):
    courier = get_object_or_404(Courier, user=request.user)
    current = (
        Order.objects.filter(courier=courier, status="delivery")
        .select_related("payment")
        .prefetch_related("items", "issues")
        .first()
    )
    available = Order.objects.none()
    if courier.is_approved and courier.shift_status == "active" and not current:
        available = (
            Order.objects.filter(status="ready", courier__isnull=True)
            .exclude(issues__resolved_at__isnull=True, issues__isnull=False)
            .order_by("created_at")[:30]
        )
    history = Order.objects.filter(courier=courier, status__in=["done", "cancel"])[:10]
    return render(
        request,
        "couriers/courier_orders.html",
        {
            "courier": courier,
            "current": current,
            "orders": available,
            "history": history,
            "open_issue": current.issues.filter(resolved_at__isnull=True).first()
            if current
            else None,
            "completed_count": Order.objects.filter(courier=courier, status="done").count(),
        },
    )


@courier_required
@require_POST
@transaction.atomic
def shift(request):
    courier = get_object_or_404(Courier.objects.select_for_update(), user=request.user)
    if not courier.is_approved:
        messages.error(request, "Дождитесь одобрения администратора.")
    elif Order.objects.filter(courier=courier, status="delivery").exists():
        messages.error(request, "Сначала завершите доставку или сообщите о проблеме.")
    else:
        courier.shift_status = "inactive" if courier.shift_status == "active" else "active"
        courier.save(update_fields=["shift_status"])
    return redirect("courier_orders")


@courier_required
@require_POST
def take(request, pk):
    get_object_or_404(Order, pk=pk)
    try:
        services.take_order(pk, request.user)
        messages.success(request, "Заказ ваш. Контакты получателя доступны ниже.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("courier_orders")


@courier_required
@require_POST
def complete(request, pk):
    get_object_or_404(Order, pk=pk, courier__user=request.user)
    if request.POST.get("cash_received") != "yes":
        messages.error(request, "Подтвердите передачу заказа и получение полной суммы наличными.")
    else:
        try:
            services.deliver_order(pk, request.user)
            messages.success(request, "Доставка завершена. Спасибо за работу!")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return redirect("courier_orders")


@courier_required
@require_POST
def problem(request, pk):
    get_object_or_404(Order, pk=pk, courier__user=request.user)
    try:
        services.report_issue(pk, request.user, request.POST.get("reason", ""))
        messages.success(request, "Администратор получил обращение. Ожидайте решения.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("courier_orders")
