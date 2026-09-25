"""Charge le jeu de démonstration fictif (idempotent). Refusé en production."""

import base64
import hashlib
import zlib
from datetime import date, datetime, time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pme360.accounts.access import build_access
from pme360.accounts.models import Role, User, UserMembership
from pme360.audit import services as audit
from pme360.core.tenancy import system_context, tenant_context
from pme360.diagnostic import services as diagnostic_services
from pme360.diagnostic.models import Answer, Diagnostic, Question
from pme360.diagnostic.referential import install_gude360
from pme360.organizations.models import Cohort, Organization, Programme
from pme360.pmes import services as pme_services
from pme360.pmes.defaults import install_defaults
from pme360.pmes.models import LegalForm, Pme, PmeAssignment, Region, Sector
from seeds import demo, demo_diagnostics


def demo_totp_secret(email: str) -> str:
    """Secret TOTP déterministe des comptes de démonstration (jamais utilisé hors démo)."""
    return base64.b32encode(hashlib.sha256(f"pme360-demo:{email}".encode()).digest()[:20]).decode()


def ensure_not_production() -> None:
    if settings.ENVIRONMENT == "prod":
        raise CommandError("Les données de démonstration sont interdites en production.")


class Command(BaseCommand):
    help = "Charge les données de démonstration fictives (organisations, utilisateurs, 6 PME DEMO-)."

    def handle(self, *args, **options):
        ensure_not_production()
        users = self._users()
        organizations = self._organizations(users["superadmin@demo.test"])
        for slug, organization in organizations.items():
            with tenant_context(organization.id):
                install_defaults(organization)
                install_gude360(organization)
                programme = self._programme(organization) if slug == "gude-pme-demo" else None
                pmes = self._pmes(slug, users, programme)
                self._memberships(slug, users, programme, pmes)
                self._pme_setup(slug, organization, users, programme, pmes)
                self._diagnostics(slug, organization, users, pmes)
        self._report()

    # --- Étapes -------------------------------------------------------------------------------------------------

    def _users(self) -> dict[str, User]:
        users = {}
        for email, full_name, _org, role, _scope, _ref in demo.USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, full_name=full_name)
            is_staff = role is None or not Role.objects.filter(organization=None, code=role, is_pme_role=True).exists()
            if is_staff:
                if not user.has_usable_password():
                    user.set_password(demo.DEMO_PASSWORD)
                user.mfa_secret = demo_totp_secret(email)
                user.mfa_enabled = True
            user.is_platform_admin = role is None
            user.save()
            users[email] = user
        return users

    def _organizations(self, platform_admin: User) -> dict[str, Organization]:
        organizations = {}
        with system_context():
            for spec in demo.ORGANIZATIONS:
                organization, _ = Organization.objects.update_or_create(
                    slug=spec["slug"],
                    defaults={
                        "name": spec["name"],
                        "type": spec["type"],
                        "branding": spec["branding"],
                        "created_by": platform_admin,
                    },
                )
                organizations[spec["slug"]] = organization
        return organizations

    def _programme(self, organization: Organization) -> Programme:
        spec = demo.PROGRAMME
        programme, _ = Programme.objects.get_or_create(
            name=spec["name"],
            defaults={
                "funder": spec["funder"],
                "start_date": spec["start_date"],
                "end_date": spec["end_date"],
                "description": "Programme fictif de démonstration.",
            },
        )
        Cohort.objects.get_or_create(
            programme=programme, name=spec["cohort"], defaults={"start_date": spec["start_date"]}
        )
        return programme

    def _memberships(self, slug: str, users: dict, programme: Programme | None, pmes: dict[str, Pme]) -> None:
        for email, _name, org_slug, role_code, scope, ref in demo.USERS:
            if org_slug != slug:
                continue
            scope_ref_id = programme.id if ref == "programme" else (pmes[ref].id if ref else None)
            UserMembership.objects.get_or_create(
                user=users[email],
                role=Role.objects.get(organization=None, code=role_code),
                scope=scope,
                scope_ref_id=scope_ref_id,
            )

    def _pmes(self, slug: str, users: dict, programme: Programme | None) -> dict[str, Pme]:
        pmes = {}
        for spec in demo.PMES:
            if spec["org"] != slug:
                continue
            data = dict(spec["data"])
            existing = Pme.objects.filter(rccm_number=data["rccm_number"]).first()
            if existing:
                pmes[spec["key"]] = existing
                continue
            data["legal_form"] = LegalForm.objects.get(code=data["legal_form"])
            data["sector"] = Sector.objects.get(code=data["sector"])
            data["region"] = Region.objects.get(code=data["region"])
            pme = Pme.objects.create(**data, last_activity_at=timezone.now())
            audit.record(
                "pme.created", instance=pme, pme_id=pme.pk, after={"legal_name": pme.legal_name, "source": "seed_demo"}
            )
            pmes[spec["key"]] = pme
        return pmes

    def _pme_setup(self, slug: str, organization: Organization, users: dict, programme, pmes: dict[str, Pme]) -> None:
        admin_email = next(u[0] for u in demo.USERS if u[2] == slug and u[3] == "ADMIN_ORG")
        admin = users[admin_email]
        access = build_access(admin, organization.id)
        cohort = programme.cohorts.first() if programme else None
        for spec in demo.PMES:
            if spec["org"] != slug:
                continue
            pme = pmes[spec["key"]]
            if not pme.persons.exists():
                pme_services.add_person(pme, {**spec["person"], "is_primary_contact": True}, admin)
            for key, role in (("advisor", "CONSEILLER_PRINCIPAL"), ("expert", "EXPERT")):
                if (
                    spec.get(key)
                    and not PmeAssignment.objects.filter(pme=pme, role_in_pme=role, end_date__isnull=True).exists()
                ):
                    pme_services.assign(pme, users[spec[key]], role, admin)
            if cohort and spec["cohort"] and not pme.enrollments.exists():
                pme.enrollments.create(cohort=cohort, enrolled_at=timezone.localdate())
            target = spec["status"]
            if target != "PROSPECT" and pme.lifecycle_status == "PROSPECT":
                for status in demo.LIFECYCLE_PATH[: demo.LIFECYCLE_PATH.index(target) + 1]:
                    pme_services.transition(pme, status, access.user)

    def _diagnostics(self, slug: str, organization: Organization, users: dict, pmes: dict[str, Pme]) -> None:
        """Diagnostics fictifs : questionnaire, soumission, revue en lot et validation par le conseiller."""
        admin_email = next(u[0] for u in demo.USERS if u[2] == slug and u[3] == "ADMIN_ORG")
        for spec in demo.PMES:
            plans = demo_diagnostics.DIAGNOSTICS.get(spec["key"], [])
            pme = pmes.get(spec["key"])
            if spec["org"] != slug or not plans or Diagnostic.objects.filter(pme=pme).exists():
                continue
            advisor = users[spec.get("advisor") or admin_email]
            access = build_access(advisor, organization.id)
            for plan in plans:
                pme.refresh_from_db()
                diagnostic = diagnostic_services.start_diagnostic(
                    access, pme, plan["type"], date.fromisoformat(plan["date"])
                )
                self._answer(diagnostic, plan, advisor)
                if plan["status"] in ("EN_REVUE", "VALIDE"):
                    diagnostic_services.submit(diagnostic, access)
                if plan["status"] == "VALIDE":
                    diagnostic_services.accept_remaining(diagnostic, access)
                    diagnostic_services.validate(diagnostic, access)

    @staticmethod
    def _answer(diagnostic: Diagnostic, plan: dict, advisor: User) -> None:
        by_advisor = plan["source"] == "CONSEILLER"
        when = timezone.make_aware(datetime.combine(diagnostic.reference_date, time(10)))
        only = plan.get("only_dimensions")
        questions = Question.objects.filter(framework_version=diagnostic.framework_version).select_related(
            "criterion__dimension"
        )
        for question in questions:
            value = None
            if question.code in plan["profile"]:
                value = plan["profile"][question.code]
            elif question.code == "PRO-EFF":
                value = diagnostic.pme.headcount
            elif question.feeds.startswith("input."):
                value = plan["financials"].get(question.feeds.split(".", 1)[1])
            elif question.criterion_id:
                dimension = question.criterion.dimension.code
                if (only and dimension not in only) or dimension not in plan["base"]:
                    continue
                offset = (-1, 0, 0, 1)[zlib.crc32(question.criterion.code.encode()) % 4]  # variation déterministe
                level = plan["forced"].get(question.criterion.code, plan["base"][dimension] + offset)
                value = str(max(0, min(4, level)))
            if value is None:
                continue
            Answer.objects.update_or_create(
                diagnostic=diagnostic,
                question=question,
                defaults={
                    "value": value,
                    "answered_at": when,
                    "answered_by": advisor if by_advisor else None,
                    "source": Answer.Source.CONSEILLER if by_advisor else Answer.Source.PME,
                },
            )

    def _report(self) -> None:
        self.stdout.write(self.style.SUCCESS("Données de démonstration chargées (toutes fictives)."))
        self.stdout.write(f"Mot de passe des comptes équipe : {demo.DEMO_PASSWORD}")
        self.stdout.write("Code MFA d'un compte équipe : python manage.py demo_totp <email>")
        self.stdout.write("Comptes PME (connexion par code e-mail, visible dans Mailpit http://localhost:8035) :")
        for email, _name, _org, role, _scope, _ref in demo.USERS:
            self.stdout.write(f"  {email:32} {role or 'SUPER_ADMIN'}")
