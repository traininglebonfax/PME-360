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
| 2 — Diagnostic | ✅ Livrée (voir ci-dessous) ; référentiel GUDE-360 v1 **à valider en atelier** (D-04) |
| 3 — Documents & conformité | ✅ Livrée (voir ci-dessous) ; règles réglementaires CNPS / fiscales / états financiers **à vérifier** avant activation (RM-08) |
| 4 — IA | ✅ Livrée (voir ci-dessous) ; moteur local par défaut, Claude activable par organisation ; jeu d'évaluation **synthétique** à compléter par des documents réels anonymisés |
| 5 — Accompagnement | ✅ Livrée (voir ci-dessous) ; catalogue d'offres, règles et modèles de livrables **à valider** par GUDE-PME |
| 6 — Reporting | ✅ Livrée (voir ci-dessous) ; rapport PDF à relire par GUDE-PME ; analyse d'effet des accompagnements descriptive uniquement (RM-09) |
| V1 — en cours | ✅ Import en masse des PME par CSV ; ✅ rapport trimestriel de portefeuille (PDF, anonymisé par défaut) ; ✅ administration des types de documents et des obligations ; ✅ modèles de notification ; ✅ éditeur de référentiel ; ✅ éditeur de workflows ; ✅ tableau de bord auditeur et rôles personnalisés ; ✅ livrables non fournis et carte régionale ; ✅ clé de chiffrement par organisation ; ✅ marque blanche et démo au nom d'un prospect ; ✅ rapports de suivi, annuel et de conformité d'une PME |
| Compléments MVP | ✅ Échanges sur les actions (internes ou partagés), sauvegardes chiffrées avec test de restauration ([runbook](infra/backup/README.md)) |

### V1 — généralisation (en cours)

