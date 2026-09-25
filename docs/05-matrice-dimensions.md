# Document 5 — Matrice des dimensions du diagnostic 360°

## 1. Rationalisation : de 13 dimensions proposées à 12 dimensions en 3 piliers

| Proposition initiale | Décision | Raison |
|---|---|---|
| D1 Formalisation & gouvernance | **Conservée** (D01) | Socle de toute PME formelle |
| D2 Fiscalité & conformité | **Conservée** (D02) | Domaine distinct, preuves spécifiques (DGI) |
| D3 CNPS / protection sociale & RH | **Scindée** : la conformité sociale (CNPS, contrats, droit du travail) devient D03, les pratiques RH rejoignent D08 | Évite le double comptage entre D3 et D8 et sépare *conformité* et *pratiques de gestion* |
| D4 Finance & comptabilité | **Conservée, pondération la plus forte** (D04) | Priorité exprimée ; source de la plupart des indicateurs de performance |
| D5 Stratégie & modèle économique | **Conservée** (D05) | |
| D6 Commercial, marketing & clients | **Conservée** (D06) | |
| D7 Opérations & productivité + D11 Qualité, normes & certification | **Fusionnées** : D07 « Opérations, qualité & conformité sectorielle », avec des **modules sectoriels** activés selon le secteur | La qualité est une dimension des opérations ; les exigences sectorielles (hygiène, sécurité de chantier…) sont des critères conditionnels |
| D8 RH & organisation | **Conservée**, enrichie des pratiques RH issues de D3 (D08) | |
| D9 Digitalisation & SI | **Conservée** (D09), avec un **Indice de maturité digitale** dédié | |
| D10 Risques, contrôle interne & continuité | **Conservée** (D10). Le **risque** devient aussi une *lentille transversale* calculée sur toutes les dimensions | Le risque existe partout (fiscal, social, client…) : une dimension isolée ne suffit pas |
| D12 Financement & opportunités | **Conservée** (D11) | |
| D13 Innovation & croissance | **Conservée** (D12) | |

## 2. Architecture retenue

```
PILIER A — CONFORMITÉ & GOUVERNANCE (socle)                  poids 30
  D01 Formalisation juridique & gouvernance                     10
  D02 Conformité fiscale                                        10
  D03 Conformité sociale (CNPS) & droit du travail              10

PILIER B — PERFORMANCE & PILOTAGE                             poids 50
  D04 Finance & comptabilité                                    15
  D05 Stratégie & modèle économique                              7
  D06 Commercial, marketing & clients                            8
  D07 Opérations, qualité & conformité sectorielle               8
  D08 Ressources humaines & organisation                         7
  D09 Digitalisation & systèmes d'information                    5

PILIER C — RÉSILIENCE & CROISSANCE                            poids 20
  D10 Risques, contrôle interne & continuité                     8
  D11 Financement & accès aux opportunités                       6
  D12 Innovation & croissance                                    6
                                                              ─────
                                                               100
```

Les poids ci-dessus sont les **valeurs par défaut** du référentiel `GUDE-360 v1.0.0`. Ils sont modifiables par l'administrateur, avec publication d'une nouvelle version.

## 3. Lentilles transversales (sous-scores)

Chaque critère est rattaché à **une** lentille :

| Lentille | Question posée | Exemple |
|---|---|---|
| **C : Conformité** | L'obligation est-elle remplie et prouvée ? | Immatriculation RCCM, déclarations CNPS à jour |
| **O : Organisation** | La pratique existe-t-elle, est-elle formalisée et appliquée ? | Procédure d'achats écrite et appliquée |
| **P : Performance** | Quels sont les résultats obtenus ? | Marge nette, croissance du CA |
| **R : Risque** | Quelle est l'exposition ? (score élevé = risque **maîtrisé**) | Concentration client, arriérés |

Ces lentilles produisent les sous-scores **Conformité**, **Organisation**, **Performance** et **Maîtrise des risques** demandés (cf. Document 6).

## 4. Grille de notation commune (niveaux 0 à 4)

Chaque critère est noté selon une grille à **ancres descriptives** : le conseiller ou l'IA choisit une description, pas un chiffre arbitraire.

