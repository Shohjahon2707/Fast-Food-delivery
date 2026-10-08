from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def money(value):
    return f"{Decimal(value or 0):,.0f}".replace(",", " ")


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = str(value)
    return "?" + query.urlencode()
