from django.contrib import admin
from apps.delivery.models import Courier,Delivery
# Register your models here.
admin.site.register(Courier)
admin.site.register(Delivery)