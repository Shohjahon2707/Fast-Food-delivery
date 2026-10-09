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
    from django.utils import timezone

    from apps.orders.dispatch import LOCATION_TTL
    from apps.orders.models import DeliveryOffer, Restaurant

    offer = (
        DeliveryOffer.objects.filter(
            courier=courier, state__in=["pending", "accepted"], expires_at__gt=timezone.now()
        )
        .select_related("order")
        .first()
    )
    restaurant, _ = Restaurant.objects.get_or_create(pk=1)
    history = Order.objects.filter(courier=courier, status__in=["done", "cancel"])[:10]
    return render(
        request,
        "couriers/courier_orders.html",
        {
            "courier": courier,
            "current": current,
            "offer": offer,
            "restaurant": restaurant,
            "location_fresh": courier.location_updated_at is not None
            and courier.location_updated_at >= timezone.now() - LOCATION_TTL,
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
        if courier.shift_status == "inactive":
            courier.latitude = courier.longitude = courier.location_updated_at = (
                courier.location_accuracy
            ) = None
        courier.save(
            update_fields=[
                "shift_status",
                "latitude",
                "longitude",
                "location_updated_at",
                "location_accuracy",
            ]
        )
        from apps.orders.dispatch import dispatch_once

        transaction.on_commit(dispatch_once)
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


@courier_required
@require_POST
def offer_response(request, pk):
    from apps.orders.dispatch import respond
    from apps.orders.models import DeliveryOffer

    get_object_or_404(DeliveryOffer, pk=pk, courier__user=request.user)
    if request.POST.get("action") not in ("accept", "decline"):
        return redirect("courier_orders")
    try:
        respond(pk, request.user, request.POST.get("action") == "accept")
        messages.success(
            request,
            "Заказ зарезервирован за вами."
            if request.POST.get("action") == "accept"
            else "Предложение передано следующему курьеру.",
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("courier_orders")


@courier_required
@require_POST
@transaction.atomic
def location(request):
    from decimal import Decimal, InvalidOperation
    from math import isfinite

    from django.http import JsonResponse
    from django.utils import timezone

    courier = get_object_or_404(Courier.objects.select_for_update(), user=request.user)
    if not courier.is_approved or courier.shift_status == "inactive":
        return JsonResponse({"error": "Геопозиция доступна только во время смены."}, status=403)
    try:
        lat, lon = (
            Decimal(request.POST.get("latitude", "")),
            Decimal(request.POST.get("longitude", "")),
        )
        accuracy = float(request.POST.get("accuracy", ""))
        if (
            not lat.is_finite()
            or not lon.is_finite()
            or not (-90 <= lat <= 90 and -180 <= lon <= 180)
            or not isfinite(accuracy)
            or not 0 < accuracy <= 10000
        ):
            raise ValueError
    except (ValueError, InvalidOperation):
        return JsonResponse({"error": "Некорректные координаты."}, status=400)
    courier.latitude, courier.longitude = (
        lat.quantize(Decimal("0.000001")),
        lon.quantize(Decimal("0.000001")),
    )
    courier.location_accuracy, courier.location_updated_at = accuracy, timezone.now()
    courier.save(
        update_fields=["latitude", "longitude", "location_accuracy", "location_updated_at"]
    )
    from apps.orders.dispatch import dispatch_once

    transaction.on_commit(dispatch_once)
    return JsonResponse({"ok": True, "precise": accuracy <= 200})


@courier_required
def live(request):
    from django.http import JsonResponse
    from django.utils import timezone

    from apps.orders.models import DeliveryOffer

    courier = get_object_or_404(Courier, user=request.user)
    offer = DeliveryOffer.objects.filter(
        courier=courier, state__in=["pending", "accepted"], expires_at__gt=timezone.now()
    ).first()
    current = Order.objects.filter(courier=courier, status="delivery").first()
    return JsonResponse(
        {
            "offer": offer.pk if offer else None,
            "state": offer.state if offer else None,
            "current": current.pk if current else None,
            "approved": courier.is_approved,
        }
    )


@courier_required
@require_POST
@transaction.atomic
def eta(request, pk):
    from datetime import timedelta

    from django.utils import timezone

    order = get_object_or_404(
        Order.objects.select_for_update(of=("self",)),
        pk=pk,
        courier__user=request.user,
        status="delivery",
    )
    minutes = request.POST.get("minutes")
    if minutes not in ("1", "5", "10", "15"):
        messages.error(request, "Выберите время до вручения.")
    else:
        order.delivery_eta = timezone.now() + timedelta(minutes=int(minutes))
        order.save(update_fields=["delivery_eta"])
        from apps.orders.dispatch import dispatch_once

        transaction.on_commit(dispatch_once)
        messages.success(
            request, "Прогноз обновлён. Следующий заказ можно зарезервировать заранее."
        )
    return redirect("courier_orders")


@courier_required
@require_POST
@transaction.atomic
def stop_location(request):
    from django.http import JsonResponse

    from apps.orders.dispatch import dispatch_once
    from apps.orders.models import DeliveryOffer

    courier = get_object_or_404(Courier.objects.select_for_update(), user=request.user)
    courier.latitude = courier.longitude = courier.location_updated_at = (
        courier.location_accuracy
    ) = None
    courier.save(
        update_fields=["latitude", "longitude", "location_updated_at", "location_accuracy"]
    )
    DeliveryOffer.objects.filter(courier=courier, state__in=["pending", "accepted"]).update(
        state="cancelled"
    )
    transaction.on_commit(dispatch_once)
    return JsonResponse({"ok": True})
