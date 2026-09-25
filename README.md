# GUDE-PME 360 — PME Growth & Compliance Management System

> **Connaître · Diagnostiquer · Scorer · Accompagner · Mesurer**

Plateforme de diagnostic 360°, de scoring, d'accompagnement, de conformité documentaire et de pilotage de portefeuille des PME, conçue pour **GUDE-PME Côte d'Ivoire** et pensée dès l'origine comme multi-organisation (programmes publics, incubateurs, banques, bailleurs, cabinets).

## Dénomination

| Élément | Proposition | Justification |
|---|---|---|
| Nom produit (instance GUDE-PME) | **GUDE-PME 360** | Court, lisible, porte la marque du client. |
| Nom plateforme (moteur multi-tenant) | **PME360** | Neutre : réutilisable pour d'autres organisations sans rebranding du code. |
| Signature | *Connaître · Accompagner · Mesurer* | Résume les 5 niveaux du produit. |

Le code et les modèles de données utilisent le nom neutre `pme360` ; le branding GUDE-PME est une configuration du tenant.

## État du projet

| Phase | Statut |
|---|---|
| 0 — Analyse & architecture | ✅ Livrée ; recommandations D-01 à D-08 acceptées à titre provisoire le 25/09/2026 ([décisions](docs/00-decisions-ouvertes.md)) |
| 1 — Socle | ✅ Livrée (voir ci-dessous) |
| 2 — Diagnostic | À venir : référentiel GUDE-360, questionnaire adaptatif, moteur de scoring |

### Contenu de la phase 1

- **Multi-tenant** : `organization_id` + Row-Level Security PostgreSQL **forcée** sur toutes les tables métier, doublée d'un filtre applicatif ; rôle de base de données sans privilège (ni superutilisateur ni BYPASSRLS).
- **Authentification** : équipes GUDE-PME par mot de passe (Argon2id) + TOTP obligatoire (secret chiffré, anti-rejeu) ; PME par code à usage unique envoyé par e-mail ; verrouillage progressif, limitation de débit, CSRF, sessions 8 h / 30 jours.
- **RBAC + périmètres** : 7 rôles système et 23 permissions stockés en base ; périmètres organisation, programme, portefeuille, PME.
- **Organisations, programmes, cohortes** ; administration plateforme sans accès aux données des PME.
- **PME** : fiche d'identité, dirigeants (parts ≤ 100 %), assignation des conseillers, cycle de vie, détection des doublons (RCCM/NCC bloquants, raison sociale approchante par similarité trigramme).
- **Journal d'audit** en ajout seul (trigger), chaîné par hash et vérifiable ; historique de chaque PME.
- **Tableaux de bord** (squelette) : conseiller, portefeuille, portail PME. Les indicateurs des phases suivantes s'affichent « Disponible en phase N », jamais avec un chiffre inventé.
- **Données de démonstration** fictives : 6 PME du Document 3, § 7, et une seconde organisation pour démontrer l'isolation.
- **Qualité** : 84 tests backend (dont 21 d'isolation RLS), 6 tests unitaires frontend, 3 tests E2E Playwright du parcours ; ruff, ESLint, typage strict, client TypeScript généré depuis OpenAPI ; CI GitHub Actions.

## Démarrage en local

Prérequis : Docker, Python 3.12+ (testé en 3.14), Node 24. Les ports sont décalés pour cohabiter avec d'autres projets : PostgreSQL **5442**, Redis **6390**, API **8010**, frontend **3010**, Mailpit **8035**.

```bash
# 1. Infrastructure (PostgreSQL + pgvector, Redis, Mailpit)
docker compose -f infra/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS : .venv/bin/pip
cp .env.example .env        # puis renseigner DJANGO_SECRET_KEY et PME360_FIELD_ENCRYPTION_KEYS
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo          # données fictives
.venv/Scripts/python manage.py runserver 127.0.0.1:8010

# 3. Frontend
cd ../frontend && npm install && npm run dev      # http://localhost:3010
```

**Comptes de démonstration** (tous fictifs, domaine `@demo.test`) :

| Compte | Rôle | Connexion |
|---|---|---|
| `admin@demo.test` | Administrateur GUDE-PME | mot de passe `Demo-PME360-2026!` + code MFA : `python manage.py demo_totp admin@demo.test` |
| `konan.conseiller@demo.test`, `awa.conseillere@demo.test` | Conseillers | idem |
| `programme@demo.test`, `expert@demo.test`, `auditeur@demo.test` | Responsable programme, expert, auditeur | idem |
| `aya.dirigeante@demo.test` | Dirigeante de Boutik Plus (PME) | onglet « Espace PME » ; code reçu dans Mailpit (http://localhost:8035) |
| `superadmin@demo.test` | Administrateur plateforme | mot de passe + code MFA |

**Tests** : `cd backend && .venv/Scripts/python -m pytest` · `cd frontend && npm test && npm run test:e2e` (E2E : infrastructure, API et seed lancés au préalable).

**Documentation de l'API** : http://localhost:8010/api/v1/docs (OpenAPI). Après toute modification de l'API : `npm run api:types` dans `frontend/`.

## Documents de conception

| # | Document | Contenu |
|---|---|---|
| 0 | [Décisions ouvertes & registre des choix](docs/00-decisions-ouvertes.md) | Choix structurants à valider, hypothèses, ADR |
| 1 | [Architecture fonctionnelle](docs/01-architecture-fonctionnelle.md) | Personas, parcours, modules, rôles, règles métier, configuration sans code |
| 2 | [Architecture technique](docs/02-architecture-technique.md) | Stack, monolithe modulaire, multi-tenant, API, sécurité, déploiement |
| 3 | [Modèle de données](docs/03-modele-donnees.md) | Entités, relations, contraintes, versionnement |
| 4 | [Architecture IA](docs/04-architecture-ia.md) | Pipeline documentaire, extraction, RAG, Copilot, human-in-the-loop, traçabilité |
| 5 | [Matrice des dimensions](docs/05-matrice-dimensions.md) | 12 dimensions en 3 piliers, critères, preuves attendues |
| 6 | [Matrice de scoring](docs/06-matrice-scoring.md) | Maturité vs performance, confiance, niveaux, priorité, formules financières |
| 7 | [Workflow d'accompagnement](docs/07-workflow-accompagnement.md) | Cycle diagnostic → plan → actions → preuves → re-score, moteur de règles, moteur d'alertes et notifications |
| 8 | [Matrice documents / obligations](docs/08-matrice-documents-obligations.md) | Dossier de conformité, périodicités, registre réglementaire sourcé |
| 9 | [Architecture des dashboards](docs/09-architecture-dashboards.md) | Tableaux de bord PME, conseiller, programme, direction ; KPI définis |
| 10 | [Roadmap](docs/10-roadmap.md) | MVP → V1 → V2 → V3 → V4, phases et lots de développement |

## Principes directeurs

1. **Simplicité pour la PME** : une question claire, une action à la fois, mobile d'abord.
2. **Puissance pour GUDE-PME** : pilotage de portefeuille, analyse transversale, configuration sans code.
3. **L'IA propose, l'humain dispose** : toute conclusion critique est validable, modifiable et traçable.
4. **Pas de preuve, pas de conformité** : un document déposé n'est jamais synonyme de conformité.
5. **Tout score est explicable** : formule, données, source, niveau de confiance.
6. **Aucune règle réglementaire codée en dur** : registre sourcé, daté, versionné, administrable.
7. **Multi-tenant par conception** : chaque organisation a ses référentiels, ses PME, ses workflows.
