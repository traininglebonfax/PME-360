# Document 1 — Architecture fonctionnelle

## 1. Analyse du besoin

GUDE-PME accompagne un portefeuille de PME, qui peut aller jusqu'à plusieurs milliers. Aujourd'hui, l'organisation mesure surtout **l'activité** (« nous avons accompagné 500 PME »). Le produit doit lui permettre de mesurer **l'état et la trajectoire** du portefeuille : situation réelle, difficultés, maturité, actions réalisées, progrès, besoins non couverts et priorités.

Le besoin se ramène à cinq problèmes à résoudre :

| Problème | Conséquence actuelle | Réponse produit |
|---|---|---|
| Information dispersée (papier, e-mails, WhatsApp, Excel) | Pas de vue fiable sur une PME ni sur le portefeuille | Fiche PME 360° et dossier de conformité numérique |
| Diagnostics hétérogènes selon les conseillers | Scores non comparables | Référentiel versionné, grilles de notation ancrées, moteur de scoring unique |
| Preuves rarement vérifiées | Conformité supposée, pas démontrée | Cycle de vie documentaire multi-statuts, vérification IA + humaine |
| Plans d'action génériques et mal suivis | Faible exécution, peu de mesure | Recommandations issues de règles, plan 90 j / 6 m / 12 m, actions liées aux preuves |
| Reporting manuel et peu analytique | Pilotage à l'intuition | Tableaux de bord de portefeuille, analyses transversales, rapports générés |

## 2. Acteurs et personas

> Personas fictifs, destinés à guider la conception.

| Persona | Rôle système | Contexte | Besoin principal | Contraintes UX |
|---|---|---|---|---|
| **Aya K.**, gérante d'une PME de distribution (8 salariés, Abidjan) | `DIRIGEANT_PME` | Peu de temps, utilise surtout son smartphone et WhatsApp | Savoir quoi faire, pourquoi et avant quand | Mobile d'abord, vocabulaire simple, peu de saisie, dépôt photo |
| **Moussa D.**, comptable externe ou salarié d'une PME | `COLLABORATEUR_PME` | Dépose les documents financiers et fiscaux | Dépôt rapide et retour clair sur ce qui est refusé | Dépôt en masse, motifs de rejet précis |
| **Konan B.**, conseiller GUDE-PME (suit 20 à 40 PME) | `CONSEILLER` | Mène les diagnostics, vérifie les preuves, suit les plans | Gagner du temps de saisie et d'analyse, prioriser son portefeuille | File de travail unique, raccourcis, validations en lot |
| **Dr Awa T.**, experte finance ou juridique | `EXPERT` | Intervient ponctuellement sur des dossiers complexes | Analyser vite, valider ou corriger l'IA | Vue « preuve ↔ donnée extraite » côte à côte |
| **Responsable programme** | `RESPONSABLE_PROGRAMME` | Pilote une cohorte ou un programme | Suivre l'avancement, les retards, les besoins par secteur ou région | Tableaux de bord, exports |
| **Direction GUDE-PME** | `ADMIN_ORG` | Rend compte à la tutelle et aux bailleurs | Indicateurs d'impact fiables et explicables | Synthèses, rapports trimestriels ou annuels |
| **Auditeur / bailleur** | `AUDITEUR` | Contrôle a posteriori | Lecture seule, traçabilité complète | Accès restreint, journal d'audit |
| **Administrateur plateforme** | `SUPER_ADMIN` | Exploitation technique multi-organisations | Créer des tenants, superviser | Pas d'accès aux contenus métier par défaut (accès « bris de glace » journalisé) |

## 3. Les 5 niveaux fonctionnels

```
N1 CONNAÎTRE     → Fiche PME 360° (identité, activité, dirigeants, marchés, chiffres clés)
N2 DIAGNOSTIQUER → Questionnaire adaptatif + preuves documentaires + analyse IA
N3 SCORER        → Maturité / Performance / Conformité / Risque + confiance
N4 ACCOMPAGNER   → Recommandations → plan 90 j / 6 m / 12 m → actions → livrables → preuves
N5 MESURER       → Snapshots comparables, explication des écarts, indicateurs d'impact
```

