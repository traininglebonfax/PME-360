# Document 10 — Roadmap : MVP → V1 → V2 → V3 → V4

## 1. Définition du MVP

**Objectif** : permettre à **un conseiller** de réaliser le parcours complet (Document 1, § 4) sur un **pilote de 20 à 30 PME réelles**, avec des résultats fiables, traçables et présentables à la direction.

| # | Fonction MVP | Périmètre MVP | Reporté |
|---|---|---|---|
| 1 | Création PME | Fiche 360° (identité, dirigeants, activité, chiffres clés), détection de doublons, assignation d'un conseiller | Import en masse (V1) |
| 2 | Questionnaire diagnostic | Référentiel GUDE-360 v1 (12 dimensions), questionnaire adaptatif, sauvegarde automatique, saisie conseiller | Éditeur visuel du référentiel (V1) : en MVP, le référentiel est chargé par seed ou admin technique |
| 3 | Upload de documents | Pipeline sécurisé (antivirus, MIME, taille), versions, dossier par catégorie, mobile | Dépôt par e-mail ou WhatsApp (V2) |
| 4 | Analyse IA | Classification + extraction pour **6 types** : RCCM, DFE, états financiers SYSCOHADA, justificatif CNPS, attestation fiscale, attestation d'assurance ; contrôles déterministes ; file de revue humaine | Autres types, vision avancée (V2) |
| 5 | Scoring | Moteur complet (critères, dimensions, IMO/IPE, lentilles, confiance, niveaux et portes, explication des écarts) | Calibration sectorielle (V3) |
| 6 | Diagnostic | Pré-diagnostic IA par critère + revue humaine + snapshot | — |
| 7 | Plan d'accompagnement | Règles (JSON Logic, ~30 règles de seed), catalogue de 12 offres, matrice de priorisation, plan 90 j / 6 m / 12 m | Constructeur visuel de règles (V1) |
| 8 | Gestion des actions | Workflow d'action par défaut, dépendances, livrables, commentaires | Workflows configurables par l'UI (V1) |
| 9 | Échéances | Obligations récurrentes (CNPS **après vérification** de REG-CNPS-01, états financiers annuels, attestations), générateur, relances | Obligations fiscales périodiques (après vérification de REG-FISC-02) |
| 10 | Dashboard PME | Complet (Document 9, § 2) | — |
| 11 | Dashboard GUDE-PME | Conseiller + vue d'ensemble programme (KPI § 4.1) + 3 analyses : problèmes fréquents, PME à intervention urgente, progression / stagnation | Autres analyses, carte (V1) |
| 12 | Rapport PDF | Rapport de diagnostic PME | Rapport trimestriel de portefeuille (V1) |
| 13 | Notifications | In-app + e-mail, modèles, préférences simples | SMS / WhatsApp (V2) |
| 14 | Audit trail | Journal chaîné, traçabilité IA, revues humaines | Tableau de bord auditeur (V1) |

**Inclus dès le MVP (non négociable)** : multi-tenant avec RLS, RBAC + périmètre, MFA pour GUDE, chiffrement, sauvegardes testées, seed de démonstration (6 PME fictives), tests unitaires, d'intégration et E2E du parcours critique.

## 2. Phases de développement du MVP

Hypothèse d'équipe : 1 product owner (GUDE-PME), 1 designer UX (temps partiel), 2 développeurs backend (Python), 1 développeur frontend, 1 ingénieur IA / données, 1 expert métier (finance / conformité) à temps partiel. Durées en semaines, indicatives.

| Phase | Contenu | Durée | Critères de sortie |
|---|---|---|---|
| **0 — Analyse** | Les 10 documents du dossier `docs/` ; validation des décisions ouvertes ; maquettes des écrans clés | 2–3 sem. | Documents validés ; décisions D-01 à D-06 tranchées ; maquettes validées par 3 PME tests et 2 conseillers |
| **1 — Socle** | Squelette du dépôt, CI, Docker, tenancy + RLS, auth (MFA, OTP), utilisateurs, rôles, périmètres, organisations et programmes, CRUD PME + fiche d'identité, journal d'audit, squelette des dashboards, seed | 4 sem. | Tests d'isolation inter-tenants au vert ; PME créée et assignée ; audit visible |
| **2 — Diagnostic** | Référentiel versionné (modèle + seed GUDE-360 v1), questionnaire adaptatif, réponses, revue par critère, moteur de scoring, snapshots, Health Check, explication des écarts | 5 sem. | Le score de la seed est reproductible à l'identique ; couverture du moteur ≥ 90 % ; parcours questionnaire → score démontrable |
| **3 — Documents** | Stockage objet, pipeline (antivirus, MIME, OCR), versions, dossier de conformité, statuts multi-axes, obligations, générateur d'échéances, relances, notifications e-mail | 4 sem. | Fichier infecté (EICAR) bloqué ; échéances idempotentes ; relances J-30 à J+15 testées |
| **4 — IA** | Passerelle IA, prompts versionnés, classification et extraction des 6 types, contrôles et anomalies, calcul de confiance, file de revue humaine, calcul des indicateurs financiers, pré-diagnostic, traçabilité, jeu d'évaluation | 5 sem. | Seuils d'évaluation atteints (Document 4, § 12) sur le jeu de test ; aucune donnée d'un autre tenant récupérable (test RAG) |
| **5 — Accompagnement** | Moteur de règles, catalogue d'offres, recommandations, priorisation, génération du plan, actions, dépendances, livrables, bibliothèque de modèles, workflow d'action, mise à jour du score à la vérification | 4 sem. | Parcours complet sur la seed : de la faiblesse détectée au score mis à jour après preuve vérifiée |
| **6 — Reporting** | Dashboards PME, conseiller et programme, 3 analyses de portefeuille, rapport PDF de diagnostic, vues matérialisées | 4 sem. | Rapport PDF des 16 sections généré pour les 6 PME de la seed ; KPI vérifiés à la main sur la seed |
| **Pilote** | Durcissement, test d'intrusion, formation, pilote avec 20 à 30 PME réelles et 3 à 5 conseillers | 6–8 sem. | Au moins 80 % des diagnostics pilotes validés ; temps moyen de diagnostic mesuré ; au moins 70 % des extractions acceptées sans correction ; retours utilisateurs traités |