| Niveau | Signification générique | Valeur |
|---|---|---|
| 0 | **Absent** : rien n'existe | 0 |
| 1 | **Informel** : pratique occasionnelle, non écrite, dépendante d'une personne | 25 |
| 2 | **Formalisé** : existe par écrit ou est déclaré, application partielle | 50 |
| 3 | **Appliqué et prouvé** : appliqué régulièrement, preuve vérifiée | 75 |
| 4 | **Piloté** : mesuré, revu, amélioré ; prouvé dans la durée | 100 |

- Les critères de **performance (P)** ne suivent pas cette grille : ils sont notés à partir d'**indicateurs chiffrés** et de **bandes d'interprétation** (Document 6, § 7).
- Le niveau **plafond déclaratif** (2 par défaut) s'applique aux critères C et O dont la politique de preuve est `REQUIRED` (règle RM-01).

## 5. Matrice détaillée des critères

Légende : **Crit.** = critère critique (déclenche une porte de maturité, cf. Document 6, § 4). **Preuve** = types de documents attendus (codes du Document 8).

### D01 — Formalisation juridique & gouvernance (poids 10)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| FOR-01 | Existence légale et immatriculation au RCCM | C | 20 | ✅ | RCCM |
| FOR-02 | Statuts à jour et cohérents avec la réalité (capital, associés, dirigeants) | C | 12 | | STATUTS |
| FOR-03 | Identification fiscale (DFE / NCC) | C | 13 | ✅ | DFE |
| FOR-04 | Organes de décision fonctionnels (AG, PV, décisions formalisées) | O | 12 | | PV_AG |
| FOR-05 | Séparation du patrimoine personnel et professionnel (compte bancaire dédié, pas de caisse commune) | O | 13 | | RELEVE_BANCAIRE_SYNTH (V2) / déclaratif |
| FOR-06 | Délégations de pouvoir et signatures définies | O | 8 | | DELEGATIONS |
| FOR-07 | Contrats structurants écrits (bail, clients et fournisseurs clés, partenariats) | O | 10 | | CONTRATS_CLES |
| FOR-08 | Gouvernance familiale ou associative clarifiée (si entreprise familiale : règles de succession, rôles) | O | 6 | | déclaratif · *applicable si entreprise familiale* |
| FOR-09 | Procédures administratives internes documentées | O | 6 | | MANUEL_PROC |

### D02 — Conformité fiscale (poids 10)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| FIS-01 | Régime d'imposition identifié et cohérent avec le CA | C | 12 | | DFE, états financiers |
| FIS-02 | Déclarations périodiques déposées dans les délais (selon le régime) | C | 25 | ✅ | DECL_FISCALE_PERIODIQUE |
| FIS-03 | Paiements effectués / absence d'arriérés | C | 20 | ✅ | PREUVE_PAIEMENT_FISC, ATTEST_REGUL_FISC |
| FIS-04 | Attestation de régularité fiscale en cours de validité | C | 15 | | ATTEST_REGUL_FISC |
| FIS-05 | Dépôt annuel des états financiers auprès de l'administration | C | 13 | | ETATS_FIN_SYSCOHADA + preuve de dépôt |
| FIS-06 | Cohérence entre activité réelle et déclarations (CA déclaré vs CA comptable) | R | 10 | | contrôle croisé IA |
| FIS-07 | Organisation de la documentation fiscale (classement, conseil) | O | 5 | | déclaratif |

### D03 — Conformité sociale (CNPS) & droit du travail (poids 10)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| SOC-01 | Immatriculation employeur à la CNPS | C | 15 | ✅ *(si ≥ 1 salarié)* | IMMAT_CNPS |
| SOC-02 | Déclaration de tous les salariés | C | 20 | ✅ | DECL_CNPS_PERIODIQUE (effectif déclaré) |
| SOC-03 | Déclarations et cotisations à jour selon la périodicité applicable | C | 25 | ✅ | DECL_CNPS_PERIODIQUE, PREUVE_PAIEMENT_CNPS, ATTEST_CNPS |
| SOC-04 | Absence d'arriérés / plan d'apurement respecté | R | 10 | | ATTEST_CNPS |
| SOC-05 | Contrats de travail écrits pour les salariés | C | 15 | | CONTRAT_TRAVAIL_ECHANTILLON / registre |
| SOC-06 | Tenue des registres et bulletins de paie | C | 10 | | BULLETIN_PAIE_ECHANTILLON (anonymisé) |
| SOC-07 | Santé et sécurité au travail (dispositions minimales) | C | 5 | | déclaratif / sectoriel |

