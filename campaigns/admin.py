from django.contrib import admin
from django.db.models import Count
from django.forms.models import BaseInlineFormSet

from .forms import (
    CampaignAdminForm,
    CampaignCreatorAdminForm,
    ClientShareItemAdminForm,
    OutreachAdminForm,
)
from .models import (
    Campaign,
    CampaignCreator,
    CampaignCreatorDeliverable,
    ClientShare,
    ClientShareItem,
    Outreach,
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


class DeliverableLineInline(admin.TabularInline):
    model = CampaignCreatorDeliverable
    extra = 0
    autocomplete_fields = ("deliverable_type",)
    fields = ("deliverable_type", "name")
    verbose_name_plural = "deliverables"


class OutreachInline(admin.TabularInline):
    model = Outreach
    form = OutreachAdminForm
    extra = 0
    show_change_link = True
    fields = (
        "channel",
        "direction",
        "outreach_status",
        "message_summary",
        "quoted_price",
        "offered_price",
        "currency",
        "next_followup_date",
        "sent_by",
        "sent_at",
    )
    ordering = ("-sent_at", "-created_at")
    verbose_name_plural = "outreach"


class ClientShareInline(admin.TabularInline):
    model = ClientShare
    extra = 0
    show_change_link = True
    fields = ("title", "status", "sent_to_email", "sent_by", "sent_at", "expires_at")
    ordering = ("-sent_at", "title")
    verbose_name_plural = "client links"


class ClientShareItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        campaign_id = self.instance.campaign_id
        if not campaign_id:
            return
        seen = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            deal = form.cleaned_data.get("campaign_creator")
            if deal is None:
                continue
            if deal.pk in seen:
                form.add_error("campaign_creator", "This creator is already on that link.")
            seen.add(deal.pk)
            if deal.campaign_id != campaign_id:
                form.add_error("campaign_creator", "This creator is not on the campaign for this link.")


class ClientShareItemInline(admin.TabularInline):
    model = ClientShareItem
    form = ClientShareItemAdminForm
    formset = ClientShareItemFormSet
    extra = 0
    autocomplete_fields = ("campaign_creator",)
    fields = (
        "campaign_creator",
        "client_price",
        "client_currency",
        "decision",
        "client_remarks",
        "decided_at",
    )
    readonly_fields = ("decided_at",)
    verbose_name_plural = "creators on this link"


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    form = CampaignAdminForm
    empty_value_display = "—"
    save_on_top = True
    list_select_related = ("campaign_owner",)
    inlines = (CampaignDealInline, ClientShareInline)
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
    filter_horizontal = ("country_market",)
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
        return obj.get_status_display()


@admin.register(CampaignCreator)
class CampaignCreatorAdmin(admin.ModelAdmin):
    form = CampaignCreatorAdminForm
    empty_value_display = "—"
    save_on_top = True
    autocomplete_fields = ("campaign", "creator")
    list_display = (
        "creator",
        "campaign_name",
        "stage_badge",
        "creator_budget",
        "deliverable_list",
        "email_outreached",
        "sent_date",
        "date_confirmed",
        "assigned_to",
    )
    list_display_links = ("creator",)
    list_filter = ("stage", "campaign", "creator__platform", "assigned_to")
    list_select_related = ("campaign", "creator")
    search_fields = (
        "creator__influencer_name",
        "creator__profile_link",
        "campaign__client_name",
        "assigned_to",
        "email_outreached",
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
                    "deliverables_notes",
                    "assigned_to",
                    "email_outreached",
                    "sent_date",
                    "fx_lock_date",
                ),
            },
        ),
        (
            "What we pay",
            {
                "description": "Hidden from the client. A price in EUR is copied. Any other currency needs an EUR amount.",
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
                "description": "Copied from the latest accept or reject on a client link.",
                "fields": ("client_status", "client_remarks"),
            },
        ),
        ("Record", {"fields": ("added_by", "id", "created_at", "updated_at")}),
    )

    inlines = (DeliverableLineInline, OutreachInline)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("deliverable_lines")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        username = request.user.get_username()
        initial.setdefault("assigned_to", username)
        initial.setdefault("added_by", username)
        return initial

    @admin.display(description="Campaign", ordering="campaign__client_name")
    def campaign_name(self, obj):
        return obj.campaign.client_name

    @admin.display(description="Stage", ordering="stage")
    def stage_badge(self, obj):
        return obj.get_stage_display()

    @admin.display(description="Deliverables")
    def deliverable_list(self, obj):
        names = [line.name for line in obj.deliverable_lines.all()]
        if not names:
            return "—"
        return ", ".join(names)

    @admin.display(description="Creator price", ordering="creator_price")
    def creator_budget(self, obj):
        return money(obj.creator_price, obj.creator_currency)


