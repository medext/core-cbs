from django.urls import path

from next_core.ledger import api

urlpatterns = [
    path("ledger/gl-accounts", api.GLAccountsView.as_view(), name="gl-accounts"),
    path("ledger/trial-balance", api.TrialBalanceView.as_view(), name="trial-balance"),
    path("ledger/entries/<uuid:entry_id>", api.EntryDetailView.as_view(), name="journal-entry"),
]

operations = [
    path("operations/integrity-runs", api.IntegrityRunView.as_view(), name="integrity-runs"),
    path("operations/eod", api.EodView.as_view(), name="eod"),
]
