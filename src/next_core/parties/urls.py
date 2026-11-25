from django.urls import path

from next_core.parties import api

urlpatterns = [
    path("parties", api.PartyListView.as_view(), name="parties"),
    path("parties/<uuid:party_id>", api.PartyDetailView.as_view(), name="party"),
    path("parties/<uuid:party_id>/status", api.PartyStatusView.as_view(), name="party-status"),
    path("parties/<uuid:party_id>/kyc", api.PartyKycView.as_view(), name="party-kyc"),
]
