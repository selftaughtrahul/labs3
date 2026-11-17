from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .forms import CampaignAdminForm, CampaignCreatorAdminForm
from .models import Campaign, CampaignCreator


def badge(value, label):
    return format_html(
        '<span class="ccp-status ccp-status-{}">{}</span>',
        value,
        label,
    )


def money(amount, currency):
    if amount is None:
        return "—"
    text = f"{amount:,.2f}"
    return f"{text} {currency}".rstrip()


class DealInline(admin.TabularInline):
    model = CampaignCreator
    extra = 0
    show_change_link = True
    readonly_fields = ("margin_eur",)
    ordering = ("-updated_at",)


class CampaignDealInline(DealInline):
    autocomplete_fields = ("creator",)
    fields = (
        "creator",
        "stage",
        "creator_price",
        "creator_currency",
        "client_price",
        "client_currency",
        "margin_eur",
    )
    verbose_name_plural = "creators on this campaign"


class CreatorDealInline(DealInline):
    autocomplete_fields = ("campaign",)
    fields = (
        "campaign",
        "stage",
        "creator_price",
        "creator_currency",
        "client_price",
        "client_currency",
        "margin_eur",
    )
    verbose_name_plural = "campaigns"


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    form = CampaignAdminForm
    empty_value_display = "—"
    show_facets = admin.ShowFacets.ALWAYS
    save_on_top = True
    inlines = (CampaignDealInline,)
    list_display = (
        "client_name",
        "status_badge",
        "campaign_owner",
        "creators_needed",
        "deal_count",
        "deadline_to_scout",
        "updated_at",
    )
    list_display_links = ("client_name",)
    list_filter = ("status", "campaign_owner", "deadline_to_scout")
    search_fields = (
        "client_name",
        "campaign_owner__username",
        "created_by__username",
        "remarks_brief",
    )
    date_hierarchy = "deadline_to_scout"
    radio_fields = {"status": admin.HORIZONTAL}
    readonly_fields = ("id", "created_by", "created_at", "updated_at")
    fieldsets = (
        (
            "Brief",
            {
                "description": "One row per client brief. It stays Draft while the brief is being filled in.",
                "fields": (
                    "client_name",
                    "status",
                    "campaign_owner",
                    "deadline_to_scout",
                    "creators_needed",
                    "remarks_brief",
                ),
            },
        ),
        (
            "Targeting",
            {
                "fields": (
                    "platforms",
                    "country_market",
                    "niche_vertical",
                    "sub_niche",
                    "content_type",
                    "content_format",
                ),
            },
        ),
        (
            "Limits",
            {
                "description": "A scout uses these to decide whether a checked profile fits.",
                "fields": (
                    "min_followers",
                    "max_followers",
                    "min_avg_views",
                    "min_engagement_rate",
                ),
            },
        ),
        ("Record", {"fields": ("id", "created_by", "created_at", "updated_at")}),
    )

    class Media:
        css = {"all": ("campaigns/admin.css",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_deal_count=Count("deals"))

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("campaign_owner", request.user.pk)
        return initial

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Creators", ordering="_deal_count")
    def deal_count(self, obj):
        return obj._deal_count

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return badge(obj.status, obj.get_status_display())


@admin.register(CampaignCreator)
class CampaignCreatorAdmin(admin.ModelAdmin):
    form = CampaignCreatorAdminForm
    empty_value_display = "—"
    show_facets = admin.ShowFacets.ALWAYS
    save_on_top = True
    autocomplete_fields = ("campaign", "creator")
    list_display = (
        "creator",
        "campaign",
        "stage_badge",
        "creator_budget",
        "client_budget",
        "margin_eur",
        "client_status",
        "assigned_to",
    )
    list_display_links = ("creator",)
    list_filter = ("stage", "client_status", "campaign")
    list_select_related = ("campaign", "creator")
    search_fields = (
        "creator__influencer_name",
        "creator__profile_link",
        "campaign__client_name",
        "assigned_to",
        "fit_notes",
    )
    date_hierarchy = "date_confirmed"
    readonly_fields = ("id", "margin_eur", "created_at", "updated_at")
    fieldsets = (
        (
            "Deal",
            {
                "description": "One creator on one campaign. The same pair cannot be added twice.",
                "fields": (
                    "campaign",
                    "creator",
                    "stage",
                    "fit_notes",
                    "deliverables",
                    "deliverables_notes",
                    "assigned_to",
                ),
            },
        ),
        (
            "What we pay",
            {
                "description": "Hidden from the client. A price in EUR is copied. A price in USD needs an EUR amount.",
                "fields": (
                    "creator_price",
                    "creator_currency",
                    "creator_price_eur",
                    "date_confirmed",
                ),
            },
        ),
        (
            "What the client pays",
            {
                "fields": (
                    "client_price",
                    "client_currency",
                    "client_price_eur",
                    "margin_eur",
                ),
            },
        ),
        (
            "Client answer",
            {
                "description": "Copied from the review link once that exists. Leave blank until then.",
                "fields": ("client_status", "client_remarks"),
            },
        ),
        ("Record", {"fields": ("added_by", "id", "created_at", "updated_at")}),
    )

    class Media:
        css = {"all": ("campaigns/admin.css",)}

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        username = request.user.get_username()
        initial.setdefault("assigned_to", username)
        initial.setdefault("added_by", username)
        return initial

    @admin.display(description="Stage", ordering="stage")
    def stage_badge(self, obj):
        return badge(obj.stage, obj.get_stage_display())

    @admin.display(description="Creator price", ordering="creator_price")
    def creator_budget(self, obj):
        return money(obj.creator_price, obj.creator_currency)

    @admin.display(description="Client price", ordering="client_price")
    def client_budget(self, obj):
        return money(obj.client_price, obj.client_currency)
