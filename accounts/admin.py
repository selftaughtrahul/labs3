from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Profile", {"fields": ("phone_number", "date_of_birth", "bio")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Profile", {"fields": ("phone_number", "date_of_birth", "bio")}),
    )
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "phone_number",
        "is_staff",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "phone_number",
    )
