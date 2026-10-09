from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.access import operator_required
from apps.courier.models import Courier

from . import services
from .models import Order, Restaurant


@operator_required
def dashboard(request):
    status = request.GET.get("status", "issues")
    orders = Order.objects.select_related("user", "payment", "courier").prefetch_related(
        "items", "issues__author"
    )
    if status in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status)
    elif status == "issues":
        orders = orders.filter(
            Q(issues__resolved_at__isnull=True, issues__isnull=False) | ~Q(dispatch_alert="")
        ).distinct()
    elif status != "all":
        orders = orders.exclude(status__in=["done", "cancel"])
    return render(
        request,
        "operations/dashboard.html",
        {
            "page_obj": Paginator(orders, 15).get_page(request.GET.get("page")),
            "selected_status": status,
            "health": dispatch_health(),
            "stats": Order.objects.values("status").annotate(count=Count("id")),
            "couriers": Courier.objects.select_related("user").order_by("is_approved", "name"),
            "refunds": Order.objects.filter(payment__status="refund_due").select_related("payment"),
        },
    )


@operator_required
@require_POST
def action(request, pk):
    get_object_or_404(Order, pk=pk)
    action = request.POST.get("action")
    reason = request.POST.get("reason", "").strip()
    try:
        if action in ("cooking", "ready"):
            services.advance_order(pk, request.user, action)
        elif action == "cancel":
            services.cancel_order(pk, request.user, reason)
        elif action in ("resolve", "return"):
            services.resolve_issue(pk, request.user, reason, return_to_kitchen=action == "return")
        elif action == "reconcile" and request.POST.get("agreed") == "yes":
            services.reconcile_cash(pk, request.user, reason)
        elif action == "complete" and request.POST.get("received") == "yes":
            services.complete_by_admin(pk, request.user, reason)
        elif action == "refund" and request.POST.get("refunded") == "yes":
            services.confirm_refund(pk, request.user)
        else:
            raise ValidationError("Выберите действие и подтвердите его.")
        messages.success(request, "Заказ обновлён.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("operations")


@operator_required
@require_POST
@transaction.atomic
def approve_courier(request, pk):
    if not request.user.has_perm("courier.change_courier"):
        raise PermissionDenied
    courier = get_object_or_404(
        Courier.objects.select_for_update(), pk=pk, user__role="courier", user__is_staff=False
    )
    if Order.objects.filter(courier=courier, status="delivery").exists():
        messages.error(request, "Сначала решите вопрос с активной доставкой.")
    else:
        courier.is_approved = request.POST.get("approved") == "yes"
        courier.shift_status = "inactive"
        courier.latitude = courier.longitude = courier.location_updated_at = (
            courier.location_accuracy
        ) = None
        courier.save(
            update_fields=[
                "is_approved",
                "shift_status",
                "latitude",
                "longitude",
                "location_updated_at",
                "location_accuracy",
            ]
        )
        from .dispatch import dispatch_once

        transaction.on_commit(dispatch_once)
        messages.success(request, "Доступ курьера обновлён.")
    return redirect("operations")


def dispatch_health():
    from datetime import timedelta

    from django.utils import timezone

    restaurant = Restaurant.objects.first()
    configured = bool(
        restaurant
        and restaurant.address
        and restaurant.latitude is not None
        and restaurant.longitude is not None
    )
    healthy = bool(
        restaurant
        and restaurant.last_dispatch_at
        and restaurant.last_dispatch_at > timezone.now() - timedelta(seconds=60)
    )
    count = (
        Order.objects.exclude(status__in=["done", "cancel"])
        .filter(Q(issues__resolved_at__isnull=True, issues__isnull=False) | ~Q(dispatch_alert=""))
        .distinct()
        .count()
    )
    return {"count": count, "configured": configured, "healthy": healthy}


@operator_required
def alerts(request):
    from django.http import JsonResponse

    return JsonResponse(dispatch_health())
