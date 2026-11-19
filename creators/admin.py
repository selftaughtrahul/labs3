from django.contrib import admin
from django.utils.html import format_html

from campaigns.admin import CreatorDealInline
from creators.models import Country, Creator, CreatorRate, DeliverableType, Language

from .forms import CreatorAdminForm, CreatorRateForm, CreatorRateFormSet


class CreatorRateInline(admin.StackedInline):
    model = CreatorRate
    form = CreatorRateForm
    formset = CreatorRateFormSet
    extra = 0
    autocomplete_fields = ("deliverables",)
    fields = ("deliverables", "price", "currency")
    verbose_name_plural = "rate card"


@admin.register(CreatorRate)
class CreatorRateAdmin(admin.ModelAdmin):
    form = CreatorRateForm
    empty_value_display = "—"
    list_display = ("creator", "deliverable_list", "price", "currency", "updated_at")
    list_filter = ("currency",)
    list_select_related = ("creator",)
    search_fields = ("creator__influencer_name", "creator__email", "deliverables__name")
    autocomplete_fields = ("creator", "deliverables")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("deliverables")

    @admin.display(description="Deliverables")
    def deliverable_list(self, obj):
        names = sorted(item.name for item in obj.deliverables.all())
        return " + ".join(names) if names else "—"


@admin.register(Country, Language, DeliverableType)
class NameAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    form = CreatorAdminForm
    empty_value_display = "—"
    list_select_related = ("added_by", "country", "language")
    list_display = (
        "influencer_name",
        "platform",
        "tier",
        "country",
        "niche_list",
        "language",
        "followers_display",
        "email",
        "profile",
        "is_profile_checked",
        "added_by",
    )
    list_display_links = ("influencer_name",)
    list_filter = ("platform", "tier", "source", "is_profile_checked", "country")
    search_fields = (
        "influencer_name",
        "email",
        "profile_link",
        "country__name",
        "language__name",
        "added_by__username",
    )
    date_hierarchy = "added_at"
    radio_fields = {"platform": admin.HORIZONTAL}
    inlines = (CreatorRateInline, CreatorDealInline)
    readonly_fields = ("id", "updated_at")
    fieldsets = (
        (
            "Profile",
            {
                "description": "Stored once and reused. The same person on two platforms is two profiles.",
                "fields": ("platform", "profile_link", "influencer_name", "email"),
            },
        ),
        (
            "Audience",
            {
                "fields": (
                    "niche",
                    "country",
                    "language",
                    "tier",
                    "followers",
                    "engagement_rate",
                    "avg_views",
                    "geo",
                    "female_pct",
                    "male_pct",
                    "audience_insights",
                ),
            },
        ),
        (
            "Scouting",
            {
                "fields": (
                    "is_profile_checked",
                    "source",
                    "other_contact",
                    "added_by",
                    "added_at",
                ),
            },
        ),
        ("Record", {"fields": ("id", "updated_at")}),
    )

    class Media:
        css = {"all": ("creators/filters.css",)}
        js = ("creators/filters.js",)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("added_by", request.user.pk)
        return initial

    @admin.display(description="Followers", ordering="followers")
    def followers_display(self, obj):
        if obj.followers is None:
            return "—"
        return f"{obj.followers:,}"

    @admin.display(description="Niche")
    def niche_list(self, obj):
        if not obj.niche:
            return "—"
        return ", ".join(obj.niche)

    @admin.display(description="Profile")
    def profile(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Open</a>',
            obj.profile_link,
        )