> Si la PME n'a **aucun salarié**, les critères SOC-01 à SOC-06 sont `NON_APPLICABLE` et la dimension est recalculée sur les critères restants. Au-delà d'un taux de non-applicabilité de 70 %, la dimension est exclue et son poids redistribué (Document 6, § 3.4).

### D04 — Finance & comptabilité (poids 15)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| FIN-01 | Tenue d'une comptabilité régulière (SYSCOHADA normal ou SMT selon la taille) | C | 12 | ✅ | ETATS_FIN_SYSCOHADA |
| FIN-02 | Qualité de la comptabilité (expert-comptable ou CGA, états certifiés ou visés) | O | 8 | | ETATS_FIN + attestation / visa |
| FIN-03 | Suivi de trésorerie (plan de trésorerie, rapprochements bancaires) | O | 10 | | TABLEAU_TRESORERIE |
| FIN-04 | Reporting de gestion périodique (mensuel ou trimestriel) | O | 8 | | TABLEAU_BORD_FIN |
| FIN-05 | Budget et prévisions financières | O | 7 | | BUDGET, PREVISIONNEL |
| FIN-06 | Rentabilité (marge nette, EBE / CA) | P | 12 | | indicateurs calculés |
| FIN-07 | Croissance du CA (N / N-1, tendance sur 3 ans) | P | 8 | | indicateurs calculés |
| FIN-08 | Structure financière et solvabilité (autonomie financière, endettement) | P | 10 | | indicateurs calculés |
| FIN-09 | Liquidité et BFR (liquidité générale, délais clients et fournisseurs) | P | 10 | | indicateurs calculés |
| FIN-10 | Capacité de remboursement (dettes financières / CAF) | P | 8 | | indicateurs calculés |
| FIN-11 | Concentration clients et fournisseurs (part du 1er et des 5 premiers) | R | 7 | | déclaratif + balance âgée (V2) |

### D05 — Stratégie & modèle économique (poids 7)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| STR-01 | Vision, mission et objectifs formalisés et partagés | O | 15 | | PLAN_STRATEGIQUE |
| STR-02 | Proposition de valeur et segments clients clairs | O | 20 | | BUSINESS_MODEL |
| STR-03 | Positionnement et avantage concurrentiel identifiés (analyse de la concurrence) | O | 15 | | déclaratif / BUSINESS_PLAN |
| STR-04 | Plan d'affaires ou feuille de route à jour (< 2 ans) | O | 20 | | BUSINESS_PLAN, FEUILLE_ROUTE |
| STR-05 | Diversification (produits, clients, marchés) | R | 15 | | déclaratif + FIN-11 |
| STR-06 | Suivi des objectifs stratégiques (revue au moins annuelle) | O | 15 | | PV / compte rendu de revue |

### D06 — Commercial, marketing & clients (poids 8)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| COM-01 | Connaissance et suivi du portefeuille clients (fichier ou CRM) | O | 15 | | EXPORT_FICHIER_CLIENTS (agrégé) |
| COM-02 | Processus de vente et pipeline suivis | O | 15 | | TABLEAU_SUIVI_COMMERCIAL |
| COM-03 | Politique de prix documentée (calcul des coûts et des marges) | O | 12 | | GRILLE_TARIFAIRE |
| COM-04 | Actions marketing et communication planifiées | O | 10 | | PLAN_MARKETING |
| COM-05 | Présence digitale (site, réseaux sociaux, annuaires) | O | 10 | | liens vérifiables |
| COM-06 | Satisfaction client et traitement des réclamations | O | 13 | | REGISTRE_RECLAMATIONS |
| COM-07 | Canaux de distribution adaptés et diversifiés | P | 10 | | déclaratif |
| COM-08 | Dépendance commerciale (part du 1er client) | R | 15 | | déclaratif + FIN-11 |

### D07 — Opérations, qualité & conformité sectorielle (poids 8)

