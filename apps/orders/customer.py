from collections import Counter

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.cart.basket import MAX_QUANTITY, Basket
from apps.common.access import customer_required
from apps.orders.delivery import is_open

from .models import DishReview, Order, OrderReview


class ReviewForm(forms.Form):
    score = forms.IntegerField(label=_("Оценка ресторана"), min_value=1, max_value=5)
    comment = forms.CharField(
        label=_("Отзыв"), max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, dishes, data=None):
        super().__init__(data)
        for dish_id, name in dishes.items():
            self.fields[f"dish_{dish_id}"] = forms.IntegerField(
                label=_(name), min_value=1, max_value=5, required=False,
            )


@customer_required
@transaction.atomic
def review_order(request, order_id):
    orders = Order.objects.select_for_update()
    order = get_object_or_404(orders, pk=order_id, user=request.user, status="done")
    if OrderReview.objects.filter(order=order).exists():
        messages.info(request, _("Отзыв на этот заказ уже есть."))
        return redirect("order_detail", order_id=order.pk)
    dishes = dict(order.items.values_list("menu_item_id", "name"))
    form = ReviewForm(dishes, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        review = OrderReview.objects.create(
            order=order, score=form.cleaned_data["score"], comment=form.cleaned_data["comment"],
        )
        DishReview.objects.bulk_create([
            DishReview(review=review, dish_id=pk, score=score)
            for pk in dishes if (score := form.cleaned_data[f"dish_{pk}"]) is not None
        ])
        messages.success(request, _("Спасибо за отзыв."))
        return redirect("order_detail", order_id=order.pk)
    return render(request, "orders/review.html", {"order": order, "form": form})


@customer_required
@require_POST
@transaction.atomic
def repeat_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    available, unavailable, options = Counter(), [], {}
    for line in order.items.select_related("menu_item__restaurant").prefetch_related("menu_item__options"):
        item = line.menu_item
        if item.is_available and item.restaurant_id == order.restaurant_id and (
            item.restaurant is None or is_open(item.restaurant)
        ):
            available[item.pk] = min(MAX_QUANTITY, available[item.pk] + line.quantity)
            active = {option.pk for option in item.options.all() if option.active}
            requested = [option["id"] for option in line.options]
            options[item.pk] = {
                "option_ids": [pk for pk in requested if pk in active], "note": line.note,
            }
            unavailable.extend(option["name"] for option in line.options if option["id"] not in active)
        else:
            unavailable.append(line.name or item.name)
    if not available:
        messages.error(request, _("Доступных блюд для повтора пока нет."))
        return redirect("order_detail", order_id=order.pk)
    basket = Basket(request, lock=True)
    existing = {
        line.menu_item.pk: {"option_ids": line.option_ids, "note": line.note} for line in basket.lines
    }
    if basket.lines and (basket.contents != available or existing != options) and request.POST.get("replace") != "yes":
        return render(request, "cart/replace.html", {
            "repeat_order": order, "confirm_message": _("Заменить корзину блюдами из заказа?"),
        })
    basket.store(available, options)
    if unavailable:
        messages.info(request, _("Недоступные блюда: %(dishes)s") % {"dishes": ", ".join(unavailable)})
    messages.success(request, _("Доступные блюда добавлены в корзину."))
    return redirect("cart_detail")