@admin.register(Outreach)
class OutreachAdmin(admin.ModelAdmin):
    form = OutreachAdminForm
    empty_value_display = "—"
    save_on_top = True
    autocomplete_fields = ("campaign_creator",)
    list_select_related = ("campaign_creator__campaign", "campaign_creator__creator")
    list_display = (
        "campaign_creator",
        "status_badge",
        "channel",
        "direction",
        "summary",
        "ask",
        "offer",
        "next_followup_date",
        "sent_by",
        "sent_at",
    )
    list_display_links = ("campaign_creator",)
    list_filter = (
        "outreach_status",
        "channel",
        "direction",
        "campaign_creator__campaign",
        "next_followup_date",
    )
    search_fields = (
        "message_summary",
        "contact_email",
        "sent_by",
        "campaign_creator__creator__influencer_name",
        "campaign_creator__campaign__client_name",
    )
    date_hierarchy = "next_followup_date"
    readonly_fields = ("id", "created_at")
    fieldsets = (
        (
            "Message",
            {
                "description": "One row per message, quote, or follow-up on a deal. A new price is a new row.",
                "fields": (
                    "campaign_creator",
                    "channel",
                    "direction",
                    "outreach_status",
                    "message_summary",
                    "contact_email",
                    "sent_by",
                    "sent_at",
                    "next_followup_date",
                ),
            },
        ),
        (
            "Quote",
            {
                "description": "The creator's ask and our offer on this message. The client never sees these.",
                "fields": ("quoted_price", "offered_price", "currency"),
            },
        ),
        ("Record", {"fields": ("id", "created_at")}),
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("sent_by", request.user.get_username())
        return initial

    @admin.display(description="Status", ordering="outreach_status")
    def status_badge(self, obj):
        return obj.get_outreach_status_display()

    @admin.display(description="Summary")
    def summary(self, obj):
        text = obj.message_summary
        if len(text) <= 80:
            return text or "—"
        return f"{text[:79]}…"

    @admin.display(description="Ask", ordering="quoted_price")
    def ask(self, obj):
        return money(obj.quoted_price, obj.currency)

    @admin.display(description="Offer", ordering="offered_price")
    def offer(self, obj):
        return money(obj.offered_price, obj.currency)


@admin.register(ClientShare)
class ClientShareAdmin(admin.ModelAdmin):
    empty_value_display = "—"
    save_on_top = True
    autocomplete_fields = ("campaign",)
    list_select_related = ("campaign",)
    inlines = (ClientShareItemInline,)
    list_display = (
        "title",
        "campaign",
        "status_badge",
        "sent_to_email",
        "sent_by",
        "sent_at",
        "expires_at",
        "creator_count",
    )
    list_display_links = ("title",)
    list_filter = ("status", "campaign")
    search_fields = (
        "title",
        "share_token",
        "sent_to_email",
        "sent_by",
        "campaign__client_name",
    )
    date_hierarchy = "sent_at"
    readonly_fields = ("share_token", "submitted_at")
    radio_fields = {"status": admin.HORIZONTAL}
    fieldsets = (
        (
            "Link",
            {
                "description": "One secure link for a campaign. The client sees only the price on each creator.",
                "fields": ("campaign", "title", "status", "share_token"),
            },
        ),
        (
            "Delivery",
            {
                "fields": (
                    "sent_to_email",
                    "sent_by",
                    "sent_at",
                    "expires_at",
                    "submitted_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_creator_count=Count("items"))

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("sent_by", request.user.get_username())
        return initial

    @admin.display(description="Creators", ordering="_creator_count")
    def creator_count(self, obj):
        return obj._creator_count

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return obj.get_status_display()
