from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(role):
    def decorator(view):
        @login_required(login_url="courier_login" if role == "courier" else "login")
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.is_staff or request.user.role != role:
                raise PermissionDenied("Этот раздел предназначен для другого типа аккаунта.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


customer_required = role_required("customer")
courier_required = role_required("courier")


def operator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff or not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
