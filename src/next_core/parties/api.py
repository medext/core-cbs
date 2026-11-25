"""Parties API — /api/v1/parties."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.iam.permissions import PARTIES_READ, PARTIES_WRITE
from next_core.iam.views import DataPlaneView
from next_core.parties import application as svc
from next_core.parties.models import KycStatus, Party, PartyStatus, PartyType, RiskRating
from next_core.platform.api import BoundedCursorPagination, StrictSerializer

TAG = ["Parties"]


class IdentifierSerializer(StrictSerializer):
    scheme = serializers.RegexField(r"^[A-Z][A-Z0-9_]{1,29}$")
    value = serializers.CharField(max_length=64)
    issuing_country = serializers.RegexField(r"^[A-Z]{2}$", required=False, default="")


class PartyWriteSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=PartyType.choices)
    display_name = serializers.CharField(max_length=200)
    given_name = serializers.CharField(max_length=100, required=False, default="")
    family_name = serializers.CharField(max_length=100, required=False, default="")
    legal_name = serializers.CharField(max_length=200, required=False, default="")
    registration_number = serializers.CharField(max_length=64, required=False, default="")
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    nationality = serializers.RegexField(r"^[A-Z]{2}$", required=False, default="")
    residence_country = serializers.RegexField(r"^[A-Z]{2}$", required=False, default="")
    email = serializers.EmailField(required=False, default="")
    phone = serializers.RegexField(r"^\+?[0-9 ]{4,20}$", required=False, default="")
    risk_rating = serializers.ChoiceField(choices=RiskRating.choices, required=False, default="LOW")
    external_ref = serializers.CharField(max_length=64, required=False, default="")
    identifiers = IdentifierSerializer(many=True, required=False, default=list)


class PartyPatchSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=200, required=False)
    given_name = serializers.CharField(max_length=100, required=False)
    family_name = serializers.CharField(max_length=100, required=False)
    legal_name = serializers.CharField(max_length=200, required=False)
    registration_number = serializers.CharField(max_length=64, required=False)
    birth_date = serializers.DateField(required=False, allow_null=True)
    nationality = serializers.RegexField(r"^[A-Z]{2}$", required=False)
    residence_country = serializers.RegexField(r"^[A-Z]{2}$", required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.RegexField(r"^\+?[0-9 ]{4,20}$", required=False)
    risk_rating = serializers.ChoiceField(choices=RiskRating.choices, required=False)
    external_ref = serializers.CharField(max_length=64, required=False)


class PartyStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=PartyStatus.choices)
    reason = serializers.CharField(max_length=300)


class KycSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=KycStatus.choices)
    level = serializers.IntegerField(min_value=0, max_value=3)
    reference = serializers.CharField(max_length=128, required=False, default="")


class PartySerializer(serializers.ModelSerializer[Party]):
    identifiers = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = (
            "id",
            "type",
            "status",
            "external_ref",
            "display_name",
            "given_name",
            "family_name",
            "legal_name",
            "registration_number",
            "birth_date",
            "nationality",
            "residence_country",
            "email",
            "phone",
            "kyc_status",
            "kyc_level",
            "kyc_reference",
            "risk_rating",
            "identifiers",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_identifiers(self, obj: Party) -> list[dict[str, str]]:
        return [
            {"scheme": i.scheme, "value": i.value, "issuing_country": i.issuing_country}
            for i in obj.identifiers.all()
        ]


class PartyListView(DataPlaneView):
    method_permissions = {"GET": PARTIES_READ, "POST": PARTIES_WRITE}
    FILTERS = ("status", "kyc_status", "external_ref", "type")

    @extend_schema(tags=TAG, summary="List parties", responses=PartySerializer(many=True))
    def get(self, request: Request) -> Response:
        qs = Party.objects.all().order_by("-created_at", "-id")
        for name in self.FILTERS:
            value = request.query_params.get(name)
            if value:
                qs = qs.filter(**{name: value[:64]})
        paginator = BoundedCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(PartySerializer(page, many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Create a party",
        request=PartyWriteSerializer,
        responses={201: PartySerializer},
    )
    def post(self, request: Request) -> Response:
        ser = PartyWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data: dict[str, Any] = dict(ser.validated_data)
        identifiers = data.pop("identifiers")
        party = svc.create_party(data, identifiers)
        return Response(PartySerializer(party).data, status=201)


class PartyDetailView(DataPlaneView):
    method_permissions = {"GET": PARTIES_READ, "PATCH": PARTIES_WRITE}

    @extend_schema(tags=TAG, summary="Get a party", responses=PartySerializer)
    def get(self, request: Request, party_id: UUID) -> Response:
        return Response(PartySerializer(svc.get_party(party_id)).data)

    @extend_schema(
        tags=TAG,
        summary="Update party attributes",
        request=PartyPatchSerializer,
        responses=PartySerializer,
    )
    def patch(self, request: Request, party_id: UUID) -> Response:
        ser = PartyPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(PartySerializer(svc.update_party(party_id, dict(ser.validated_data))).data)


class PartyStatusView(DataPlaneView):
    method_permissions = {"POST": PARTIES_WRITE}

    @extend_schema(
        tags=TAG,
        summary="Change party status",
        request=PartyStatusSerializer,
        responses=PartySerializer,
    )
    def post(self, request: Request, party_id: UUID) -> Response:
        ser = PartyStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        party = svc.change_status(
            party_id, ser.validated_data["status"], ser.validated_data["reason"]
        )
        return Response(PartySerializer(party).data)


class PartyKycView(DataPlaneView):
    method_permissions = {"POST": PARTIES_WRITE}

    @extend_schema(
        tags=TAG,
        summary="Record an external KYC outcome",
        request=KycSerializer,
        responses=PartySerializer,
    )
    def post(self, request: Request, party_id: UUID) -> Response:
        ser = KycSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        party = svc.record_kyc(
            party_id, status=v["status"], level=v["level"], reference=v["reference"]
        )
        return Response(PartySerializer(party).data)