## 4. Parcours de référence (critère de réussite)

```
CRÉER PME → QUESTIONNAIRE → IMPORT DOCUMENTS → ANALYSE IA → DIAGNOSTIC 360° → SCORE
→ PRIORITÉS → PLAN D'ACCOMPAGNEMENT → VALIDATION DU PLAN → ACTIONS → LIVRABLES
→ VÉRIFICATION → MISE À JOUR DU SCORE → REPORTING → RÉÉVALUATION
```

| Étape | Acteur principal | Écran / fonction | Sortie | Contrôle |
|---|---|---|---|---|
| 1. Inscription PME | Conseiller (ou PME via invitation) | Assistant de création en 3 étapes | PME au statut `PROSPECT` puis `ONBOARDING` | Détection de doublons (RCCM, NCC, raison sociale approchante) |
| 2. Questionnaire initial | PME + conseiller | Questionnaire adaptatif par dimension, sauvegarde automatique | Réponses déclaratives | Questions filtrées selon secteur, taille, régime, effectif |
| 3. Import documentaire | PME | Checklist « documents demandés » générée par le profil | Documents `REÇU` | Scan antivirus, format, taille |
| 4. Analyse IA | Système | File de traitement | Type détecté, données extraites, anomalies | Confiance < seuil → vérification humaine |
| 5. Diagnostic humain + IA | Conseiller / expert | Écran de revue par dimension | Niveaux validés, commentaires | Chaque modification de l'IA est justifiée |
| 6. Score initial | Système | Health Check | Snapshot `BASELINE` figé | Calcul reproductible (version du référentiel) |
| 7. Plan d'accompagnement | Système → conseiller | Proposition de plan (moteur de règles + IA) | Plan `BROUILLON` | Matrice de priorisation modifiable |
| 8. Validation du plan | Conseiller + dirigeant PME | Revue, signature électronique simple (acceptation horodatée) | Plan `VALIDÉ` | Double validation GUDE et PME |
| 9. Exécution | PME / GUDE / prestataires | Tableau de bord des actions | Actions en cours | Relances automatiques |
| 10. Dépôt des livrables | PME | Bouton « Déposer la preuve » sur l'action | Document lié à l'action | Pipeline documentaire |
| 11. Contrôle | IA + conseiller | File de vérification | `CONFORME` / `NON CONFORME` + motif | Motif obligatoire en cas de rejet |
| 12. Mise à jour du score | Système | Recalcul incrémental | Score courant + explication de l'écart | Seules les preuves vérifiées modifient les critères de conformité |
| 13. Reporting | Système | Rapports PDF, dashboards | Rapport PME et rapports consolidés | Données figées à la date d'édition |
| 14. Réévaluation | Conseiller | Nouveau diagnostic pré-rempli | Snapshot `FOLLOW_UP` (6 m, 12 m) | Comparaison avec le snapshot de référence |

## 5. Cartographie des modules

