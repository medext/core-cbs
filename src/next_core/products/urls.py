from django.urls import path

from next_core.products import api

urlpatterns = [
    path("products", api.ProductListView.as_view(), name="products"),
    path("products/templates", api.TemplatesView.as_view(), name="product-templates"),
    path("products/validate", api.ValidateDefinitionView.as_view(), name="product-validate"),
    path("products/<uuid:product_id>", api.ProductDetailView.as_view(), name="product"),
    path("products/<uuid:product_id>/retire", api.RetireView.as_view(), name="product-retire"),
    path(
        "products/<uuid:product_id>/simulate", api.SimulateView.as_view(), name="product-simulate"
    ),
    path(
        "products/<uuid:product_id>/versions",
        api.VersionListView.as_view(),
        name="product-versions",
    ),
    path(
        "products/<uuid:product_id>/versions/<int:version>",
        api.VersionDetailView.as_view(),
        name="product-version",
    ),
    path(
        "products/<uuid:product_id>/versions/<int:version>/submit",
        api.SubmitView.as_view(),
        name="product-version-submit",
    ),
    path(
        "products/<uuid:product_id>/versions/<int:version>/approve",
        api.ApproveView.as_view(),
        name="product-version-approve",
    ),
    path(
        "products/<uuid:product_id>/versions/<int:version>/reject",
        api.RejectView.as_view(),
        name="product-version-reject",
    ),
]