- **Import en masse des PME (CSV)** : modèle téléchargeable ; séparateur `;` ou `,`, fichiers UTF-8 ou Excel Windows, dates JJ/MM/AAAA ; secteur, région et forme juridique par code ou libellé ; dirigeant, conseiller (par e-mail) et cohorte. L'**aperçu ne crée rien** : chaque ligne passe par les règles de la saisie manuelle et par la détection de doublons (base et fichier). L'import crée les lignes valides ; les doublons de RCCM ou NCC sont toujours écartés, les raisons sociales proches seulement sur confirmation ; bilan ligne par ligne, tracé au journal. 2 000 lignes par fichier.
- **Rapport trimestriel de portefeuille** (Document 9, § 7) : PDF en 11 sections (synthèse, activité du trimestre, évolution des scores, principaux problèmes, besoins, actions réalisées ou en retard, progression par secteur et par région, conformité, accompagnement renforcé, **recommandations de pilotage** déduites des chiffres, méthodologie et définitions). Périmètre : organisation, programme ou cohorte, limité au portefeuille de l'utilisateur ; **anonymisé par défaut** (diffusable aux bailleurs), nominatif en option pour la direction ; évolutions présentées sans attribution causale (RM-09), cellules masquées sous 5 PME, part de données vérifiées affichée. Données figées et versionnées ; édition automatique anonymisée le 1er jour de chaque trimestre ; lisible seulement par qui voit toutes les PME du rapport.
- **Administration sans code des types de documents et des obligations** (Conformité → onglets « Types de documents » et « Obligations ») : création et modification des types (catégorie, période couverte, validité, fraîcheur, niveau prouvé, données personnelles, consigne), avec leur usage (documents déposés, obligations, critères du référentiel publié) ; un code est définitif et un type exigé par une obligation active ne peut pas être désactivé. Obligations créées **inactives**, avec constructeur visuel « à qui elle s'applique » (effectif, taille, secteur, statut, société — clauses ET) et « périodicité selon l'effectif », repli JSON Logic pour les règles avancées ; les règles sont affichées en français dans la liste. Une obligation réglementaire exige une règle du registre, et reste inactivable tant qu'elle n'est pas vérifiée (RM-08). Les modifications valent pour les prochaines échéances ; tout est tracé au journal d'audit.
- **Modèles de notification** (menu « Modèles de notification ») : objet et texte de chacun des 17 messages, modifiables par l'organisation ; variables propres à chaque événement insérables d'un clic, contrôle en direct (variable inconnue, accolade isolée), aperçu application et e-mail avec des valeurs d'exemple, e-mail de test envoyé à l'administrateur, retour au texte par défaut. Rendu par simple substitution de `{variable}` (aucun accès aux attributs Python) ; un modèle invalide en base retombe sur le texte par défaut ; modifications tracées au journal d'audit.
- **Éditeur de référentiel sans code** (Référentiel → brouillon) : sur un brouillon cloné d'une version, modification des poids des piliers, dimensions et critères directement dans les tableaux, avec **équilibre des poids affiché en direct** (✓ 100 / 100 ou ⚠ 95 / 100) ; création, modification et suppression de dimensions, critères (lentille, grille des niveaux 0 à 4, preuves attendues, plafond déclaratif, module sectoriel, applicabilité via le constructeur visuel) et questions (réponses et niveau atteint, public, aide, « pourquoi », condition d'affichage). L'état de publication (anomalies bloquantes, avertissements — par exemple un critère supprimé encore visé par une offre ou une règle d'accompagnement) est recalculé à chaque modification ; la publication reste refusée tant qu'une anomalie subsiste. Codes non modifiables, questions alimentant le moteur protégées, version publiée immuable, brouillon supprimable, chaque modification tracée au journal d'audit. Les formules des indicateurs calculés restent en lecture seule.
- **Éditeur de workflows** (menu « Workflows ») : pour les actions du plan d'accompagnement, libellés des états côté équipe et côté PME, passages manuels autorisés, qui peut les déclencher (GUDE-PME, PME), motif obligatoire et libellé des boutons. Brouillon contrôlé en direct puis activé (versions conservées) ; le moteur applique la version active (`pme360/workflows`), et les écrans des actions affichent ses libellés et boutons. Garde-fous : états et passages automatiques (dépôt, analyse, vérification, déblocage) non modifiables, abandon avec motif toujours possible pour GUDE-PME, la PME ne peut que démarrer/reprendre ou signaler qu'elle attend son conseiller, pas de sortie d'un état final, une action doit toujours pouvoir être terminée, fin conditionnée à des livrables conformes. Audit de chaque modification.
- **Rôles personnalisés** (Utilisateurs → « Rôles et permissions ») : l'organisation compose ses rôles d'équipe à partir des permissions atomiques, en partant d'une page blanche ou d'un rôle système ; périmètre par défaut (organisation, programme, portefeuille — un rôle « portefeuille » peut suivre des PME). Garde-fous : rôles système et rôles du portail PME non modifiables, pas d'élévation de privilèges (on n'accorde que ce que l'on détient), pas de retrait de sa propre gestion des utilisateurs, rôle attribué non supprimable ; changements immédiats pour les détenteurs, tracés au journal.
- **Tableau de bord auditeur** (menu « Tableau de bord auditeur », permission `audit.view`, lecture seule) : activité du journal par domaine et par type d'acteur sur la période, échecs de connexion, vérification de l'intégrité de la chaîne, événements sensibles (accès, rôles, publications, exports, fichiers bloqués), revue humaine des propositions de l'IA par dimension (acceptées, modifiées, écartées, taux de modification) et des lectures de documents, échantillonnage reproductible de dossiers PME (graine), export CSV du journal (aussi depuis le journal). Tirages et exports sont eux-mêmes journalisés. Compte de démonstration : `auditeur@demo.test`.
- **Livrables non fournis** (Analyses) : pour les livrables d'action, taux de non-fourniture (aucun dépôt 30 jours après le passage à « Document demandé ») et délai moyen entre la demande et le premier dépôt ; pour les documents d'obligation, échéances échues sans document, dépôts en retard et retard moyen. Par type, avec effectifs ; effectif < 5 signalé.
- **Carte des régions** (Analyses) : choroplèthe des 31 régions et 2 districts autonomes — nombre de PME, score moyen, part à risque —, moyennes masquées sous 5 PME évaluées (hachures), info-bulle, vue tableau. Fond de carte précalculé par `infra/geo/build_civ_regions.py` depuis geoBoundaries (CIV ADM2, Banque mondiale 2016, CC BY 4.0, attribution affichée).
- **Clé de chiffrement par organisation** (chiffrement enveloppe) : chaque document et rapport est chiffré en AES-256-GCM avant d'être stocké, avec une clé propre à l'organisation ; cette clé est conservée en base **enveloppée** par la clé maîtresse de la plateforme (`PME360_STORAGE_MASTER_KEYS`, hors base). Le chemin du fichier est lié au chiffré : un fichier déplacé (autre PME, autre organisation) ou modifié est refusé. Rotation de la clé d'une organisation depuis le tableau de bord auditeur (administrateur) ou `manage.py storage_keys rotate <slug>` : les anciens fichiers restent lisibles, `manage.py encrypt_storage --reencrypt` les passe sur la nouvelle clé. Fichiers antérieurs : relus tels quels, puis chiffrés par `manage.py encrypt_storage` (idempotent, contrôle avant remplacement). Rotation de la clé maîtresse : nouvelle clé en tête de liste puis `manage.py storage_keys rewrap` (aucun fichier à réécrire). **La clé maîtresse doit être sauvegardée à part** (coffre) : sans elle, les fichiers — sauvegardes comprises — sont illisibles.
- **Marque blanche** : le logiciel s'appelle **PME360** (identité neutre par défaut) ; chaque organisation affiche son nom de produit, son nom court (« Équipe … », « Mon conseiller … », « Interne … »), sa couleur principale (contraste contrôlé) et son logo, dans l'interface, la page de connexion (`/connexion?org=<identifiant>`), les rapports PDF et les e-mails. Réglage : menu « Identité de l'organisation » (administrateur). Pour GUDE-PME, rien ne change à l'écran (« GUDE-PME 360 », vert, « Diagnostic 360° GUDE-PME »). Sans `?org=`, la page de connexion reste neutre ; à la déconnexion, on revient à la page de connexion de son organisation.
- **Démo au nom d'un prospect** : `python manage.py create_demo_org --nom "Banque Atlantique" --couleur "#0055A4" [--logo logo.png] [--produit "…"]` crée en ~30 s une organisation distincte avec le scénario fictif complet (équipe, 6 PME, diagnostics, documents, plan, rapports) et des comptes `<compte>.<identifiant>@demo.test` (mot de passe et codes comme les autres comptes de démo) ; adresse : `http://localhost:3010/connexion?org=banque-atlantique`. Aucune donnée ni aucun nom de GUDE-PME n'y apparaît (vérifié par un test de bout en bout qui parcourt tous les écrans). Après la présentation : `python manage.py close_demo_org banque-atlantique` (organisation suspendue, comptes désactivés, fichiers et clés détruits).
- **Rapports de suivi, annuel et de conformité d'une PME** (Document 9, § 7 ; fiche PME → onglet « Rapports », bouton « Éditer un rapport ») : PDF à données figées, versionnés et archivés comme le rapport de diagnostic, téléchargeables par la PME, notifiés à la PME et au conseiller. **Suivi** (8 sections) : période depuis la fin du rapport de suivi précédent, sinon depuis la validation du dernier diagnostic (90 jours à défaut) ; score à date comparé au début de période et au diagnostic initial, par dimension ; **explication des écarts** par dimension et critère (progrès, recul, gain de preuve) ; actions terminées, en retard (avec la partie attendue), en cours ; progrès vérifiés ; conformité et échéances de la période ; alertes ; prochaines étapes. Édité **automatiquement le 1er jour de chaque trimestre** pour chaque PME dont le plan est validé ou en cours. **Annuel** (9 sections) : mêmes contenus sur 12 mois, avec la trajectoire des évaluations. **Conformité** (6 sections) : taux et décompte, ce qu'il reste à fournir (avec la consigne ou le motif de refus), dossier par catégorie, échéances en retard et à 90 jours, bilan sur 12 mois, documents expirant sous 60 jours, anomalies et documents refusés ; mention « ne vaut pas attestation de régularité ». Évolutions décrites sans attribution causale (RM-09). Réédition le même jour : nouvelle version sur la même période. Couleur de l'organisation reprise dans les nouveaux gabarits.