**Total estimé jusqu'à la fin du pilote : environ 8 à 9 mois.**

Chaque phase se termine par une démonstration sur la seed et une mise à jour de la documentation et des ADR.

## 3. Versions suivantes

### V1 — Généralisation (diagnostic + scoring + documents + accompagnement)
- Administration **sans code** : éditeur du référentiel (dimensions, critères, questions, poids), constructeur visuel de règles avec test, éditeur de workflows, types de documents, obligations, modèles de notifications.
- Import en masse des PME (CSV) ; gestion des cohortes.
- Rapport trimestriel de portefeuille ; toutes les analyses du Document 9, § 4.2 ; carte régionale.
- Obligations fiscales périodiques (une fois REG-FISC-02 vérifiée).
- Tableau de bord auditeur ; rôles personnalisés.
- Clé de chiffrement par tenant.

### V2 — IA avancée, analyse financière et automatisation
- Extraction étendue (contrats, procédures avec critères de contrôle, relevés synthétiques, balances âgées).
- **Ask AI** complet (PME et portefeuille) avec outils et citations.
- Analyse financière multi-exercices : tendances, alertes de dégradation, prévisionnel vs réalisé.
- Rédaction assistée de tous les rapports.
- Canaux WhatsApp / SMS (selon les fournisseurs disponibles localement et le consentement).
- Contrôle automatique des livrables selon leurs critères de vérification.
- Assistant PME restreint (explication des actions et du « comment faire »).

### V3 — BI, prédiction des risques, benchmarking
- Entrepôt analytique séparé (réplica + modèle en étoile) et tableaux de bord libres pour la direction.
- **Calibration sectorielle** des bandes de ratios à partir du portefeuille.
- Modèle de **prédiction de risque** (dégradation, décrochage, abandon), explicable et validé humainement, sans décision automatique.
- Benchmarking anonymisé (n ≥ 5 par cellule) : secteur, région, taille.
- Méthodologie d'impact outillée (cohortes de comparaison, différence de différences).
- Option de modèle d'IA auto-hébergé pour les tenants exigeant une souveraineté totale.

### V4 — Écosystème partenaires, financement et opportunités
- Onboarding d'autres organisations (banques, bailleurs, incubateurs) en multi-tenant.
- **Partage de dossier avec consentement de la PME** (« passeport PME ») entre organisations.
- Place de marché d'opportunités : appels à projets, marchés, programmes de financement, avec mise en relation fondée sur le profil et le niveau de maturité.
- API partenaires (OAuth2) et webhooks.
- Intégrations éventuelles avec des services publics, **si et seulement si** des API officielles et des accords existent.

## 4. Risques projet et mesures

| Risque | Probabilité | Impact | Mesure |
|---|---|---|---|
| Règles réglementaires inexactes | Moyenne | Élevé | Registre sourcé, statut VÉRIFIÉ obligatoire, revue par un juriste ou un expert-comptable avant le pilote |
| Faible adoption par les PME (effort, confiance) | Élevée | Élevé | Mobile d'abord, 3 actions visibles au maximum, accompagnement en présentiel au démarrage, valeur immédiate (rapport gratuit) |
| Qualité des scans (photos, papier) | Élevée | Moyen | Guide de prise de photo, contrôle de lisibilité à l'upload, OCR + repli vision, revue humaine |
| Hébergement ou transfert de données non conforme | Moyenne | Élevé | Décisions D-02 et D-03 tranchées avant le pilote, formalités auprès de l'autorité de protection |
| Charge des conseillers (file de vérification) | Moyenne | Moyen | Seuils de confiance ajustés, validation en lot, mesure du temps de revue |
| Dérive du périmètre | Élevée | Moyen | MVP figé ; toute nouveauté passe par la roadmap |
| Dépendance au fournisseur d'IA | Faible | Moyen | Passerelle abstraite, mode dégradé local |
| Connectivité limitée | Moyenne | Moyen | Pages légères, reprise d'upload, résumé des notifications par e-mail |

## 5. Indicateurs de succès du produit

| Indicateur | Cible à la fin du pilote |
|---|---|
| Temps de réalisation d'un diagnostic complet (conseiller) | ≤ 3 h (hors entretien), contre plusieurs jours aujourd'hui (à mesurer) |
| Part des PME ayant déposé ≥ 80 % des documents demandés | ≥ 60 % |
| Extractions IA acceptées sans correction | ≥ 70 % (≥ 90 % en V2) |
| Actions du plan 90 jours terminées à J+90 | ≥ 50 % |
| Satisfaction des PME (échelle de 1 à 5) | ≥ 4 |
| Rapports de portefeuille produits sans retraitement manuel | 100 % |
