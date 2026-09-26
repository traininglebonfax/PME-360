"""Éditeur sans code du référentiel (V1) : brouillon seul, contrôles, équilibre des poids, audit, publication."""

import pytest

from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context
from pme360.diagnostic.models import Criterion, FrameworkVersion, Question
from pme360.diagnostic.referential import install_gude360

pytestmark = pytest.mark.django_db
RUBRIC = ["Rien", "Informel", "Partiel", "En place", "Maîtrisé et vérifié"]


@pytest.fixture
def framework(org):
    with tenant_context(org.id):
        return install_gude360(org)


@pytest.fixture
def admin(org, make_user, client_for):
    return client_for(make_user(org, "ADMIN_ORG"), org)


@pytest.fixture
def draft(framework, admin):
    response = admin.post(f"/api/v1/framework-versions/{framework.id}/clone", {"version": "1.1.0"}, format="json")
    assert response.status_code == 201
    return response.json()["id"]


def _criterion(tree, code):
    return next(c for d in tree["dimensions"] for c in d["criteria"] if c["code"] == code)


def _dimension_balance(tree, code):
    return next(d for d in tree["issues"]["balance"]["dimensions"] if d["code"] == code)


def test_published_version_is_read_only_in_editor(framework, admin):
    tree = admin.get(f"/api/v1/framework-versions/{framework.id}/editor").json()
    assert tree["editable"] is False and tree["issues"]["errors"] == []
    criterion = _criterion(tree, "FOR-01")
    refused = admin.patch(
        f"/api/v1/framework-versions/{framework.id}/criteria/{criterion['id']}", {"weight": 5}, format="json"
    )
    assert refused.status_code == 400 and refused.json()["code"] == "version_not_draft"


