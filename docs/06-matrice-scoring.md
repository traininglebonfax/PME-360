# Document 6 — Matrice et moteur de scoring

## 1. Ce que le moteur produit

| Indicateur | Échelle | Question à laquelle il répond | Calcul |
|---|---|---|---|
| **Score global 360** | 0–100 | « Où en est la PME, toutes dimensions confondues ? » | Moyenne pondérée des 12 dimensions |
| **Score par dimension** | 0–100 | « Où en est-elle en finance, en RH… ? » | Moyenne pondérée des critères applicables |
| **Indice de Maturité Organisationnelle (IMO)** | 0–100 | « Est-elle structurée, conforme et maîtrisée ? » | Critères des lentilles C + O + R |
| **Indice de Performance Économique (IPE)** | 0–100 | « Obtient-elle des résultats ? » | Critères de la lentille P (indicateurs chiffrés) |
| **Sous-scores par lentille** | 0–100 | Conformité, Organisation, Performance, Maîtrise des risques | Critères de chaque lentille, toutes dimensions |
| **Taux de conformité documentaire** | % | « Les obligations sont-elles remplies et prouvées ? » | Éléments exigibles conformes / éléments exigibles |
| **Indice d'exposition au risque** | 0–100 (élevé = risqué) | « Faut-il s'inquiéter ? » | 100 − lentille R, majoré par les alertes ouvertes |
| **Niveau de maturité** | N1 à N5 | Libellé lisible | IMO + portes de passage |
| **Priorité d'intervention** | P1 à P4 | « Faut-il intervenir vite ? » | Règles configurables |
| **Indice de confiance** | % | « Ce score est-il fiable ? » | Sources, fraîcheur, couverture |

**Séparation maturité / performance (RM-02).** Le **niveau de maturité** est calculé sur l'**IMO**, jamais sur le CA ni sur l'IPE. Une PME à fort chiffre d'affaires mais désorganisée apparaîtra « Performante mais fragile » et non « Mature ».

## 2. Score d'un critère

### 2.1 Critères à grille (lentilles C, O, R)
```
niveau_retenu = niveau_final (validé par l'humain) sinon niveau_proposé_IA sinon niveau_déclaré
si politique_preuve = REQUIRED et aucune preuve VÉRIFIÉE et à jour :
    niveau_retenu = min(niveau_retenu, plafond_déclaratif)      # 2 par défaut (RM-01)
score_critère = niveau_retenu × 25                              # 0, 25, 50, 75, 100
```

### 2.2 Critères de performance (lentille P)
Chaque critère P est relié à un ou plusieurs indicateurs (`metric_definition`). Chaque indicateur est converti en points par des **bandes d'interprétation** configurables (§ 7), et le score du critère est la moyenne pondérée de ses indicateurs.

Si les données financières sont indisponibles, le critère est **non évalué** (et non noté 0). La confiance de la dimension baisse en conséquence.

### 2.3 Modules sectoriels (D07)
Tronc commun ramené à 85 % du poids de la dimension et module sectoriel à 15 %. Sans module pour le secteur, le tronc commun vaut 100 %.

## 3. Agrégation

### 3.1 Score d'une dimension
```
S_d = Σ(w_c × s_c) / Σ(w_c)        sur les critères applicables ET évalués
couverture_d = Σ(w_c évalués) / Σ(w_c applicables)
```
- Si `couverture_d < 70 %`, la dimension est affichée comme **« provisoire »** (pastille grise) et sa confiance est fortement réduite (§ 5).
- Si `couverture_d < 40 %`, la dimension est **« non évaluable »** : elle n'est pas affichée en chiffre et est exclue du score global, dont les poids sont renormalisés.

### 3.2 Score global
```
Score_global = Σ(W_d × S_d) / Σ(W_d)     sur les dimensions évaluables
```

### 3.3 Indices transversaux
```
IMO = Σ w_c × s_c / Σ w_c        critères des lentilles C, O, R ; w_c = poids critère × poids dimension
IPE = Σ w_c × s_c / Σ w_c        critères de la lentille P
Sous-score lentille L = même formule, restreinte à la lentille L
```

