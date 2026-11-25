from django.urls import include, path
from django.views.decorators.cache import cache_page
from drf_spectacular.views import SpectacularJSONAPIView, SpectacularRedocView

from next_core.ledger.urls import operations as ledger_operations
from next_core.ledger.urls import urlpatterns as ledger
from next_core.transactions.urls import holds, loans, transactions
from next_core.transactions.urls import operations as txn_operations

urlpatterns = [
    path("health/", include("next_core.platform.health.urls")),
    path(
        "api/schema/openapi.json",
        cache_page(3600)(SpectacularJSONAPIView.as_view()),
        name="openapi-schema",
    ),
    path(
        "api/schema/docs", SpectacularRedocView.as_view(url_name="openapi-schema"), name="api-docs"
    ),
    path("api/v1/audit/", include("next_core.audit.urls")),
    path("api/v1/", include("next_core.parties.urls")),
    path("api/v1/", include("next_core.products.urls")),
    path("api/v1/", include("next_core.accounts.urls")),
    path("api/v1/", include(transactions)),
    path("api/v1/", include(holds)),
    path("api/v1/", include(loans)),
    path("api/v1/", include(ledger)),
    path("api/v1/", include(ledger_operations)),
    path("api/v1/", include(txn_operations)),
]