**Tronc commun**

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| OPE-01 | Processus clés cartographiés | O | 12 | | CARTO_PROCESSUS |
| OPE-02 | Gestion des achats et des fournisseurs (procédure, mise en concurrence) | O | 12 | | PROC_ACHATS |
| OPE-03 | Gestion des stocks (inventaire, suivi) | O | 10 | | ETAT_STOCKS · *si activité avec stocks* |
| OPE-04 | Maîtrise des délais et de la qualité (indicateurs suivis) | P | 12 | | TABLEAU_BORD_OPS |
| OPE-05 | Équipements et maintenance (plan de maintenance) | O | 8 | | PLAN_MAINTENANCE · *si production* |
| OPE-06 | Calcul et maîtrise des coûts de revient | O | 10 | | fiche de coût de revient |
| OPE-07 | Capacité de production et productivité connues | P | 8 | | déclaratif |
| OPE-08 | Démarche qualité (procédures qualité, certification éventuelle : ISO ou autre) | O | 13 | | CERTIFICAT / MANUEL_QUALITE |

**Modules sectoriels** (critères conditionnels, 15 points redistribués, ajoutés selon `pme.sector`)

| Secteur | Critères ajoutés (exemples, à valider avec des experts sectoriels) |
|---|---|
| Agroalimentaire | Hygiène et bonnes pratiques de fabrication ; traçabilité des lots ; autorisations ou agréments sanitaires applicables ; chaîne du froid |
| BTP | Sécurité des chantiers (EPI, plan de prévention) ; agréments ou qualifications professionnelles ; assurances professionnelles ; références de marchés exécutés |
| Industrie | HSE et gestion des déchets ; conformité environnementale applicable ; sécurité des machines |
| Commerce | Gestion des stocks et démarque ; conformité de l'étiquetage et des prix ; factures normalisées |
| Services | Qualité de service (délais, SLA) ; confidentialité client |
| Startup technologique | Sécurité des produits ; conformité à la protection des données des utilisateurs ; propriété du code et des actifs |

> Les exigences sectorielles réglementaires sont enregistrées dans le **registre réglementaire** (Document 8) et restent **au statut « à vérifier »** tant qu'une source officielle n'est pas documentée.