### 3.4 Non-applicabilité
Les critères `NON_APPLICABLE` (règle d'applicabilité ou décision justifiée du conseiller) sont retirés du numérateur **et** du dénominateur. Au-delà de 70 % de non-applicabilité, la dimension entière est exclue et son poids redistribué proportionnellement.

### 3.5 Pseudo-code du moteur

```python
def compute_snapshot(diagnostic, framework_version, as_of) -> Snapshot:
    items = []
    for dim in framework_version.dimensions:
        crit_scores = []
        for crit in dim.criteria:
            if not crit.is_applicable(diagnostic.pme_profile):
                continue
            a = diagnostic.assessment(crit)             # niveaux, preuves, sources
            s = score_criterion(crit, a, as_of)         # § 2 (plafond déclaratif inclus)
            c = confidence_criterion(crit, a, as_of)    # § 5
            crit_scores.append(CriterionScore(crit, s, c))
        items.append(aggregate_dimension(dim, crit_scores))  # § 3.1
    snapshot = aggregate_global(items)                      # § 3.2, 3.3
    snapshot.level = maturity_level(snapshot)               # § 4 (portes)
    snapshot.priority = intervention_priority(snapshot)     # § 6, règles configurables
    snapshot.engine_version = ENGINE_VERSION
    return snapshot     # entièrement dérivé des entrées : recalcul identique garanti
```

Le moteur est une **fonction pure** : mêmes entrées, même version du référentiel et même version du moteur donnent le même résultat. Cette propriété est couverte par des tests de non-régression (instantanés sur la seed).

## 4. Niveaux de maturité (nomenclature proposée)

| Niveau | Libellé | Plage IMO | Portes de passage (toutes requises) | Lecture pour la PME |
|---|---|---|---|---|
| **N1** | **Fragile** | 0–34 | — | « Les bases de votre entreprise doivent être consolidées en priorité. » |
| **N2** | **En structuration** | 35–54 | Critères critiques du pilier A ≥ niveau 1 (existence légale reconnue) | « Vous avez commencé à vous organiser ; il reste des fondations à poser. » |
| **N3** | **Structurée** | 55–69 | Tous les critères critiques ≥ niveau 2 ; aucune dimension du pilier A < 40 | « Votre entreprise est organisée ; place à l'optimisation. » |
| **N4** | **Maîtrisée** | 70–84 | Tous les critères critiques ≥ niveau 3 **prouvés** ; aucune dimension < 40 ; confiance globale ≥ 60 % ; aucune alerte CRITIQUE ouverte | « Votre entreprise est bien pilotée et conforme. » |
| **N5** | **Prête pour la croissance** | 85–100 | Portes N4 + aucune dimension < 55 ; IPE ≥ 60 ; confiance ≥ 75 % | « Vous êtes prête à changer d'échelle : financement, nouveaux marchés. » |

Pourquoi « En structuration » et « Maîtrisée » plutôt qu'« Émergent » et « Mature » : ces libellés décrivent **ce que la PME fait** et restent encourageants, sans jugement sur la taille ni sur l'âge.

**Plafonnement** : si l'IMO correspond à N4 mais qu'une porte échoue, le niveau affiché est N3 avec la mention **« Niveau plafonné : 2 critères critiques non prouvés (FIS-02, SOC-03) »**. Le plafonnement est en soi une information d'accompagnement.

### Matrice Maturité × Performance

```
            IPE ≥ 60                                    IPE < 60
IMO ≥ 55 │ ★ Championne structurée                  │ Structurée, performance à développer │
IMO < 55 │ ⚠ Performante mais fragile (risque caché) │ ✚ À consolider en priorité            │
```
Ces quadrants sont affichés sur la fiche PME et servent à segmenter le portefeuille.

## 5. Indice de confiance

### 5.1 Confiance d'un critère
```
conf_c = facteur_source × facteur_fraîcheur
```

| Source de la donnée retenue | facteur_source |
|---|---|
| Document **vérifié par un humain** | 1,00 |
| Document analysé par l'IA, non vérifié | 0,80 × confiance du document |
| Déclaratif **corroboré** par le conseiller (entretien, visite) | 0,60 |
| Déclaratif PME seul | 0,45 |
| Inféré par l'IA sans source directe | 0,35 |
| Non renseigné | 0 |

| Fraîcheur | facteur_fraîcheur |
|---|---|
| Dans la durée de validité (ou < 12 mois pour une donnée déclarative) | 1,00 |
| Entre 1× et 2× la durée de validité | décroissance linéaire de 1,00 à 0,50 |
| Au-delà | 0,50 |

### 5.2 Confiance d'une dimension et confiance globale
```
Conf_d = Σ(w_c × conf_c) / Σ(w_c applicables)     # un critère non renseigné compte pour 0 : la couverture est intégrée
Conf_globale = Σ(W_d × Conf_d) / Σ(W_d)
```

### 5.3 Exemple (exigence § 6 du cahier des charges)

| Situation | Finance | Confiance | Pourquoi |
|---|---|---|---|
| États financiers 2025 vérifiés, situation intermédiaire 2026 analysée par l'IA, questionnaire complet | 72/100 | **≈ 90 %** | 80 % du poids des critères repose sur des documents vérifiés |
| Mêmes réponses, sans états financiers | 72/100 (critères P non évalués → score calculé sur les critères O) | **≈ 55 %** | Données uniquement déclaratives, couverture réduite |

Affichage : **« Finance : 72/100 — Confiance 55 % »**, avec un lien « Pourquoi ? » qui liste les sources utilisées et les documents qui augmenteraient la confiance (« Déposez vos états financiers 2025 : +35 points de confiance estimés »).

Seuils d'affichage : ≥ 75 % **Élevée** (vert) · 50–74 % **Moyenne** (orange) · < 50 % **Faible** (gris, score en italique « indicatif »).

## 6. Priorité d'intervention (niveau PME)

Règles par défaut, stockées comme règles de type `PRIORITE` (JSON Logic, modifiables) :

| Priorité | Condition par défaut (première règle vérifiée) |
|---|---|
| **P1 — Urgente** | Alerte CRITIQUE ouverte **ou** exposition au risque ≥ 70 **ou** (IMO < 35 **et** baisse ≥ 5 points depuis le dernier snapshot) |
| **P2 — Renforcée** | IMO < 55 **ou** exposition ≥ 50 **ou** ≥ 3 actions critiques en retard **ou** stagnation (< +2 points en 6 mois d'accompagnement) |
| **P3 — Standard** | Autres cas |
| **P4 — Veille** | Niveau ≥ N4 **et** exposition < 30 **et** aucune alerte ≥ ÉLEVÉE |

La priorité proposée peut être **surchargée** par le conseiller (motif obligatoire, visible, journalisé) ; la surcharge expire au prochain snapshot.

## 7. Indicateurs financiers : transparence totale

Chaque indicateur est affiché sous la forme : **Indicateur → Formule → Données utilisées → Résultat → Interprétation → Source documentaire**.

Exemple d'affichage :

> **Autonomie financière** = Capitaux propres / Total passif
> = 48 500 000 / 162 000 000 = **29,9 %**
> Interprétation : *Acceptable (bande 20–35 %). L'entreprise dépend encore significativement de ses créanciers.*
> Source : États financiers 2025, bilan passif, p. 2 (vérifiés par A. T. le 03/04/2026)

### 7.1 Catalogue par défaut (seuils indicatifs, à calibrer par secteur avec les experts GUDE-PME)

| Code | Indicateur | Formule | Bandes → points (0 / 25 / 50 / 75 / 100) | Critère |
|---|---|---|---|---|
| `CA_CROISSANCE` | Croissance du CA | (CA_N − CA_N-1) / CA_N-1 | < −10 % / −10–0 / 0–5 / 5–15 / > 15 % | FIN-07 |
| `CA_TCAM3` | Croissance annuelle moyenne sur 3 ans | (CA_N / CA_N-2)^(1/2) − 1 | idem | FIN-07 |
| `MARGE_BRUTE` | Marge commerciale ou brute | Marge commerciale / Ventes de marchandises | sectoriel | FIN-06 |
| `TAUX_VA` | Taux de valeur ajoutée | VA / CA | sectoriel | FIN-06 |
| `TAUX_EBE` | Taux d'EBE | EBE / CA | < 0 / 0–5 / 5–10 / 10–20 / > 20 % | FIN-06 |
| `MARGE_NETTE` | Rentabilité nette | Résultat net / CA | < 0 / 0–2 / 2–5 / 5–10 / > 10 % | FIN-06 |
| `ROE` | Rentabilité des capitaux propres | Résultat net / Capitaux propres | < 0 / 0–5 / 5–10 / 10–20 / > 20 % | FIN-06 |
| `CAF` | Capacité d'autofinancement (méthode simplifiée) | Résultat net + dotations aux amortissements et provisions − reprises (± plus-values de cession) | sert à `CAP_REMB` | FIN-10 |
| `AUTONOMIE` | Autonomie financière | Capitaux propres / Total passif | < 10 / 10–20 / 20–35 / 35–50 / > 50 % | FIN-08 |
| `ENDETTEMENT` | Taux d'endettement (gearing) | Dettes financières / Capitaux propres | > 3 / 2–3 / 1–2 / 0,5–1 / < 0,5 | FIN-08 |
| `CAP_REMB` | Capacité de remboursement | Dettes financières / CAF (en années) | > 7 ou CAF ≤ 0 / 5–7 / 3–5 / 1–3 / < 1 | FIN-10 |
| `FR` | Fonds de roulement | Ressources stables − Actif immobilisé | sert à `TN` | FIN-09 |
| `BFR` | Besoin en fonds de roulement | (Stocks + Créances d'exploitation) − Dettes d'exploitation | exprimé aussi en jours de CA | FIN-09 |
| `BFR_JOURS` | BFR en jours de CA | BFR / CA × 360 | sectoriel | FIN-09 |
| `TN` | Trésorerie nette | FR − BFR (contrôle : Trésorerie actif − Trésorerie passif) | < 0 et en baisse / < 0 / ≈ 0 / > 0 / > 1 mois de charges | FIN-09 |
| `LIQ_GEN` | Liquidité générale | Actif circulant (y c. trésorerie) / Passif circulant (y c. trésorerie passif) | < 0,8 / 0,8–1 / 1–1,2 / 1,2–1,5 / > 1,5 | FIN-09 |
| `DSO` | Délai de paiement clients | Créances clients / CA TTC × 360 | > 120 / 90–120 / 60–90 / 30–60 / < 30 j | FIN-09 |
| `DPO` | Délai de paiement fournisseurs | Dettes fournisseurs / Achats TTC × 360 | informatif | FIN-09 |
| `CONC_CLIENT_1` | Concentration du 1er client | CA du 1er client / CA total | > 50 / 35–50 / 20–35 / 10–20 / < 10 % | FIN-11, COM-08 |
| `CONC_CLIENT_5` | Concentration des 5 premiers clients | CA top 5 / CA total | > 80 / 60–80 / 40–60 / 25–40 / < 25 % | FIN-11 |
| `CONC_FOURN_1` | Dépendance au 1er fournisseur | Achats au 1er fournisseur / Achats totaux | > 60 / 45–60 / 30–45 / 15–30 / < 15 % | FIN-11 |
| `MASSE_SAL_CA` | Poids de la masse salariale | Charges de personnel / CA | informatif, sectoriel | — |

> **Avertissements** :
> 1. Les bandes ci-dessus sont des **valeurs de départ**. Elles doivent être validées par un expert-comptable et calibrées **par secteur** (le BFR d'un commerce n'est pas celui d'une entreprise de BTP). La calibration sur les données réelles du portefeuille est prévue en V3.
> 2. Les correspondances avec les rubriques SYSCOHADA (bilan et compte de résultat) sont stockées en configuration et **à valider** par l'expert-comptable du projet.
> 3. Pour une entreprise au **SMT** (système minimal de trésorerie), seuls les indicateurs calculables sont produits ; les autres sont « non évaluables », ce qui baisse la confiance mais ne pénalise pas le score.

## 8. Explication des évolutions de score

Pour deux snapshots A (référence) et B (actuel) :
```
Contribution_d (en points de score global) = W_d × (S_d(B) − S_d(A)) / ΣW
Δ_global = Σ Contribution_d
```
Détail par critère : `W_d × w_c × (s_c(B) − s_c(A)) / (ΣW × Σw_d)`.

Affichage :
> **+14 points depuis le diagnostic initial (54 → 68)**
> - Formalisation : **+4,1** (FOR-03 DFE prouvée ; FOR-04 PV d'AG déposés)
> - Finance : **+3,8** (FIN-03 tableau de trésorerie mensuel ; FIN-01 états financiers 2025 déposés)
> - RH : **+2,9** (RHO-01 organigramme ; RHO-02 fiches de poste)
> - Digital : **+1,6** (DIG-04 sauvegardes)
> - Commercial : **−0,8** (COM-08 dépendance au 1er client en hausse)
> - Autres : **+2,4**
> *Une partie de la hausse (≈ +3 points) provient de preuves nouvellement fournies sur des pratiques qui existaient déjà : il s'agit d'une meilleure **mesure**, pas nécessairement d'un progrès réel.*

Le moteur distingue en effet :
- **Progrès réel** : le niveau d'un critère augmente ;
- **Gain de preuve** : le niveau augmente uniquement parce que le plafond déclaratif a été levé par une preuve ;
- **Effet de référentiel** : si le référentiel a changé de version entre A et B, le snapshot A est **recalculé** avec la version B (« baseline re-projetée ») afin de comparer ce qui est comparable ; les deux valeurs sont conservées.

## 9. Priorisation des actions : matrice Impact × Urgence × Risque × Effort

### 9.1 Notation (1 à 5), proposée automatiquement puis modifiable

| Axe | Proposition automatique |
|---|---|
| **Impact** | Gain potentiel sur le score global = W_d × w_c × (niveau cible − niveau actuel) ; converti en quintiles |
| **Urgence** | 5 si obligation légale non remplie ou échéance < 30 jours ; 4 si critère critique ; sinon selon la dépendance d'autres actions |
| **Risque** | Selon la lentille R, les alertes liées et l'exposition financière |
| **Effort** | Selon la durée et le coût de l'offre d'accompagnement (1 = < 1 semaine et gratuit ; 5 = > 3 mois ou coûteux) |

### 9.2 Score de priorité
```
PS = 20 × (0,40 × Impact + 0,30 × Urgence + 0,30 × Risque) × facteur_effort
facteur_effort = {1: 1,00 ; 2: 0,95 ; 3: 0,85 ; 4: 0,75 ; 5: 0,65}
```
PS est compris entre 13 et 100. Les coefficients sont paramétrables.

### 9.3 Affectation aux horizons (plan 90 jours)

| Horizon | Règle par défaut |
|---|---|
| **Jours 1–30 : urgentes** | Obligations légales non remplies, alertes CRITIQUES, PS ≥ 70, « gains rapides » (Impact ≥ 3 et Effort ≤ 2) |
| **Jours 31–60 : structurantes** | PS 50–69, ou actions dont les prérequis sont en J1–30 |
| **Jours 61–90 : consolidation** | PS 35–49 |
| **6 mois** | PS < 35, ou Effort = 5 |
| **12 mois** | Actions de croissance (D11, D12) conditionnées à un niveau ≥ N3 |

Contraintes : les **dépendances** sont respectées ; une **capacité maximale** d'actions simultanées côté PME (5 par défaut, modifiable) évite de surcharger l'entreprise. Le plan est une **proposition** : le conseiller réordonne, et chaque changement est tracé.

## 10. Exemple de Health Check (seed : Boutik Plus Distribution — valeurs illustratives)

```
PME HEALTH CHECK — Boutik Plus Distribution SARL          Diagnostic initial · 15/03/2026

Global : 52/100   Maturité : N2 En structuration   Confiance : 58 %
IMO 47 · IPE 71 → « Performante mais fragile »      Conformité documentaire : 46 %   Risque : 62 (Élevé)
Priorité d'intervention : P2 Renforcée

Formalisation     60  ██████░░░░
Fiscalité         55  █████▌░░░░
CNPS / Social     40  ████░░░░░░  ⚠ SOC-03 non prouvé
Finance           58  █████▊░░░░
Stratégie         45  ████▌░░░░░
Commercial        78  ███████▊░░
Opérations        62  ██████▏░░░
RH & Organisation 35  ███▌░░░░░░
Digital           42  ████▏░░░░░
Risques           30  ███░░░░░░░
Financement       50  █████░░░░░
Innovation        55  █████▌░░░░

TOP 5 PRIORITÉS
1. Régulariser et prouver les déclarations CNPS (SOC-03)                 J1–30   PS 88
2. Mettre en place un contrôle de caisse et une double signature (RIS-02/03)  J1–30   PS 79
3. Tableau de trésorerie mensuel (FIN-03)                                J1–30   PS 74 (gain rapide)
4. Organigramme et fiches de poste (RHO-01/02)                           J31–60  PS 63
5. Réduire la dépendance au 1er client (COM-08) : plan de prospection    J61–90  PS 48
```
Vérification du score global : (60×10 + 55×10 + 40×10 + 58×15 + 45×7 + 78×8 + 62×8 + 35×7 + 42×5 + 30×8 + 50×6 + 55×6) / 100 = **51,8 → 52**.

## 11. Gouvernance du référentiel de scoring

- Toute modification (poids, grilles, bandes, portes) se fait dans un référentiel au statut **DRAFT**, testé sur la seed et sur un échantillon anonymisé (écart de scores affiché avant publication), puis **publié** en nouvelle version.
- Les diagnostics en cours conservent leur version ; les nouveaux diagnostics utilisent la dernière version publiée.
- Les écarts de pondération entre organisations (multi-tenant) sont autorisés ; le **benchmarking inter-organisations** (V3+) ne compare que des PME évaluées avec le **même référentiel**.
