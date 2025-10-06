from django.contrib import admin
from apps.menu.models import MenuItem, Category
# Register your models here.
admin.site.register(Category)
admin.site.register(MenuItem)