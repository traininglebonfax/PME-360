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
from pme360.compliance.defaults import install as install_compliance
from pme360.core.tenancy import system_context, tenant_context
from pme360.diagnostic import services as diagnostic_services
from pme360.diagnostic.models import Answer, Diagnostic, Question
from pme360.diagnostic.referential import install_gude360
from pme360.organizations.models import Cohort, Organization, Programme
from pme360.plans.services import install_plans
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
                install_compliance(organization)
                install_plans(organization)
                programme = self._programme(organization) if slug == "gude-pme-demo" else None
                pmes = self._pmes(slug, users, programme)
                self._memberships(slug, users, programme, pmes)
                self._pme_setup(slug, organization, users, programme, pmes)
                self._diagnostics(slug, organization, users, pmes)
                self._documents(slug, organization, users, pmes)
                self._plans(slug, organization, users, pmes)
                self._reports(pmes)
        self._report()

    def _reports(self, pmes: dict[str, Pme]) -> None:
        """Phase 6 : rapport de diagnostic (16 sections) pour chaque PME ayant un diagnostic validé."""
        from pme360.reports import services as reports
        from pme360.reports.models import Report

        for pme in pmes.values():
            diagnostic = Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date")
            latest = diagnostic.first()
            if latest and not Report.objects.filter(diagnostic=latest).exists():
                reports.generate_diagnostic_report(latest)

    def _plans(self, slug: str, organization: Organization, users: dict, pmes: dict[str, Pme]) -> None:
        """Accompagnement (phase 5) : recommandations ; plan de Boutik Plus accepté, une action menée à terme."""
        from datetime import timedelta

        from pme360.documents import pipeline
        from pme360.documents import services as documents
        from pme360.documents.models import DocumentType
        from pme360.plans import services as plans
        from pme360.plans.models import ActionPlan, Recommendation
        from seeds.pdfkit import text_pdf

        if slug != "gude-pme-demo":
            return
        for key in ("BOUTIK", "DELICES"):
            pme = pmes.get(key)
            if pme is None or Recommendation.objects.filter(pme=pme).exists():
                continue
            diagnostic = Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date")
            if diagnostic.exists():
                plans.generate_recommendations(diagnostic.first())
        boutik = pmes.get("BOUTIK")
        if boutik is None or ActionPlan.objects.filter(pme=boutik).exists():
            return
        advisor = build_access(users["konan.conseiller@demo.test"], organization.id)
        leader = build_access(users["aya.dirigeante@demo.test"], organization.id)
        proposed = Recommendation.objects.filter(pme=boutik, status=Recommendation.Status.PROPOSEE)
        for recommendation in proposed.order_by("-priority_final")[:5]:
            plans.decide_recommendation(recommendation, advisor, status=Recommendation.Status.ACCEPTEE)
        plan = plans.generate_plan(boutik, advisor, horizon_start=timezone.localdate() - timedelta(days=20))
        plans.transition_plan(plan, advisor, "submit")
        plans.transition_plan(plan, advisor, "validate")
        plans.transition_plan(plan, leader, "accept")
        startable = [a for a in plan.actions.order_by("position") if a.status == "NON_COMMENCE"]
        if not startable:
            return
        first = startable[0]
        plans.transition_action(first, leader, "EN_COURS")
        for deliverable in first.deliverables.all():
            lines = [
                "DOCUMENT DE DEMONSTRATION - FICTIF",
                deliverable.title.upper(),
                f"Entreprise : {boutik.legal_name}",
                f"Etabli le {timezone.localdate():%d/%m/%Y} dans le cadre de l'action {first.human_ref}.",
            ]
            result = documents.upload(
                leader,
                boutik,
                filename=f"{deliverable.document_type_code.lower()}-demo.pdf",
                content=text_pdf(lines),
                document_type=DocumentType.objects.get(code=deliverable.document_type_code),
                title=f"{deliverable.title} (démonstration)",
            )
            plans.on_deliverable_uploaded(deliverable, result.document, leader.user)
            pipeline.process(str(result.version.pk))
            result.document.refresh_from_db()
            documents.verify(advisor, result.document, decision="CONFORME")
        for action in startable[1:2]:
            plans.transition_action(action, leader, "EN_COURS")
            plans.transition_action(action, advisor, "DOCUMENT_DEMANDE")

    def _documents(self, slug: str, organization: Organization, users: dict, pmes: dict[str, Pme]) -> None:
        """Documents fictifs déposés, analysés par l'IA (moteur local), vérifiés ; échéances et alertes (phases 3-4)."""
        from datetime import timedelta

        from pme360.ai import documents as ai_documents
        from pme360.ai.knowledge import reindex_organization
        from pme360.ai.models import DocumentExtraction
        from pme360.compliance import services as compliance
        from pme360.documents import pipeline
        from pme360.documents import services as documents
        from pme360.documents.models import Document, DocumentType
        from seeds import demo_documents
        from seeds.pdfkit import text_pdf

        today = timezone.localdate()
        for spec in demo.PMES:
            pme = pmes.get(spec["key"])
            if spec["org"] != slug or pme is None:
                continue
            pme.refresh_from_db()
            items = [d for d in demo_documents.DOCUMENTS if d[0] == spec["key"]]
            if items and not Document.objects.filter(pme=pme).exists():
                advisor = users[spec["advisor"]] if spec.get("advisor") else None
                leader_email = next((u[0] for u in demo.USERS if u[3] == "DIRIGEANT_PME" and u[5] == spec["key"]), None)
                pme_data = {"key": spec["key"], **spec["data"]}
                for _, type_code, decision, reason, expires_in in items:
                    uploader = users[leader_email] if decision is None and leader_email else advisor
                    access = build_access(uploader, organization.id)
                    document_type = DocumentType.objects.get(code=type_code)
                    issued_at = today - timedelta(days=60)
                    expires_at = today + timedelta(days=expires_in) if expires_in else None
                    result = documents.upload(
                        access,
                        pme,
                        filename=f"{type_code.lower()}-demo.pdf",
                        content=text_pdf(demo_documents.content(pme_data, type_code, today, expires_at, issued_at)),
                        document_type=document_type,
                        title=f"{document_type.name} (démonstration)",
                        issued_at=issued_at,
                        expires_at=expires_at,
                    )
                    pipeline.process(str(result.version.pk))  # analyse immédiate (idempotente)
                    if decision:
                        reviewer = build_access(advisor, organization.id)
                        documents.verify(reviewer, result.document, decision=decision, reason=reason)
                        extraction = DocumentExtraction.objects.filter(version=result.version).first()
                        if (
                            extraction
                            and extraction.schema_code
                            and extraction.status not in DocumentExtraction.REVIEWED
                        ):
                            ai_documents.review(
                                extraction,
                                reviewer,
                                status=DocumentExtraction.Status.VALIDEE,
                                corrections={},
                                comment="",
                            )
            compliance.run_for_pme(pme, today)
        reindex_organization()

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
