from django import forms

from creators.choices import Platform
from creators.forms import CommaListForm, use_checkboxes

from .models import Campaign, CampaignCreator, ClientShareItem, Outreach


class CampaignAdminForm(CommaListForm):
    comma_list_fields = ("niche_vertical", "sub_niche")

    class Meta:
        model = Campaign
        fields = "__all__"
        widgets = {
            "remarks_brief": forms.Textarea(attrs={"rows": 5}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_checkboxes(self, "platforms", Platform.choices)


class CampaignCreatorAdminForm(CommaListForm):
    comma_list_fields = ()

    class Meta:
        model = CampaignCreator
        fields = "__all__"
        widgets = {
            "fit_notes": forms.Textarea(attrs={"rows": 3}),
            "deliverables_notes": forms.Textarea(attrs={"rows": 3}),
            "client_remarks": forms.Textarea(attrs={"rows": 3}),
        }


class OutreachAdminForm(forms.ModelForm):
    class Meta:
        model = Outreach
        fields = "__all__"
        widgets = {"message_summary": forms.Textarea(attrs={"rows": 3})}


class ClientShareItemAdminForm(forms.ModelForm):
    class Meta:
        model = ClientShareItem
        fields = "__all__"
        widgets = {"client_remarks": forms.Textarea(attrs={"rows": 2})}