| Module | Responsabilité | Niveau |
|---|---|---|
| **Authentication** | Connexion, MFA, OTP e-mail/SMS pour la PME, sessions, réinitialisation | Socle |
| **Users** | Comptes, profils, invitations, rattachement aux organisations et aux PME | Socle |
| **Organizations** | Tenants, programmes, cohortes, branding, paramètres | Socle |
| **PMEs** | Fiche 360°, dirigeants, établissements, chiffres clés par exercice, statut de cycle de vie | N1 |
| **Diagnostic** | Référentiel (dimensions, critères, questions), campagnes, sessions, réponses, revue | N2 |
| **Scoring** | Calcul des indices, niveaux, confiance, snapshots, explication des écarts | N3 |
| **Documents** | Upload, stockage, versions, pipeline, visionneuse, dossier de conformité | N2/N4 |
| **Compliance** | Obligations, échéances récurrentes, statuts de conformité, registre réglementaire | N2/N4 |
| **Recommendations** | Moteur de règles, catalogue d'offres d'accompagnement | N4 |
| **Action Plans** | Plans, jalons (90 j / 6 m / 12 m), roadmap | N4 |
| **Tasks** | Actions, sous-actions, dépendances, affectations, commentaires | N4 |
| **Templates** | Bibliothèque de modèles de livrables | N4 |
| **Workflows** | Machines à états configurables, déclencheurs, enchaînements | Transverse |
| **AI** | Passerelle LLM, extraction, anomalies, Copilot, RAG, traçabilité IA | Transverse |
| **Alerts** | Règles d'alerte, détection, cycle de vie des alertes | Transverse |
| **Notifications** | Canaux (in-app, e-mail, puis WhatsApp/SMS), préférences, calendrier de relances | Transverse |
| **Reports** | Rapports PDF (PME, suivi, conformité, portefeuille), exports | N5 |
| **Dashboards** | Vues PME, conseiller, programme, direction ; analyses de portefeuille | N5 |
| **Audit Logs** | Journal inaltérable des actions et des accès | Transverse |
| **Settings** | Configuration sans code (référentiels, pondérations, règles, périodicités) | Transverse |

## 6. Rôles et droits (RBAC + périmètre)