### Compléments du MVP

- **Échanges sur les actions** : chaque action a un fil de messages ; le conseiller choisit « interne GUDE-PME » (par défaut) ou « partagé avec la PME » ; la PME ne voit que les messages partagés et prévient son conseiller en écrivant. Messages en ajout seul, tracés au journal, notifiés à l'autre partie.
- **Sauvegardes** (Document 2) : archivage continu des WAL (restauration à un instant donné, RPO 15 min), sauvegarde quotidienne **chiffrée** (AES-256) avec manifeste d'intégrité, sauvegarde de base hebdomadaire, réplication continue des documents et rapports, rétention 30 jours, **test de restauration mensuel automatique** (volumes, dernier maillon d'audit, propriétaire applicatif et RLS forcée vérifiés ; rapport archivé), commande `verify_audit` après restauration. Procédures dans [infra/backup/README.md](infra/backup/README.md).

### Contenu de la phase 6

- **Vues analytiques** (Document 3, § 6) : `mv_pme_current_state`, `mv_portfolio_weaknesses`, `mv_score_trajectories`, rafraîchies après chaque fait métier (au plus toutes les 30 s) et toutes les 15 minutes. Une vue matérialisée ignorant la RLS, elles ne sont **jamais lues directement** : l'application passe par des vues filtrées (`v_*`, `security_barrier`) qui appliquent le prédicat de tenant, puis par le périmètre de l'utilisateur ; un test vérifie qu'aucun code ne lit une `mv_*`.
- **Tableaux de bord** (Document 9) : KPI de la vue d'ensemble selon leurs définitions exactes, avec **info-bulle de définition** et date de fraîcheur (PME accompagnées, en retard, actions réalisées, score moyen courant, progression, conformité…) ; **tableau du portefeuille** filtrable (score et tendance 6 mois, confiance, conformité, risque, priorité, retards) avec **export CSV** et **nuage maturité × performance** ; côté PME, « Mon évolution » (initial → aujourd'hui par dimension) et compteurs d'actions.
- **Analyses de portefeuille** : problèmes les plus fréquents (dimensions et critères), accompagnements les plus demandés, **heatmap secteur × dimension** (cellules masquées si moins de 5 PME), progression et stagnation, PME à accompagnement renforcé, évolutions observées par offre comparées aux PME éligibles non accompagnées, avec l'avertissement RM-09 (corrélation n'est pas causalité).
- **Rapport PDF de diagnostic en 16 sections** (présentation, méthodologie, score global, dimensions, forces, faiblesses, risques, anomalies, documents manquants, priorités, recommandations, plan, calendrier, indicateurs, conclusion, annexes avec formules financières, sources et journal de validation) : **généré automatiquement à la validation**, données figées, PDF archivé avec empreinte SHA-256 vérifiée au téléchargement, table en ajout seul, nouvelle version à chaque réédition ; téléchargeable par la PME et l'équipe. Rendu **WeasyPrint** en production (bibliothèques ajoutées à l'image Docker) et **xhtml2pdf** en repli sur un poste sans Pango (`PME360_PDF_ENGINE`).
- **Qualité** : 290 tests backend, 20 tests unitaires frontend, 22 tests E2E.

