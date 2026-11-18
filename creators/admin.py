from django.contrib import admin
from django.utils.html import format_html

from campaigns.admin import CreatorDealInline
from creators.models import Creator

from .forms import CreatorAdminForm


@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    form = CreatorAdminForm
    empty_value_display = "—"
    list_select_related = ("added_by",)
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
        "country",
        "added_by__username",
    )
    date_hierarchy = "added_at"
    radio_fields = {"platform": admin.HORIZONTAL}
    inlines = (CreatorDealInline,)
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
            "Rate card",
            {
                "description": "Reference rate only. What we pay on a campaign is stored on the deal.",
                "fields": ("rate_card_price", "rate_currency"),
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
