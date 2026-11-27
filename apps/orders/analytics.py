from datetime import timedelta

from django import forms
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.common.access import operator_required

from .models import Order, OrderItem


class PeriodForm(forms.Form):
    start = forms.DateField(label=_("Начало периода"), widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label=_("Конец периода"), widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and start > end:
            raise forms.ValidationError(_("Начало периода должно быть раньше конца."))
        return data


@operator_required
def dashboard(request):
    today = timezone.localdate()
    form = PeriodForm(request.GET or {"start": today - timedelta(days=29), "end": today})
    stats, popular = None, []
    if form.is_valid():
        orders = Order.objects.filter(
            created_at__date__range=(form.cleaned_data["start"], form.cleaned_data["end"]),
        )
        delivered = orders.filter(status="done")
        stats = {
            "placed": orders.count(), "delivered": delivered.count(),
            "revenue": delivered.filter(payment__status="paid").aggregate(
                total=Sum("total_price"),
            )["total"] or 0,
        }
        stats["completion_rate"] = (
            stats["delivered"] * 100 / stats["placed"] if stats["placed"] else 0
        )
        popular = (
            OrderItem.objects.filter(order__in=delivered)
            .values("name").annotate(portions=Sum("quantity"), orders=Count("order_id", distinct=True))
            .order_by("-portions", "name")[:10]
        )
    return render(request, "operations/analytics.html", {
        "form": form, "stats": stats, "popular": popular,
    })
