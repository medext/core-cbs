"""Product engine API — /api/v1/products (catalog, versions, maker-checker, simulation)."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.iam.permissions import PRODUCTS_APPROVE, PRODUCTS_READ, PRODUCTS_WRITE
from next_core.iam.views import DataPlaneView
from next_core.platform.api import (
    OBJ,
    OBJ_LIST,
    BoundedPageNumberPagination,
    MoneyInputSerializer,
    StrictSerializer,
    actor_from,
)
from next_core.platform.errors import ValidationFailedError
from next_core.platform.money import AmountFormatError, Money
from next_core.pricing.fees import compute_fees
from next_core.products import application as svc
from next_core.products.catalog import SEED_PRODUCTS
from next_core.products.definition import (
    Operation,
    parse_definition,
    validate_overrides,
)
from next_core.products.expressions import ExpressionError
from next_core.products.models import Product, ProductVersion

TAG = ["Products"]

_EXAMPLE_DEF = SEED_PRODUCTS[0][3]


class ProductCreateSerializer(StrictSerializer):
    code = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_]{1,39}$")
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, default="")
    definition = serializers.JSONField()


class DefinitionSerializer(StrictSerializer):
    definition = serializers.JSONField()


class DecisionSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500, required=False, default="")


class VersionSerializer(serializers.ModelSerializer[ProductVersion]):
    product_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ProductVersion
        fields = (
            "id",
            "product_id",
            "version",
            "status",
            "definition",
            "definition_hash",
            "created_by",
            "submitted_by",
            "approved_by",
            "approved_at",
            "effective_from",
            "decision_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer[Product]):
    versions = serializers.SerializerMethodField()
    active_version = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "code",
            "name",
            "description",
            "category",
            "active_version",
            "versions",
            "created_at",
        )
        read_only_fields = fields

    def get_versions(self, obj: Product) -> list[dict[str, Any]]:
        return [
            {"version": v.version, "status": v.status, "effective_from": v.effective_from}
            for v in obj.versions.order_by("version")
        ]

    def get_active_version(self, obj: Product) -> int | None:
        v = obj.versions.filter(status="ACTIVE").first()
        return v.version if v else None


class SimulationSerializer(StrictSerializer):
    operation = serializers.ChoiceField(choices=[o.value for o in Operation])
    amount = serializers.CharField(max_length=24)
    currency = serializers.CharField(max_length=3)
    channel = serializers.CharField(max_length=20, required=False, default="API")
    kyc_level = serializers.IntegerField(min_value=0, max_value=3, required=False, default=1)
    book_balance = serializers.CharField(max_length=24, required=False, default="0")
    account_age_days = serializers.IntegerField(min_value=0, required=False, default=0)
    days_to_maturity = serializers.IntegerField(required=False, default=-1)
    parameter_overrides = serializers.JSONField(required=False, default=dict)
    version = serializers.IntegerField(min_value=1, required=False)


class ProductListView(DataPlaneView):
    method_permissions = {"GET": PRODUCTS_READ, "POST": PRODUCTS_WRITE}

    @extend_schema(tags=TAG, summary="List products", responses=ProductSerializer(many=True))
    def get(self, request: Request) -> Response:
        qs = Product.objects.all().order_by("code")
        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category[:20])
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(ProductSerializer(page, many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Create a product (version 1 as DRAFT)",
        request=ProductCreateSerializer,
        responses={201: VersionSerializer},
        examples=[
            OpenApiExample(
                "Current account",
                value={"code": "CURRENT", "name": "Current account", "definition": _EXAMPLE_DEF},
                request_only=True,
            )
        ],
    )
    def post(self, request: Request) -> Response:
        ser = ProductCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        version = svc.create_product(
            code=v["code"],
            name=v["name"],
            description=v["description"],
            definition=v["definition"],
            actor=actor_from(request),
        )
        return Response(VersionSerializer(version).data, status=201)


class ProductDetailView(DataPlaneView):
    method_permissions = {"GET": PRODUCTS_READ}

    @extend_schema(tags=TAG, summary="Get a product", responses=ProductSerializer)
    def get(self, request: Request, product_id: UUID) -> Response:
        return Response(ProductSerializer(svc.get_product(product_id)).data)


class VersionListView(DataPlaneView):
    method_permissions = {"GET": PRODUCTS_READ, "POST": PRODUCTS_WRITE}

    @extend_schema(tags=TAG, summary="List versions", responses=VersionSerializer(many=True))
    def get(self, request: Request, product_id: UUID) -> Response:
        svc.get_product(product_id)
        qs = ProductVersion.objects.filter(product_id=product_id).order_by("version")
        return Response(VersionSerializer(qs, many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Draft a new version",
        request=DefinitionSerializer,
        responses={201: VersionSerializer},
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        ser = DefinitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        version = svc.new_version(product_id, ser.validated_data["definition"], actor_from(request))
        return Response(VersionSerializer(version).data, status=201)


class VersionDetailView(DataPlaneView):
    method_permissions = {"GET": PRODUCTS_READ, "PUT": PRODUCTS_WRITE}

    @extend_schema(tags=TAG, summary="Get a version", responses=VersionSerializer)
    def get(self, request: Request, product_id: UUID, version: int) -> Response:
        return Response(VersionSerializer(svc.get_version(product_id, version)).data)

    @extend_schema(
        tags=TAG,
        summary="Replace a DRAFT definition",
        request=DefinitionSerializer,
        responses=VersionSerializer,
    )
    def put(self, request: Request, product_id: UUID, version: int) -> Response:
        ser = DefinitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = svc.update_draft(
            product_id, version, ser.validated_data["definition"], actor_from(request)
        )
        return Response(VersionSerializer(v).data)


class _DecisionView(DataPlaneView):
    action_name = ""

    def _decide(self, request: Request, product_id: UUID, version: int) -> Response:
        ser = DecisionSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        actor, reason = actor_from(request), ser.validated_data["reason"]
        if self.action_name == "submit":
            v = svc.submit(product_id, version, actor)
        elif self.action_name == "approve":
            v = svc.approve(product_id, version, actor, reason)
        else:
            if not reason:
                raise ValidationFailedError("A rejection requires a reason.")
            v = svc.reject(product_id, version, actor, reason)
        return Response(VersionSerializer(v).data)


class SubmitView(_DecisionView):
    method_permissions = {"POST": PRODUCTS_WRITE}
    action_name = "submit"

    @extend_schema(
        tags=TAG,
        summary="Submit a DRAFT for approval (maker)",
        request=DecisionSerializer,
        responses=VersionSerializer,
    )
    def post(self, request: Request, product_id: UUID, version: int) -> Response:
        return self._decide(request, product_id, version)


class ApproveView(_DecisionView):
    method_permissions = {"POST": PRODUCTS_APPROVE}
    action_name = "approve"

    @extend_schema(
        tags=TAG,
        summary="Approve & activate (checker ≠ maker)",
        request=DecisionSerializer,
        responses=VersionSerializer,
    )
    def post(self, request: Request, product_id: UUID, version: int) -> Response:
        return self._decide(request, product_id, version)


class RejectView(_DecisionView):
    method_permissions = {"POST": PRODUCTS_APPROVE}
    action_name = "reject"

    @extend_schema(
        tags=TAG,
        summary="Reject a pending version (checker)",
        request=DecisionSerializer,
        responses=VersionSerializer,
    )
    def post(self, request: Request, product_id: UUID, version: int) -> Response:
        return self._decide(request, product_id, version)


class RetireView(DataPlaneView):
    method_permissions = {"POST": PRODUCTS_APPROVE}

    @extend_schema(
        tags=TAG,
        summary="Retire the product (no new accounts)",
        request=None,
        responses=VersionSerializer,
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        return Response(VersionSerializer(svc.retire(product_id, actor_from(request))).data)


class ValidateDefinitionView(DataPlaneView):
    method_permissions = {"POST": PRODUCTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Validate a definition document (no side effects)",
        request=DefinitionSerializer,
        responses={200: OBJ},
    )
    def post(self, request: Request) -> Response:
        ser = DefinitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        defn = parse_definition(ser.validated_data["definition"])
        return Response(
            {
                "valid": True,
                "category": defn.category.value,
                "currencies": list(defn.currencies),
                "fees": [f.code for f in defn.fees],
                "limits": [lim.code for lim in defn.limits],
                "operation_rules": [r.code for r in defn.operation_rules],
            }
        )


class TemplatesView(DataPlaneView):
    method_permissions = {"GET": PRODUCTS_READ}

    @extend_schema(tags=TAG, summary="Seed product templates", responses={200: OBJ_LIST})
    def get(self, request: Request) -> Response:
        return Response(
            [
                {"code": code, "name": name, "description": desc, "definition": definition}
                for code, name, desc, definition in SEED_PRODUCTS
            ]
        )


class SimulateView(DataPlaneView):
    method_permissions = {"POST": PRODUCTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Simulate fees and rules for an operation (pure; no account needed)",
        request=SimulationSerializer,
        responses={200: OBJ},
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        ser = SimulationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if "version" in v:
            resolved = svc.resolve_version(svc.get_version(product_id, v["version"]).id)
        else:
            resolved = svc.active_version(product_id)
        defn = resolved.definition
        money_ser = MoneyInputSerializer(data={"amount": v["amount"], "currency": v["currency"]})
        money_ser.is_valid(raise_exception=True)
        amount = money_ser.validated_data["money"]
        if amount.currency not in defn.currencies:
            raise ValidationFailedError(f"Product does not support {amount.currency}.")
        overrides = validate_overrides(defn, v["parameter_overrides"], amount.currency)
        try:
            book = Money.from_wire(v["book_balance"], amount.currency).to_major_decimal()
        except (AmountFormatError, ValueError) as exc:
            raise ValidationFailedError(f"book_balance: {exc}") from exc
        op = Operation(v["operation"])
        env: dict[str, Any] = {
            "amount": amount.to_major_decimal(),
            "currency": amount.currency,
            "operation": op.value,
            "channel": v["channel"],
            "kyc_level": Decimal(v["kyc_level"]),
            "account_age_days": Decimal(v["account_age_days"]),
            "days_to_maturity": Decimal(v["days_to_maturity"]),
            "book_balance": book,
            "available_balance": book,
        }
        env.update(defn.expression_env_params(amount.currency, overrides))
        rules = []
        for rule in defn.operation_rules:
            if op in rule.operations:
                try:
                    ok = rule.condition.evaluate_bool(env)
                except ExpressionError as exc:
                    ok, rule_msg = False, str(exc)
                else:
                    rule_msg = "" if ok else rule.message
                rules.append({"code": rule.code, "passed": ok, "message": rule_msg})
        fees = compute_fees(defn.fees, op, amount, env)
        return Response(
            {
                "product": resolved.product_code,
                "version": resolved.version,
                "operation": op.value,
                "allowed": op in defn.allowed_operations and all(r["passed"] for r in rules),
                "operation_allowed_by_product": op in defn.allowed_operations,
                "rules": rules,
                "fees": [
                    {
                        "code": f.code,
                        "amount": f.net.to_wire(),
                        "tax": f.tax.to_wire(),
                        "total": f.total.to_wire(),
                    }
                    for f in fees
                ],
                "limits": [
                    {
                        "code": lim.code,
                        "window": lim.window.value,
                        "max_amount": (
                            Money(lim.max_amount[amount.currency], amount.currency).to_wire()
                            if lim.max_amount
                            else None
                        ),
                        "max_count": lim.max_count,
                    }
                    for lim in defn.limits
                    if op in lim.operations
                ],
                "currency": amount.currency,
            }
        )