Le contrôle d'accès combine :
- **un rôle** (ce que l'on peut faire) ;
- **un périmètre** (sur quelles PME) : `ORG` (toute l'organisation), `PROGRAMME`, `PORTEFEUILLE` (PME assignées) ou `PME` (sa propre entreprise).

| Permission ↓ / Rôle → | SUPER_ADMIN | ADMIN_ORG | RESP_PROG | CONSEILLER | EXPERT | DIRIGEANT_PME | COLLAB_PME | AUDITEUR |
|---|---|---|---|---|---|---|---|---|
| Gérer les tenants | ✅ | — | — | — | — | — | — | — |
| Configurer les référentiels, règles et pondérations | — | ✅ | 🔸 proposer | — | — | — | — | — |
| Gérer les utilisateurs de l'organisation | — | ✅ | 🔸 son programme | — | — | 🔸 collaborateurs PME | — | — |
| Créer / éditer une PME | — | ✅ | ✅ | ✅ portefeuille | — | 🔸 fiche identité | — | — |
| Répondre au questionnaire | — | — | — | ✅ | ✅ | ✅ | ✅ | — |
| Valider un diagnostic / figer un score | — | ✅ | ✅ | ✅ portefeuille | ✅ dimension d'expertise | — | — | — |
| Déposer un document | — | — | — | ✅ | ✅ | ✅ | ✅ | — |
| Vérifier / rejeter un document | — | ✅ | ✅ | ✅ portefeuille | ✅ | — | — | — |
| Modifier un résultat de l'IA | — | ✅ | ✅ | ✅ | ✅ | — | — | — |
| Créer ou modifier un plan d'action | — | ✅ | ✅ | ✅ | 🔸 proposer | 🔸 commenter / accepter | — | — |
| Mettre à jour le statut d'une action | — | ✅ | ✅ | ✅ | ✅ | ✅ actions PME | ✅ actions assignées | — |
| Voir les dashboards de portefeuille | — | ✅ | ✅ programme | ✅ portefeuille | — | — | — | ✅ lecture |
| Générer des rapports | — | ✅ | ✅ | ✅ | ✅ | ✅ rapport PME | — | ✅ lecture |
| Consulter le journal d'audit | 🔸 technique | ✅ | — | — | — | — | — | ✅ |
| Utiliser Ask AI | — | ✅ | ✅ | ✅ | ✅ | ⏳ V2 (assistant PME restreint) | — | — |

✅ autorisé · 🔸 autorisé avec restriction · — interdit · ⏳ version ultérieure

Les rôles sont des **données** (table `role` et table `permission`) et non des constantes dans le code. Une organisation peut créer des rôles personnalisés à partir des permissions atomiques (V1).

## 7. Cycle de vie de la PME

```
PROSPECT → ONBOARDING → DIAGNOSTIC_EN_COURS → ACCOMPAGNEMENT_ACTIF ⇄ SUSPENDU
                                                       ↓
                                            SORTIE (diplômée / abandon / réorientation)
                                                       ↓
                                               SUIVI_POST_PROGRAMME (alumni)
```

Une PME est considérée **inactive** si aucun événement significatif (connexion, dépôt, changement de statut d'une action) n'a eu lieu depuis N jours (paramètre, 60 par défaut).

## 8. Règles métier structurantes

1. **RM-01 : pas de conformité sans vérification.** Un critère de conformité ne dépasse pas le niveau plafond « déclaratif » (niveau 2/4 par défaut) sans preuve au statut `VÉRIFIÉ`.
2. **RM-02 : séparation maturité / performance.** Le score de maturité (organisation, pratiques, conformité) et l'indice de performance (résultats économiques) sont calculés et affichés séparément.
3. **RM-03 : confiance obligatoire.** Tout score affiché est accompagné de son indice de confiance et de la liste des sources utilisées.
4. **RM-04 : snapshots immuables.** Un diagnostic validé produit un snapshot figé, lié à la version du référentiel. Les comparaisons dans le temps se font entre snapshots.
5. **RM-05 : human-in-the-loop.** Les décisions critiques (conformité confirmée, validation d'un score, clôture d'une action critique, exclusion d'une PME) exigent une validation humaine.
6. **RM-06 : toute modification humaine d'un résultat IA est justifiée** (motif obligatoire) et journalisée.
7. **RM-07 : priorités modifiables.** La priorité calculée est une proposition. Une surcharge manuelle exige une justification et reste visible.
8. **RM-08 : registre réglementaire sourcé.** Une obligation réglementaire ne peut être activée que si elle porte une source officielle, une date de vérification et un vérificateur.
9. **RM-09 : pas d'attribution causale automatique.** Les tableaux d'impact présentent des évolutions et des corrélations. L'attribution à l'accompagnement exige une méthodologie explicite (cf. Document 9, § Impact).
10. **RM-10 : minimisation.** On ne collecte que les données personnelles nécessaires (dirigeants, contacts) ; les données salariales nominatives ne sont pas demandées, seuls des agrégats le sont.

## 9. Fiche PME 360° : structure des onglets

| Onglet | Contenu principal | Source |
|---|---|---|
| Synthèse | Health Check, top 5 priorités, alertes, prochaines échéances | Calculé |
| Identité | Raison sociale, sigle, forme juridique, RCCM, NCC (compte contribuable), n° CNPS employeur, date de création, adresse, région, commune, contacts | Déclaratif + extraction RCCM/DFE |
| Dirigeants & gouvernance | Dirigeants, associés, répartition du capital, organes | Déclaratif + statuts |
| Activité | Secteur (nomenclature configurable), produits/services, marchés, clients et fournisseurs principaux (agrégés) | Déclaratif |
| Finance | Chiffres clés par exercice, ratios avec formule et source, tendances | Extraction des états financiers |
| Fiscalité | Régime d'imposition, obligations, statuts | Registre + preuves |
| Social / RH | Effectif, périodicité CNPS, statuts des obligations, pratiques RH | Déclaratif + preuves |
| Organisation, Commercial, Opérations, Digital, Risques | Réponses, niveaux et preuves par dimension | Diagnostic |
| Documents | Dossier de conformité par catégorie, versions, statuts | Documents |
| Diagnostics & scores | Historique des snapshots, comparaison, explication des écarts | Scoring |
| Plan & actions | Roadmap, Kanban, retards | Action plans |
| Historique | Timeline unifiée (événements métier) | Audit + événements |
| Rapports | Rapports générés et archivés | Reports |

## 10. Portail PME : principes UX

L'écran d'accueil de la PME répond à 4 questions et rien d'autre :

1. **Où j'en suis ?** : jauge de score, niveau de maturité, progression depuis le départ.
2. **Que dois-je faire maintenant ?** : 3 prochaines actions au maximum, chacune avec *pourquoi*, *comment* (modèle téléchargeable, tutoriel), *quel document* et *avant quand*.
3. **Qu'est-ce qui a été validé ou refusé ?** : liste des retours avec le motif en langage simple.
4. **Mes prochaines échéances** : calendrier des obligations périodiques.

Règles UX : un bouton principal par écran ; dépôt par photo depuis le mobile ; libellés sans jargon (glossaire contextuel) ; fonctionnement correct en connexion 3G (pages légères, reprise des uploads interrompus).

## 11. Portail conseiller : principes UX

- **« Ma journée »** : file de travail unique triée par urgence (documents à vérifier, actions en retard, alertes, diagnostics à valider).
- **Portefeuille** : liste des PME avec score, tendance, conformité, alertes et filtres (secteur, région, niveau, priorité).
- **Écran de revue** : document à gauche, données extraites et contrôles à droite ; actions Valider / Corriger / Rejeter avec motif.
- **Ask AI** accessible depuis chaque PME et depuis le portefeuille.

## 12. Configuration sans code (§ 44 du cahier des charges)

Le code contient des **moteurs** (scoring, règles, workflow, échéances, pipeline documentaire) ; les **règles métier** sont des données administrables, versionnées et journalisées.

| Paramètre | Stockage | MVP | V1 |
|---|---|---|---|
| Dimensions, critères, questions, pondérations, grilles de notation | Référentiel versionné (`framework_version`, Document 3, § 3.3) | Chargé par seed ou par l'administrateur technique | Éditeur visuel du référentiel |
| Niveaux de maturité et portes de passage | `framework_version.maturity_levels` | Seed | Éditeur |
| Formules et bandes des indicateurs financiers | `metric_definition` | Seed | Éditeur |
| Types et catégories de documents, règles de validité | `document_type`, `document_category` | Administration | Interface d'administration complète |
| Obligations, périodicités, décalages de relance | `obligation_template` | Administration | Interface d'administration complète |
| Registre réglementaire (sources, vérification) | `regulatory_rule` | ✅ Interface ADMIN_ORG | — |
| Règles de recommandation, de priorité, d'alerte et de workflow | `rule`, `alert_rule` (JSON Logic) | JSON édité par ADMIN_ORG + bouton « Tester » | Constructeur visuel |
| États et transitions des workflows | `workflow_definition` | Workflows par défaut | Éditeur de workflows |
| Catalogue d'offres et modèles de livrables | `support_offer`, `deliverable_template` | ✅ Interface ADMIN_ORG | — |
| Modèles de notification | `notification_template` | Seed | Éditeur |
| Seuils de confiance IA, IA externe autorisée, types sensibles | `organization.settings`, `document_type.sensitive` | ✅ Interface ADMIN_ORG | — |
| Rôles personnalisés | `role`, `role_permission` | Rôles système | Rôles personnalisés |

Toute modification d'un objet publié crée une nouvelle version ; les diagnostics, recommandations et échéances déjà produits conservent la version qui les a générés.

## 13. Hors périmètre (explicite)

- Tenue de comptabilité ou production des états financiers de la PME (la plateforme **analyse**, elle ne **tient** pas la comptabilité).
- Télédéclaration fiscale ou CNPS pour le compte de la PME.
- Décision d'octroi de financement (la plateforme peut préparer un dossier, pas décider).
- Certification officielle de conformité : la plateforme atteste d'une **vérification documentaire par GUDE-PME** à une date donnée, pas d'une conformité légale opposable aux administrations.
