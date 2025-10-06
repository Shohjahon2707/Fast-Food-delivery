# apps/delivery/views.py
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import Delivery


class DeliveryListView(ListView):
    model = Delivery
    template_name = "delivery/delivery_list.html"
    context_object_name = "deliveries"


class DeliveryCreateView(CreateView):
    model = Delivery
    fields = ["order", "courier", "address", "status"]
    template_name = "delivery/delivery_form.html"
    success_url = reverse_lazy("delivery_list")


class DeliveryUpdateView(UpdateView):
    model = Delivery
    fields = ["order", "courier", "address", "status"]
    template_name = "delivery/delivery_form.html"
    success_url = reverse_lazy("delivery_list")


class DeliveryDeleteView(DeleteView):
    model = Delivery
    template_name = "delivery/delivery_confirm_delete.html"
    success_url = reverse_lazy("delivery_list")
