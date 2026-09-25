"""Extensions drf-spectacular : schéma d'authentification par session et champs de nomenclature."""

from drf_spectacular.authentication import SessionScheme
from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes


class Pme360SessionScheme(SessionScheme):
    target_class = "pme360.core.authentication.SessionAuthentication"
    name = "sessionAuth"


class RefFieldExtension(OpenApiSerializerFieldExtension):
    """``RefField`` : identifiant (UUID) en écriture, objet ``RefItem`` ``{id, code, name}`` en lecture."""

    target_class = "pme360.pmes.serializers.RefField"

    def map_serializer_field(self, auto_schema, direction):
        if direction == "request":
            return build_basic_type(OpenApiTypes.UUID)
        from pme360.pmes.serializers import RefItemSerializer

        return auto_schema.resolve_serializer(RefItemSerializer, direction).ref
