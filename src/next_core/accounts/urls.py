from django.urls import path

from next_core.accounts import api

urlpatterns = [
    path("accounts", api.AccountListView.as_view(), name="accounts"),
    path("accounts/<uuid:account_id>", api.AccountDetailView.as_view(), name="account"),
    path(
        "accounts/<uuid:account_id>/balances",
        api.AccountBalancesView.as_view(),
        name="account-balances",
    ),
    path(
        "accounts/<uuid:account_id>/statement",
        api.AccountStatementView.as_view(),
        name="account-statement",
    ),
    path(
        "accounts/<uuid:account_id>/limits", api.AccountLimitsView.as_view(), name="account-limits"
    ),
    path(
        "accounts/<uuid:account_id>/status", api.AccountStatusView.as_view(), name="account-status"
    ),
    path(
        "accounts/<uuid:account_id>/blocks", api.AccountBlocksView.as_view(), name="account-blocks"
    ),
    path(
        "accounts/<uuid:account_id>/history",
        api.AccountHistoryView.as_view(),
        name="account-history",
    ),
]
