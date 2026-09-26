"""Marque blanche (V1) : identité par organisation, page de connexion, démo complète au nom d'un prospect."""

import base64
import io
from io import StringIO

import pytest
from django.core.management import call_command
from PIL import Image
from rest_framework.exceptions import ValidationError

from pme360.accounts.models import User
from pme360.audit.models import AuditLog
from pme360.core.tenancy import system_context, tenant_context
from pme360.diagnostic.models import Framework
from pme360.documents.models import DocumentVersion
from pme360.documents.storage import get_storage
from pme360.notifications import catalog
from pme360.organizations import branding
from pme360.organizations.models import Organization, OrganizationKey
from pme360.pmes.models import Pme

pytestmark = pytest.mark.django_db


def _png(size=(32, 32)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, (0, 85, 164)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_brand_defaults_and_validation():
    assert branding.contrast_with_white("#0F6B4F") > 4.5
    assert branding.validate({"primary_color": "#0055a4"})["primary_color"] == "#0055A4"
    with pytest.raises(ValidationError) as light:
        branding.validate({"primary_color": "#FFE066"})
    assert "trop claire" in str(light.value.detail)
    with pytest.raises(ValidationError):
        branding.validate({"primary_color": "bleu"})
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='x'/>").decode()
    with pytest.raises(ValidationError) as bad_logo:
        branding.validate({"logo": svg})
    assert "SVG" in str(bad_logo.value.detail)
    assert branding.validate({"logo": _png()})["logo"].startswith("data:image/png;base64,")
    with pytest.raises(ValidationError):
        branding.validate({"logo": _png((900, 900)).replace("iVBOR", "AAAA", 1)})  # image corrompue


def test_admin_sets_identity_used_by_me_emails_and_login_page(org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    saved = admin.put(
        "/api/v1/organization/branding",
        {
            "product_name": "Atlantique PME",
            "short_name": "Banque Atlantique",
            "primary_color": "#0055A4",
            "logo": _png(),
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    me = admin.get("/api/v1/me").json()
    assert me["organization"]["brand"]["short_name"] == "Banque Atlantique"
    assert me["organization"]["brand"]["product_name"] == "Atlantique PME"
    with tenant_context(org.id):
        entry = AuditLog.objects.get(action="organization.branding_updated")
        assert entry.after["logo"] == "(image)"  # l'image n'est pas recopiée dans le journal
        assert catalog.email_text("Aya", "Bonjour").endswith("L'équipe Banque Atlantique")

    public = admin.get("/api/v1/public/brand", {"org": org.slug}).json()
    assert public["short_name"] == "Banque Atlantique" and public["logo"].startswith("data:image/png")
    neutral = admin.get("/api/v1/public/brand", {"org": "inconnue"}).json()
    assert neutral["product_name"] == "PME360" and neutral["short_name"] == ""
    with system_context():
        Organization.objects.filter(pk=org.pk).update(status=Organization.Status.SUSPENDUE)
    assert admin.get("/api/v1/public/brand", {"org": org.slug}).json()["short_name"] == ""

    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.put("/api/v1/organization/branding", {"short_name": "X"}, format="json").status_code == 403


def test_new_organizations_get_a_neutral_framework(make_org):
    organization = make_org("Incubateur Test")
    from pme360.diagnostic.referential import install_gude360

    with tenant_context(organization.id):
        version = install_gude360(organization)
        framework = Framework.objects.get(pk=version.framework_id)
    assert (framework.code, framework.name) == ("D360", "Diagnostic 360°")


def test_prospect_demo_is_complete_isolated_and_closable(org):
    out = StringIO()
    call_command("create_demo_org", "--nom", "Banque Atlantique", "--couleur", "#0055A4", stdout=out)
    assert "connexion?org=banque-atlantique" in out.getvalue()
    with system_context():
        demo_org = Organization.objects.get(slug="banque-atlantique")
    assert demo_org.branding["short_name"] == "Banque Atlantique"
    with tenant_context(demo_org.id):
        pmes = Pme.objects.count()
        framework = Framework.objects.get()
        texts = [demo_org.name, framework.name, framework.code, *Pme.objects.values_list("legal_name", flat=True)]
        files = list(DocumentVersion.objects.values_list("storage_key", flat=True))
    assert pmes == 6 and files
    assert not any("GUDE" in text.upper() for text in texts)
    accounts = list(User.objects.filter(email__endswith=".banque-atlantique@demo.test").values_list("email", flat=True))
    assert len(accounts) == 8 and not any("gude" in email for email in accounts)

    # Relancer la commande ne duplique rien.
    call_command("create_demo_org", "--nom", "Banque Atlantique", "--couleur", "#0055A4", stdout=StringIO())
    with tenant_context(demo_org.id):
        assert Pme.objects.count() == 6

    # Aucune donnée de la démo n'est visible depuis une autre organisation.
    with tenant_context(org.id):
        assert not Pme.objects.filter(organization=demo_org).exists()

    call_command("close_demo_org", "banque-atlantique", stdout=StringIO())
    with system_context():
        demo_org.refresh_from_db()
    assert demo_org.status == Organization.Status.SUSPENDUE
    assert not User.objects.filter(email__in=accounts, is_active=True).exists()
    with system_context():
        assert not OrganizationKey.objects.filter(organization=demo_org).exists()
    storage = get_storage()
    with pytest.raises(FileNotFoundError):
        storage.get_raw(files[0])


def test_demo_commands_refuse_reserved_or_real_organizations(org, make_user):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("create_demo_org", "--nom", "x", "--slug", "gude-pme-demo", stdout=StringIO())
    make_user(org, "ADMIN_ORG", email="vraie.personne@exemple.ci")
    with pytest.raises(CommandError):
        call_command("close_demo_org", org.slug, stdout=StringIO())
