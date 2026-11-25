from django.urls import path

from next_core.transactions import api

transactions = [
    path("transactions", api.TransactionListView.as_view(), name="transactions"),
    path("transactions/deposits", api.DepositView.as_view(), name="deposits"),
    path("transactions/withdrawals", api.WithdrawalView.as_view(), name="withdrawals"),
    path("transactions/transfers", api.TransferView.as_view(), name="transfers"),
    path("transactions/simulate", api.SimulateView.as_view(), name="transactions-simulate"),
    path("transactions/<uuid:txn_id>", api.TransactionDetailView.as_view(), name="transaction"),
    path(
        "transactions/<uuid:txn_id>/transitions",
        api.TransactionTransitionsView.as_view(),
        name="transaction-transitions",
    ),
    path(
        "transactions/<uuid:txn_id>/reversal",
        api.ReversalView.as_view(),
        name="transaction-reversal",
    ),
]

holds = [
    path("holds", api.HoldCreateView.as_view(), name="holds"),
    path("holds/<uuid:hold_id>", api.HoldDetailView.as_view(), name="hold"),
    path("holds/<uuid:hold_id>/capture", api.HoldCaptureView.as_view(), name="hold-capture"),
    path("holds/<uuid:hold_id>/release", api.HoldReleaseView.as_view(), name="hold-release"),
]

loans = [
    path(
        "loans/<uuid:account_id>/disbursements",
        api.DisbursementView.as_view(),
        name="loan-disbursements",
    ),
    path("loans/<uuid:account_id>/repayments", api.RepaymentView.as_view(), name="loan-repayments"),
]

operations = [
    path("operations/eod", api.EodView.as_view(), name="eod"),
]