### Contenu de la phase 5

- **Moteur de recommandations sans code** : règles « SI … ALORS proposer une offre » en JSON Logic sur le score courant (critères, dimensions, indicateurs, risque, maturité, conformité, alertes, échéances) ; **versionnées** (une règle active n'est jamais modifiée), **testées sur le portefeuille** en lecture seule avant activation ; justification rédigée à partir des données (« RHO-01 niveau 1 »). 14 règles et 14 offres par défaut (Document 7, § 3.4), 21 modèles de livrables avec instructions en langage simple et points de vérification.
- **Priorisation** Impact × Urgence × Risque × Effort (Document 6, § 9) : notes proposées et expliquées, score PS de 13 à 100, ajustement possible avec motif ; revue du conseiller (accepter, rejeter avec motif, ajouter une recommandation).
- **Plan versionné** : génération des actions (étapes, livrables, dépendances, horizons J1–30 à 12 mois, capacité de 5 actions par horizon), références `ACT-AAAA-NNNNN`, « pourquoi » en langage PME ; cycle BROUILLON → EN VALIDATION → validation GUDE-PME → **acceptation par la dirigeante** (ou acceptation recueillie hors ligne, enregistrée avec motif par le conseiller) → EN COURS → CLOS ; nouvelle version avec historique.
- **Workflow des actions** (Document 7, § 2.2) : BLOQUÉE tant qu'une dépendance n'est pas terminée, démarrage par la PME, livrable déposé depuis la fiche action → analyse → « À vérifier » dans la file du conseiller → conforme / à reprendre (motif pour la PME) ; action **terminée automatiquement** quand tous ses livrables sont conformes, actions dépendantes débloquées et notifiées, abandon motivé ; journal des transitions en ajout seul ; alerte « Action en retard » activée.
- **Le score suit les preuves** : une action terminée enregistre un **progrès vérifié** (critères portés au niveau visé) qui relève le score courant ; les snapshots figés restent inchangés, un nouveau diagnostic revu par le conseiller fait foi.
- **Interfaces** : onglet « Plan & actions » de la fiche PME, fiche action, page « Mon plan » et prochaines actions sur l'accueil du portail PME, retards d'actions dans la file du conseiller, administration « Accompagnement » (règles, offres, livrables) ; le Copilot répond sur les priorités du plan.
- **Qualité** : 281 tests backend, 20 tests unitaires frontend, 18 tests E2E.

### Contenu de la phase 4

- **Passerelle IA** unique : moteur local à règles (aucune donnée envoyée) par défaut ; Claude (Anthropic) si une clé est configurée **et** que l'organisation autorise l'IA externe ; routage par tâche (rapide / standard / raisonnement), prompts versionnés, sorties validées par schéma JSON, quota mensuel de jetons, reprise et mode différé si le fournisseur est indisponible. Données personnelles **pseudonymisées** avant tout envoi.
- **Lecture des documents** (6 types : RCCM, DFE, états financiers SYSCOHADA, attestation CNPS, attestation fiscale, attestation d'assurance) : classification, extraction champ par champ avec confiance, **contrôles déterministes** (bon type, bonne entreprise, dates, équilibre du bilan, cohérence CA / déclaratif, effectif / CNPS, régime fiscal / CA). Sous le seuil (85 % par document, 90 % par champ critique, réglables) ou en cas d'anomalie : vérification humaine.
- **Revue humaine** dans l'écran de vérification : valider, corriger (justification obligatoire, RM-06) ou rejeter la lecture ; la lecture IA ne décide **jamais** de la conformité. File « Documents à vérifier » priorisée (anomalies graves, puis confiance faible).
- **Analyse financière** : états financiers extraits (provisoires tant qu'ils ne sont pas relus), ratios calculés de façon déterministe, commentaire rédigé par l'IA en **brouillon à relire** (onglet « Finances » de la fiche PME).
- **Pré-diagnostic** : à la soumission d'un diagnostic, un niveau proposé par critère avec justification, sources et confiance, affiché dans la revue ; le conseiller décide.
- **Copilot** : questions en langage naturel sur une PME ou le portefeuille, réponse diffusée en direct (SSE), limitée au périmètre de l'utilisateur, avec sources, niveau de confiance et limites ; outils en lecture seule ; index documentaire (référentiel, règles vérifiées, documents validés, historique).
- **Traçabilité** : chaque analyse enregistre moteur, modèle, version du prompt, entrées, sortie, jetons, coût et durée (« Voir l'analyse IA ») ; page « Intelligence artificielle » : politique du tenant, consommation, versions, jeu d'évaluation (132 échantillons synthétiques ; seuils : classification ≥ 97 %, montants financiers clés ≥ 95 %) et reconstruction de l'index (`ai_eval`, `ai_reindex`).
- **Qualité** : 252 tests backend, 17 tests unitaires frontend, 13 tests E2E.

### Contenu de la phase 3

- **Dépôt sécurisé** : contrôle par signature binaire (et non par extension), refus des macros, PDF actifs ou chiffrés, archives suspectes et fichiers corrompus ; **antivirus en mémoire avant tout stockage** (ClamAV en production, échec fermé) ; stockage objet S3 (MinIO en local, chiffrement côté serveur en production) ; téléchargement par URL signée personnelle de 5 minutes, liée à l'utilisateur et à l'organisation, tracé dans le journal.
- **Chaîne de traitement asynchrone** (Celery) : extraction du texte, doublons, lisibilité, validité, période attendue ; elle ne remplace jamais une décision humaine. Un document déposé n'est **jamais conforme d'office** : vérification par le conseiller (conforme, sous réserve, non conforme, incohérent) avec un motif en langage simple pour la PME.
- **Dossier de conformité** par PME (≈ 55 types de documents en 9 catégories, durées de validité et de fraîcheur) et **taux de conformité** (sous réserve = ½).
- **Registre réglementaire** : chaque obligation légale s'appuie sur une règle sourcée et datée ; une obligation liée à une règle non vérifiée **ne peut pas être activée** (RM-08). Obligations CNPS mensuelles/trimestrielles, déclarations fiscales et états financiers livrées **inactives**, en attente de vérification.
- **Échéances** générées de façon idempotente (horizon 120 jours, fréquence selon l'effectif), statuts temporels, **relances** à J-30, J-15, J-7, J0, J+7, J+15, J+30 (une seule fois chacune), escalade des obligations critiques, dispense motivée ; planificateur quotidien (Celery beat, 02 h) et commande `run_compliance`.
- **Moteur d'alertes** paramétrable (12 règles : document expiré ou manquant, échéance proche ou dépassée, anomalie de dépôt, baisse de score, risque élevé, stagnation…), dédoublonnage, résolution automatique ; **notifications** in-app et e-mail avec préférences (événements obligatoires non désactivables).
- **Les preuves relèvent le score** : un justificatif vérifié lève le plafond déclaratif (RM-01) ; le **score courant** est recalculé à chaque décision, les snapshots figés restent reproductibles (preuves « à date »).
- **Interfaces** : file « Documents à vérifier » avec aperçu, onglets Documents et Alertes de la fiche PME, page Alertes, cloche de notifications, administration « Conformité et obligations » ; côté PME, « Mes documents » (dépôt par fichier ou photo depuis le téléphone), prochaines échéances et retours du conseiller.
- **Qualité** : 221 tests backend, 12 tests unitaires frontend, 9 tests E2E (dont dépôt, refus antivirus, vérification et administration de la conformité).

### Contenu de la phase 2

- **Référentiel GUDE-360 v1.0.0** (Documents 5 et 6) : 3 piliers, 12 dimensions, 94 critères de tronc commun (dont 8 critiques) et 19 critères répartis en 6 modules sectoriels (D07), 13 indicateurs financiers. Tout est **donnée** : poids, grilles d'ancres, bandes, niveaux, portes, règles de priorité (JSON Logic).
- **Versionnement** : une version publiée est **immuable** (trigger PostgreSQL) ; clonage en brouillon, contrôles de cohérence à la publication (sommes des poids, preuves des critères critiques, formules, bandes), retrait automatique de l'ancienne version.
- **Questionnaire adaptatif** : questions de profil (effectif, entreprise familiale, stocks, production), applicabilité par critère (secteur, salariés, forme sociale, ancienneté), questions réservées au conseiller, sauvegarde automatique, historique des réponses, diagnostic de suivi pré-rempli.
- **Moteur de scoring pur et reproductible** : critères (grille 0-4 ou indicateurs), plafond déclaratif sans preuve (RM-01), dimensions (couverture, provisoire, non évaluable, exclusion), score global, IMO / IPE séparés (RM-02), lentilles, exposition au risque, maturité digitale, confiance (source × fraîcheur), niveaux N1-N5 avec **portes et plafonnement expliqué**, quadrant maturité × performance, priorité P1-P4, écarts à plus fort impact.
- **Revue humaine** (RM-05, RM-06) : valider, modifier (justification obligatoire), non applicable, déclaration corroborée ; acceptation en lot confirmée ; validation → **snapshot figé** (trigger), recalcul identique vérifié par test.
- **Explication des évolutions** : contributions par dimension et critère, distinction progrès / recul / **gain de preuve**, re-projection du point de départ si le référentiel a changé.
- **Interfaces** : Health Check, courbe d'évolution, explication des écarts, indicateurs « formule → données → résultat → interprétation → source », écran de revue, référentiel consultable, tableaux de bord (score moyen, progression, PME à risque et urgentes, problèmes les plus fréquents, stagnation), espace PME (questionnaire, score, progression).
- **Démonstration** : diagnostics fictifs illustrant les profils du Document 3, § 7 (Boutik Plus « performante mais fragile », Délices du Bandama en progression sur 3 snapshots, Bâti Lagune en priorité P1, Akwaba en attente de revue…).
- **Qualité** : 178 tests backend (moteur couvert à 98 %), 10 tests unitaires frontend ; contrat OpenAPI versionné (`frontend/openapi.json`) vérifié en CI.

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

Prérequis : Docker, Python 3.12+ (testé en 3.14), Node 24. Les ports sont décalés pour cohabiter avec d'autres projets : PostgreSQL **5442**, Redis **6390**, API **8010**, frontend **3010**, Mailpit **8035**, MinIO **9010** (console **9011**).

```bash
# 1. Infrastructure (PostgreSQL + pgvector, Redis, MinIO, Mailpit)
docker compose -f infra/docker-compose.yml up -d
# Sauvegardes (planificateur + réplication des documents) : docker compose -f infra/docker-compose.yml --profile backup up -d
# Antivirus ClamAV (facultatif en local ; sinon PME360_ANTIVIRUS=eicar, détecteur de test) :
# docker compose -f infra/docker-compose.yml --profile antivirus up -d   puis PME360_ANTIVIRUS=clamd

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS : .venv/bin/pip
cp .env.example .env        # puis renseigner DJANGO_SECRET_KEY, PME360_FIELD_ENCRYPTION_KEYS et PME360_STORAGE_MASTER_KEYS
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

**Tests** : `cd backend && .venv/Scripts/python -m pytest` · `cd frontend && npm test && npm run test:e2e` (E2E : infrastructure, API et seed lancés au préalable ; les tests de revue Akwaba et de dépôt/vérification supposent une base fraîchement « seedée », sinon ils sont ignorés).

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
