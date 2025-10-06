# apps/courier/views.py
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import Courier


class CourierListView(ListView):
    model = Courier
    template_name = "courier/courier_list.html"
    context_object_name = "couriers"


class CourierCreateView(CreateView):
    model = Courier
    fields = ["name", "phone", "vehicle_type", "shift_status"]
    template_name = "courier/courier_form.html"
    success_url = reverse_lazy("courier_list")


class CourierUpdateView(UpdateView):
    model = Courier
    fields = ["name", "phone", "vehicle_type", "shift_status"]
    template_name = "courier/courier_form.html"
    success_url = reverse_lazy("courier_list")


class CourierDeleteView(DeleteView):
    model = Courier
    template_name = "courier/courier_confirm_delete.html"
    success_url = reverse_lazy("courier_list")