### D08 — Ressources humaines & organisation (poids 7)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| RHO-01 | Organigramme à jour | O | 12 | | ORGANIGRAMME |
| RHO-02 | Fiches de poste (postes clés) | O | 12 | | FICHES_POSTE |
| RHO-03 | Recrutement structuré | O | 8 | | PROC_RH |
| RHO-04 | Plan de formation et formations réalisées | O | 12 | | PLAN_FORMATION |
| RHO-05 | Évaluation de la performance (entretiens annuels) | O | 10 | | SUPPORT_EVALUATION |
| RHO-06 | Politique de rémunération et gestion des congés | O | 10 | | POLITIQUE_REMUNERATION |
| RHO-07 | Turnover maîtrisé | P | 10 | | déclaratif (effectifs entrées / sorties) |
| RHO-08 | Délégation managériale (le dirigeant n'est pas un point unique de décision) | R | 14 | | déclaratif + entretien |
| RHO-09 | Plan de succession des postes clés | R | 12 | | déclaratif |

### D09 — Digitalisation & systèmes d'information (poids 5)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| DIG-01 | Équipements adaptés à l'activité | O | 8 | | INVENTAIRE_SI |
| DIG-02 | Logiciel de comptabilité ou de gestion | O | 15 | | déclaratif + capture |
| DIG-03 | Outils métier (ERP, CRM, paie, stocks, caisse) | O | 12 | | déclaratif |
| DIG-04 | Sauvegardes régulières et testées | R | 15 | | POLITIQUE_SAUVEGARDE |
| DIG-05 | Cybersécurité de base (mots de passe, antivirus, mises à jour, MFA) | R | 15 | | POLITIQUE_SI |
| DIG-06 | Gestion documentaire numérique | O | 10 | | déclaratif |
| DIG-07 | Digitalisation des processus (paiements mobiles, facturation électronique, commandes) | O | 10 | | déclaratif |
| DIG-08 | Présence web et réseaux sociaux (mutualisé avec COM-05, compté une seule fois dans le global) | O | 5 | | liens |
| DIG-09 | Usage de l'IA et des outils collaboratifs | O | 10 | | déclaratif |

**Indice de maturité digitale (IMD)** = score de D09 + COM-05, sur 100, publié séparément (niveaux : *Analogique*, *Équipé*, *Connecté*, *Intégré*, *Piloté par la donnée*).

### D10 — Risques, contrôle interne & continuité (poids 8)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| RIS-01 | Cartographie ou registre des risques | O | 15 | | REGISTRE_RISQUES |
| RIS-02 | Contrôle interne de base (séparation des tâches, double signature, rapprochements) | O | 20 | | PROC_CONTROLE_INTERNE |
| RIS-03 | Gestion de la caisse et prévention de la fraude | R | 15 | | PROC_CAISSE |
| RIS-04 | Assurances adaptées (responsabilité civile, biens, marchandises) | C | 15 | | ATTEST_ASSURANCE |
| RIS-05 | Plan de continuité d'activité (dépendances critiques, personnes clés) | O | 15 | | PCA |
| RIS-06 | Gestion de crise (procédure, contacts) | O | 10 | | déclaratif |
| RIS-07 | Litiges en cours maîtrisés | R | 10 | | déclaratif |

### D11 — Financement & accès aux opportunités (poids 6)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| FIO-01 | Besoin de financement identifié et chiffré | O | 15 | | PLAN_FINANCEMENT |
| FIO-02 | Relation bancaire (compte, historique de crédit, incidents) | P | 15 | | déclaratif / attestation bancaire |
| FIO-03 | Capacité à présenter un dossier finançable (états financiers, business plan, garanties) | O | 20 | | score composite FIN + STR |
| FIO-04 | Connaissance et utilisation des dispositifs d'appui (programmes, garanties, fonds) | O | 10 | | déclaratif |
| FIO-05 | Accès aux marchés publics (inscription, dossiers, marchés obtenus) | P | 15 | | déclaratif / références |
| FIO-06 | Export ou marchés régionaux | P | 10 | | déclaratif |
| FIO-07 | Partenariats et investisseurs | P | 15 | | déclaratif |

### D12 — Innovation & croissance (poids 6)

| Code | Critère | Lentille | Poids | Crit. | Preuve |
|---|---|---|---|---|---|
| INN-01 | Nouveaux produits ou services lancés (3 dernières années) | P | 20 | | déclaratif |
| INN-02 | Nouveaux marchés ou segments conquis | P | 15 | | déclaratif |
| INN-03 | Démarche d'innovation (veille, R&D, amélioration continue) | O | 15 | | déclaratif |
| INN-04 | Propriété intellectuelle (marques, brevets : dépôt OAPI) | C | 15 | | CERTIFICAT_PI |
| INN-05 | Partenariats d'innovation (universités, incubateurs, grands comptes) | O | 10 | | déclaratif |
| INN-06 | Capacité d'expansion et de passage à l'échelle (processus reproductibles, capacité de financement) | O | 25 | | composite |

## 6. Adaptation du questionnaire

Le questionnaire est **adaptatif** : chaque critère et chaque question porte une règle d'applicabilité (JSON Logic) évaluée sur le profil de la PME.

| Variable du profil | Effets |
|---|---|
| `size_category` (micro / petite / moyenne) | Micro : SMT accepté pour FIN-01, questions de gouvernance allégées, D10 simplifiée |
| `headcount` | 0 salarié : D03 non applicable ; ≥ 20 : périodicité CNPS mensuelle (Document 8) |
| `sector` | Activation du module sectoriel de D07 |
| `tax_regime` | Obligations et périodicités fiscales attendues (FIS-02) |
| `has_stock`, `has_production`, `is_family_business` | OPE-03, OPE-05, FOR-08 |
| `company_age` | < 2 ans : FIN-07 (croissance) remplacé par la traction commerciale, historique non exigé |

**Volume cible** : 60 à 90 questions pour la PME, réparties en 12 étapes courtes (5 à 10 minutes chacune), sauvegarde automatique, reprise possible. Les questions « expertes » (`target_audience = CONSEILLER`) sont renseignées par le conseiller lors de l'entretien.

## 7. Exemple de question avec ancres (FIN-03)

> **Comment suivez-vous l'argent qui entre et qui sort de votre entreprise ?**
> *Pourquoi cette question ?* Savoir à l'avance quand la trésorerie manquera permet d'éviter les retards de paiement.
>
> - ○ Je ne fais pas de suivi particulier → **0**
> - ○ Je regarde mon solde bancaire ou ma caisse de temps en temps → **1**
> - ○ J'ai un tableau (cahier ou Excel) mis à jour de temps en temps → **2**
> - ○ J'ai un tableau de trésorerie mis à jour chaque semaine ou chaque mois, et je rapproche avec la banque → **3** *(preuve demandée : tableau de trésorerie des 3 derniers mois)*
> - ○ J'ai des prévisions sur 3 à 6 mois que je compare au réel chaque mois → **4** *(preuve demandée)*
