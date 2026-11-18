from django.contrib import admin

from campaigns.admin import CreatorDealInline
from creators.models import Creator

from .forms import CreatorAdminForm


@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    form = CreatorAdminForm
    empty_value_display = "—"
    show_facets = admin.ShowFacets.ALWAYS
    list_display = (
        "influencer_name",
        "platform",
        "country",
        "followers_display",
        "engagement",
        "rate_card",
        "is_profile_checked",
        "added_by",
    )
    list_display_links = ("influencer_name",)
    list_filter = ("platform", "tier", "is_profile_checked", "rate_currency", "country")
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

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("added_by", request.user.pk)
        return initial

    @admin.display(description="Followers", ordering="followers")
    def followers_display(self, obj):
        if obj.followers is None:
            return "—"
        return f"{obj.followers:,}"

    @admin.display(description="Engagement", ordering="engagement_rate")
    def engagement(self, obj):
        if obj.engagement_rate is None:
            return "—"
        return f"{obj.engagement_rate}%"

    @admin.display(description="Rate card", ordering="rate_card_price")
    def rate_card(self, obj):
        if obj.rate_card_price is None:
            return "—"
        return f"{obj.rate_card_price:,.2f} {obj.rate_currency}"