def test_admin_rebalances_weights_adds_a_criterion_and_publishes(org, framework, admin, draft, make_user, client_for):
    base = f"/api/v1/framework-versions/{draft}"
    tree = admin.get(f"{base}/editor").json()
    assert tree["editable"] is True
    for_01 = _criterion(tree, "FOR-01")
    before = _dimension_balance(tree, "D01")
    assert before["actual"] == before["expected"]

    # Baisser un poids : enregistré, mais la publication est bloquée tant que D01 n'est pas équilibrée.
    lowered = admin.patch(f"{base}/criteria/{for_01['id']}", {"weight": float(for_01["weight"]) - 5}, format="json")
    assert lowered.status_code == 200, lowered.content
    unbalanced = _dimension_balance(lowered.json(), "D01")
    assert float(unbalanced["actual"]) == float(before["actual"]) - 5
    assert any("D01" in e for e in lowered.json()["issues"]["errors"])
    assert admin.post(f"{base}/publish").status_code == 400

    # Nouveau critère de 5 points avec sa question principale générée depuis la grille.
    created = admin.post(
        f"{base}/criteria",
        {
            "code": "for-99",
            "dimension": "D01",
            "name": "Registre des décisions tenu à jour",
            "lens": "O",
            "weight": 5,
            "rubric": RUBRIC,
            "applicability": {"==": [{"var": "is_company"}, True]},
            "evidence_policy": "RECOMMENDED",
            "evidence_document_types": ["STATUTS"],
            "question": "Tenez-vous un registre des décisions ?",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    tree = created.json()
    new = _criterion(tree, "FOR-99")
    assert new["questions"][0]["code"] == "Q-FOR-99"
    assert [o["label"] for o in new["questions"][0]["options"]] == RUBRIC
    assert tree["issues"]["errors"] == []

    # La grille modifiée met à jour les réponses de la question principale.
    rubric = [*RUBRIC[:4], "Tenu, signé et archivé"]
    updated = admin.patch(f"{base}/criteria/{new['id']}", {"rubric": rubric}, format="json").json()
    assert _criterion(updated, "FOR-99")["questions"][0]["options"][4]["label"] == "Tenu, signé et archivé"

    # Contrôles de saisie.
    bad = admin.post(
        f"{base}/criteria",
        {"code": "FOR-99", "dimension": "D01", "name": "x", "lens": "O", "weight": 1, "rubric": RUBRIC[:3]},
        format="json",
    )
    assert bad.status_code == 400 and "code" in bad.json()["errors"]
    bad_rubric = admin.patch(f"{base}/criteria/{new['id']}", {"rubric": ["a", "", "c", "d", "e"]}, format="json")
    assert bad_rubric.status_code == 400 and "rubric" in bad_rubric.json()["errors"]
    bad_docs = admin.patch(f"{base}/criteria/{new['id']}", {"evidence_document_types": ["INCONNU"]}, format="json")
    assert bad_docs.status_code == 400
    code_change = admin.patch(f"{base}/criteria/{new['id']}", {"code": "AUTRE"}, format="json")
    assert code_change.status_code == 400

    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.patch(f"{base}/criteria/{new['id']}", {"weight": 1}, format="json").status_code == 403

    published = admin.post(f"{base}/publish")
    assert published.status_code == 200, published.content
    with tenant_context(org.id):
        version = FrameworkVersion.objects.get(pk=draft)
        assert Criterion.objects.get(framework_version=version, code="FOR-99").weight == 5
        actions = set(AuditLog.objects.filter(action__startswith="framework.").values_list("action", flat=True))
        assert {"framework.criterion_created", "framework.criterion_updated", "framework.published"} <= actions


def test_questions_and_dimensions_edition(org, draft, admin):
    base = f"/api/v1/framework-versions/{draft}"
    tree = admin.get(f"{base}/editor").json()
    d01 = next(d for d in tree["dimensions"] if d["code"] == "D01")
    feeding = next(q for q in d01["questions"] if q["feeds"])
    refused = admin.delete(f"{base}/questions/{feeding['id']}")
    assert refused.status_code == 400 and refused.json()["code"] == "question_feeds_engine"

    created = admin.post(
        f"{base}/questions",
        {
            "code": "Q-FOR-01-B",
            "criterion": "FOR-01",
            "text": "Vos statuts sont-ils à jour ?",
            "type": "SINGLE",
            "options": [{"label": "Non", "level": 0}, {"label": "Oui", "level": 3}],
            "target_audience": "PME",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    question = next(q for q in _criterion(created.json(), "FOR-01")["questions"] if q["code"] == "Q-FOR-01-B")
    assert [o["value"] for o in question["options"]] == ["0", "3"]
    one_option = admin.patch(
        f"{base}/questions/{question['id']}", {"options": [{"label": "Oui", "level": 3}]}, format="json"
    )
    assert one_option.status_code == 400
    assert admin.delete(f"{base}/questions/{question['id']}").status_code == 200

    # Dimension : création, refus de suppression tant qu'elle contient des critères.
    new_dim = admin.post(
        f"{base}/dimensions", {"code": "D13", "pillar": "C", "name": "Innovation", "weight": 5}, format="json"
    )
    assert new_dim.status_code == 201
    assert any("Pilier C" in e for e in new_dim.json()["issues"]["errors"])
    d13 = next(d for d in new_dim.json()["dimensions"] if d["code"] == "D13")
    assert admin.delete(f"{base}/dimensions/{d13['id']}").status_code == 200
    not_empty = admin.delete(f"{base}/dimensions/{d01['id']}")
    assert not_empty.status_code == 400 and not_empty.json()["code"] == "dimension_not_empty"

    pillar = tree["pillars"][0]
    assert admin.patch(f"{base}/pillars/{pillar['id']}", {"weight": 0}, format="json").status_code == 400


def test_deleted_criterion_used_by_support_warns_and_draft_can_be_discarded(org, framework, draft, admin):
    base = f"/api/v1/framework-versions/{draft}"
    tree = admin.get(f"{base}/editor").json()
    with tenant_context(org.id):
        from pme360.plans.services import ensure_catalog

        ensure_catalog(org)
        from pme360.plans.models import SupportOffer

        target = SupportOffer.objects.filter(is_active=True).exclude(target_criteria=[]).first()
        code = target.target_criteria[0]
    criterion = _criterion(tree, code)
    after = admin.delete(f"{base}/criteria/{criterion['id']}").json()
    assert any(w.startswith(f"{code} n'existe plus") for w in after["issues"]["warnings"])
    with tenant_context(org.id):
        assert not Question.objects.filter(framework_version_id=draft, criterion__code=code).exists()

    assert admin.delete(base + "/editor").status_code == 204
    with tenant_context(org.id):
        assert not FrameworkVersion.objects.filter(pk=draft).exists()
    refused = admin.delete(f"/api/v1/framework-versions/{framework.id}/editor")
    assert refused.status_code == 400
