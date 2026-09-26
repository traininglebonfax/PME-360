"""Routes de l'API v1 (Document 2, § 6.1)."""

from django.db import connection
from django.urls import include, path
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from pme360.accounts import views as accounts
from pme360.ai import views as ai
from pme360.alerts import views as alerts
from pme360.audit import views as audit
from pme360.compliance import views as compliance
from pme360.dashboards import views as dashboards
from pme360.diagnostic import views as diagnostic
from pme360.documents import views as documents
from pme360.notifications import views as notifications
from pme360.organizations import views as organizations
from pme360.plans import views as plans
from pme360.pmes import views as pmes
from pme360.reports import views as reports
from pme360.scoring import views as scoring


@extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})


health.cls.requires_organization = False

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pmes", pmes.PmeViewSet, basename="pme")
router.register("pmes/<uuid:pme_pk>/persons", pmes.PmePersonViewSet, basename="pme-person")
router.register("programmes", organizations.ProgrammeViewSet, basename="programme")
router.register("platform/organizations", organizations.PlatformOrganizationViewSet, basename="platform-organization")

urlpatterns = [
    path("health", health),
    path("schema", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]), name="docs"),
    # Authentification
    path("auth/csrf", accounts.CsrfView.as_view()),
    path("auth/login", accounts.LoginView.as_view()),
    path("auth/logout", accounts.LogoutView.as_view()),
    path("auth/mfa/verify", accounts.MfaVerifyView.as_view()),
    path("auth/mfa/setup", accounts.MfaSetupView.as_view()),
    path("auth/mfa/confirm", accounts.MfaConfirmView.as_view()),
    path("auth/otp/request", accounts.OtpRequestView.as_view()),
    path("auth/otp/verify", accounts.OtpVerifyView.as_view()),
    path("auth/password/reset", accounts.PasswordResetRequestView.as_view()),
    path("auth/password/reset/confirm", accounts.PasswordResetConfirmView.as_view()),
    path("auth/switch-organization", accounts.SwitchOrganizationView.as_view()),
    path("me", accounts.MeView.as_view()),
    # Utilisateurs et rôles
    path("users", accounts.OrganizationMembersView.as_view()),
    path("users/invite", accounts.InviteView.as_view()),
    path("users/advisors", accounts.AdvisorListView.as_view()),
    path("memberships/<uuid:membership_id>/revoke", accounts.RevokeMembershipView.as_view()),
    path("roles", accounts.RoleListView.as_view()),
    # Organisation
    path("organization", organizations.CurrentOrganizationView.as_view()),
    # Nomenclatures
    path("ref/<str:kind>", pmes.ReferenceListView.as_view()),
    # Tableaux de bord
    path("dashboards/advisor", dashboards.AdvisorDashboardView.as_view()),
    path("dashboards/portfolio", dashboards.PortfolioDashboardView.as_view()),
    path("dashboards/portfolio/analyses", dashboards.PortfolioAnalysesView.as_view()),
    path("dashboards/portfolio/pmes", dashboards.PortfolioPmesView.as_view()),
    # Rapports (Document 9, § 7)
    # Import en masse des PME (CSV, V1)
    path("pme-import/template", pmes.PmeImportTemplateView.as_view()),
    path("pme-import/preview", pmes.PmeImportPreviewView.as_view()),
    path("pme-import", pmes.PmeImportView.as_view()),
    path("pmes/<uuid:pme_id>/reports", reports.PmeReportsView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/report", reports.DiagnosticReportView.as_view()),
    path("reports/<uuid:report_id>/pdf", reports.ReportPdfView.as_view()),
    path("dashboards/pme/<uuid:pme_id>", dashboards.PmeDashboardView.as_view()),
    # Référentiel de diagnostic
    path("framework-versions", diagnostic.FrameworkVersionListView.as_view()),
    path("framework-versions/<uuid:version_id>", diagnostic.FrameworkVersionDetailView.as_view()),
    path("framework-versions/<uuid:version_id>/clone", diagnostic.FrameworkVersionCloneView.as_view()),
    path("framework-versions/<uuid:version_id>/publish", diagnostic.FrameworkVersionPublishView.as_view()),
    # Diagnostics
    path("pmes/<uuid:pme_id>/diagnostics", diagnostic.PmeDiagnosticsView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>", diagnostic.DiagnosticDetailView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/questionnaire", diagnostic.QuestionnaireView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/answers", diagnostic.AnswersView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/submit", diagnostic.SubmitView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/reopen", diagnostic.ReopenView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/cancel", diagnostic.CancelView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/review", diagnostic.ReviewView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/review/accept-remaining", diagnostic.AcceptRemainingView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/review/<str:criterion_code>", diagnostic.ReviewCriterionView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/validate", diagnostic.ValidateView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/preview", scoring.DiagnosticPreviewView.as_view()),
    # Scores
    path("pmes/<uuid:pme_id>/health-check", scoring.HealthCheckView.as_view()),
    path("snapshots/<uuid:snapshot_id>", scoring.SnapshotDetailView.as_view()),
    path("snapshots/<uuid:snapshot_id>/compare/<uuid:other_id>", scoring.SnapshotCompareView.as_view()),
    # Documents et dossier de conformité
    path("document-types", documents.DocumentTypeListView.as_view()),
    path("pmes/<uuid:pme_id>/documents", documents.PmeDocumentsView.as_view()),
    path("documents/<uuid:document_id>", documents.DocumentDetailView.as_view()),
    path("documents/<uuid:document_id>/verify", documents.DocumentVerifyView.as_view()),
    path("documents/<uuid:document_id>/versions/<int:version_no>/download-url", documents.DownloadUrlView.as_view()),
    path("files/<str:token>", documents.FileDownloadView.as_view()),
    path("verifications", ai.VerificationQueueView.as_view()),
    # IA (Document 4) : extraction, revue, traçabilité, pré-diagnostic, analyse financière, Copilot
    path("documents/<uuid:document_id>/extraction", ai.DocumentExtractionView.as_view()),
    path("documents/<uuid:document_id>/extraction/review", ai.ExtractionReviewView.as_view()),
    path("documents/<uuid:document_id>/reanalyze", ai.DocumentReanalyzeView.as_view()),
    path("ai/analyses", ai.AnalysisListView.as_view()),
    path("ai/analyses/<uuid:analysis_id>", ai.AnalysisDetailView.as_view()),
    path("ai/settings", ai.AiSettingsView.as_view()),
    path("ai/evaluations", ai.EvaluationListView.as_view()),
    path("ai/reindex", ai.ReindexView.as_view()),
    path("ai/conversations", ai.ConversationListView.as_view()),
    path("ai/conversations/<uuid:conversation_id>", ai.ConversationDetailView.as_view()),
    path("ai/conversations/<uuid:conversation_id>/messages", ai.ConversationAskView.as_view()),
    path("diagnostics/<uuid:diagnostic_id>/suggestions", ai.SuggestionListView.as_view()),
    path("pmes/<uuid:pme_id>/financial-analysis", ai.FinancialAnalysisView.as_view()),
    path("pmes/<uuid:pme_id>/financial-analysis/interpretation", ai.FinancialInterpretationView.as_view()),
    # Accompagnement (Document 7) : recommandations, plan versionné, actions, livrables, catalogue et règles
    path("pmes/<uuid:pme_id>/recommendations", plans.PmeRecommendationsView.as_view()),
    path("pmes/<uuid:pme_id>/recommendations/manual", plans.ManualRecommendationView.as_view()),
    path("recommendations/<uuid:recommendation_id>/decision", plans.RecommendationDecisionView.as_view()),
    path("pmes/<uuid:pme_id>/plan", plans.PmePlanView.as_view()),
    path("pmes/<uuid:pme_id>/plans", plans.PmePlanHistoryView.as_view()),
    path("pmes/<uuid:pme_id>/plan/generate", plans.PlanGenerateView.as_view()),
    path("plans/<uuid:plan_id>", plans.PlanDetailView.as_view()),
    path("plans/<uuid:plan_id>/transition", plans.PlanTransitionView.as_view()),
    path("plans/<uuid:plan_id>/new-version", plans.PlanNewVersionView.as_view()),
    path("actions", plans.ActionListView.as_view()),
    path("actions/<uuid:action_id>", plans.ActionDetailView.as_view()),
    path("actions/<uuid:action_id>/transition", plans.ActionTransitionView.as_view()),
    path("actions/<uuid:action_id>/dependencies", plans.ActionDependencyView.as_view()),
    path("actions/<uuid:action_id>/comments", plans.ActionCommentsView.as_view()),
    path("support-offers", plans.SupportOfferListView.as_view()),
    path("deliverable-templates", plans.DeliverableTemplateListView.as_view()),
    path("recommendation-rules", plans.RuleListView.as_view()),
    path("recommendation-rules/variables", plans.RuleVariablesView.as_view()),
    path("recommendation-rules/<uuid:rule_id>/test", plans.RuleTestView.as_view()),
    path("recommendation-rules/<uuid:rule_id>/activate", plans.RuleStatusView.as_view(target="activate")),
    path("recommendation-rules/<uuid:rule_id>/deactivate", plans.RuleStatusView.as_view(target="deactivate")),
    path("pmes/<uuid:pme_id>/compliance-folder", compliance.ComplianceFolderView.as_view()),
    path("pmes/<uuid:pme_id>/deadlines", compliance.PmeDeadlinesView.as_view()),
    path("deadlines/upcoming", compliance.UpcomingDeadlinesView.as_view()),
    path("deadlines/<uuid:deadline_id>/waive", compliance.DeadlineWaiveView.as_view()),
    path("regulatory-rules", compliance.RegulatoryRuleListView.as_view()),
    path("regulatory-rules/<uuid:rule_id>/verify", compliance.RegulatoryRuleVerifyView.as_view()),
    path("regulatory-rules/<uuid:rule_id>/status", compliance.RegulatoryRuleStatusView.as_view()),
    path("obligation-templates", compliance.ObligationTemplateListView.as_view()),
    path("obligation-templates/<uuid:template_id>/activation", compliance.ObligationTemplateActivationView.as_view()),
    path("compliance/run", compliance.ComplianceRunView.as_view()),
    # Alertes et notifications
    path("alerts", alerts.AlertListView.as_view()),
    path("alerts/<uuid:alert_id>/transition", alerts.AlertTransitionView.as_view()),
    path("alert-rules", alerts.AlertRuleListView.as_view()),
    path("alert-rules/<uuid:rule_id>", alerts.AlertRuleDetailView.as_view()),
    path("notifications", notifications.NotificationListView.as_view()),
    path("notifications/unread-count", notifications.NotificationCountView.as_view()),
    path("notifications/read", notifications.NotificationReadView.as_view()),
    path("me/notification-preferences", notifications.NotificationPreferencesView.as_view()),
    # Audit
    path("audit-logs", audit.AuditLogListView.as_view()),
    path("audit-logs/verify", audit.AuditVerifyView.as_view()),
    path("", include(router.urls)),
]
