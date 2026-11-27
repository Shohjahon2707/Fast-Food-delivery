import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def json_ld(data):
    # HTML parsers close script elements on a literal </script>, even for JSON.
    return mark_safe(json.dumps(data, ensure_ascii=True).replace("<", "\\u003c"))
