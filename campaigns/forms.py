from django import forms

from creators.choices import Platform
from creators.forms import CommaListForm, use_checkboxes

from .models import Campaign, CampaignCreator, Deliverable


class CampaignAdminForm(CommaListForm):
    comma_list_fields = ("country_market", "niche_vertical", "sub_niche")

    class Meta:
        model = Campaign
        fields = "__all__"
        widgets = {"remarks_brief": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_checkboxes(self, "platforms", Platform.choices)


class CampaignCreatorAdminForm(forms.ModelForm):
    class Meta:
        model = CampaignCreator
        fields = "__all__"
        widgets = {
            "fit_notes": forms.Textarea(attrs={"rows": 3}),
            "deliverables_notes": forms.Textarea(attrs={"rows": 3}),
            "client_remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_checkboxes(self, "deliverables", Deliverable.choices)
