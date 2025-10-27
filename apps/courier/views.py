from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy

from .models import Courier
from .forms import CourierRegistrationForm
from apps.orders.models import Order


class CourierOrderListView(LoginRequiredMixin, ListView):
    template_name = "couriers/courier_orders.html"
    context_object_name = "orders"
    
    def get_queryset(self):
        return Order.objects.filter(
            courier__isnull=True
        ).exclude(
            status__in=['cancel', 'done', 'delivery']
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        courier = getattr(self.request.user, 'courier_profile', None)
        context['my_orders'] = Order.objects.filter(courier=courier, status='delivery') if courier else Order.objects.none()
        context['current_courier'] = courier
        return context


class TakeOrderView(LoginRequiredMixin, View):
    """Взять заказ в доставку"""
    def post(self, request, pk):
        courier = getattr(request.user, 'courier_profile', None)
        if not courier:
            return render(request, "couriers/error.html", {'error': 'У вас нет профиля курьера.'})

        try:
            order = Order.objects.get(pk=pk, courier__isnull=True)
        except Order.DoesNotExist:
            messages.error(request, "❌ Заказ уже занят или не найден.")
            return redirect('courier_orders')

        order.courier = courier
        order.status = 'delivery'
        order.save()

        messages.success(request, f'🚚 Заказ #{order.id} успешно взят в доставку!')
        return redirect('courier_orders')


class CourierRegisterView(CreateView):
    """Регистрация курьера"""
    form_class = CourierRegistrationForm
    template_name = "couriers/register.html"

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, '✅ Регистрация прошла успешно!')
        return redirect('courier_orders')


class CourierLoginView(LoginView):
    template_name = "couriers/login.html"

    def get_success_url(self):
        return reverse_lazy('courier_orders')
