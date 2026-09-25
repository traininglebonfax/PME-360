# Document 9 — Architecture des tableaux de bord

## 1. Principes

1. **Un tableau de bord par décision** : chaque vue répond aux questions d'un rôle, pas à « tout montrer ».
2. **Aucun chiffre sans définition** : chaque KPI a une info-bulle (formule, périmètre, date de fraîcheur).
3. **Du global au détail en 2 clics** : KPI → liste des PME concernées → fiche PME.
4. **Aucune valeur codée en dur** : tous les chiffres viennent des vues analytiques (Document 3, § 6).
5. **Confiance visible** : les agrégats de scores affichent la confiance moyenne et la part de PME à confiance faible.

## 2. Tableau de bord PME (portail PME, mobile d'abord)

```
┌──────────────────────────────────────────────┐
│  Bonjour Aya 👋   Boutik Plus Distribution   │
├──────────────────────────────────────────────┤
│  [ Jauge 68/100 ]   Niveau : Structurée      │
│  ▲ +16 points depuis le départ (mars 2026)   │
│  Confiance : 74 %  (« Pourquoi ? »)          │
├──────────────────────────────────────────────┤
│  À FAIRE MAINTENANT (3 max)                  │
│  ● Déposer le justificatif CNPS T3 · 15/10   │
│    Pourquoi ? · Comment ? · [Déposer]        │
│  ● Compléter le tableau de trésorerie · 20/10│
│  ● Valider votre organigramme · 31/10        │
├──────────────────────────────────────────────┤
│  CONFORMITÉ 82 %   ██████████░░              │
│  42 conformes · 4 manquants · 2 expirés      │
├──────────────────────────────────────────────┤
│  MES ACTIONS  12 terminées · 5 en cours · 3 en retard │
├──────────────────────────────────────────────┤
│  RETOURS DE GUDE-PME                         │
│  ✔ Organigramme validé                       │
│  ✖ Attestation fiscale : période incorrecte  │
│    → « Merci de déposer l'attestation 2026 » │
├──────────────────────────────────────────────┤
│  PROCHAINES ÉCHÉANCES (calendrier)           │
└──────────────────────────────────────────────┘
```

| Bloc | Donnée | Source |
|---|---|---|
| Score, niveau, progression | Snapshot LIVE vs BASELINE | scoring |
| Actions à faire | Top 3 selon (en retard > échéance proche > PS) | tasks |
| Conformité | Taux + décomptes (Document 8, § 6) | compliance |
| Retours | Dernières décisions sur les documents et livrables, avec motif | documents |
| Échéances | 60 prochains jours | compliance |
| Graphique (onglet « Mon évolution ») | Radar des 12 dimensions (initial vs actuel) + courbe du score global | scoring |

## 3. Tableau de bord conseiller (« Ma journée » + portefeuille)

**Bandeau KPI** : PME suivies · documents à vérifier · actions en retard · alertes ouvertes (par sévérité) · diagnostics à valider · échéances de la semaine.

**File de travail** triée par urgence :

| Priorité de tri | Élément |
|---|---|
| 1 | Alertes CRITIQUES / ÉLEVÉES non prises en compte |
| 2 | Documents « vérification humaine requise » (par ancienneté) |
| 3 | Diagnostics en revue |
| 4 | Actions en retard (côté GUDE en premier) |
| 5 | Livrables à vérifier |

**Tableau du portefeuille** : PME · secteur · niveau · score (+ tendance sur 6 mois) · confiance · conformité · risque · priorité P1 à P4 · actions en retard · dernière activité. Filtres et export CSV.

**Nuage « Maturité × Performance »** : chaque point est une PME (quadrants du Document 6, § 4).

## 4. Tableau de bord GUDE-PME (programme et direction)

### 4.1 Vue d'ensemble : définition des KPI

| KPI | Définition exacte |
|---|---|
| Nombre total de PME | PME non supprimées du périmètre (organisation ou programme) |
| PME nouvellement intégrées | PME dont `onboarding` a commencé dans la période sélectionnée |
| PME accompagnées | PME avec un plan au statut VALIDÉ ou EN_COURS dans la période |
| PME actives / inactives | Activité significative < N jours (60 par défaut) / ≥ N jours |
| Score moyen | Moyenne du score global LIVE des PME ayant un snapshot BASELINE ; la médiane est aussi affichée |
| Progression moyenne | Moyenne de (score LIVE − score BASELINE) pour les PME accompagnées depuis ≥ 3 mois ; les valeurs sont affichées **avec re-projection du référentiel** si nécessaire |
| Conformité moyenne | Moyenne des taux de conformité documentaire |
| PME à risque | Exposition au risque ≥ 50 |
| PME nécessitant une intervention urgente | Priorité P1 |
| PME en retard | ≥ 1 action critique ou obligation en retard |
| Actions réalisées / en retard | Décomptes dans la période |
| Accompagnements par secteur / région / taille | Répartition des PME accompagnées |
| Besoins d'accompagnement | Répartition des recommandations **acceptées** par offre |
| Évolution des scores | Série mensuelle du score moyen par cohorte (entrées alignées sur leur mois d'intégration) |

### 4.2 Analyses de portefeuille (questions du § 16)

| Question | Visualisation | Calcul |
|---|---|---|
| Quels problèmes sont les plus fréquents ? | Barres horizontales triées : « % des PME avec un score < 50 par dimension » et top 10 des critères au niveau ≤ 1 | `mv_portfolio_weaknesses` ; seuil de faiblesse paramétrable |
| Quels accompagnements sont les plus demandés ? | Barres : recommandations acceptées par offre | recommendations |
| Quels accompagnements produisent les plus fortes améliorations ? | Tableau : pour chaque offre, Δ moyen du ou des critères ciblés chez les PME qui l'ont **terminée**, **comparé** au Δ chez les PME éligibles qui ne l'ont pas suivie, avec effectifs et intervalle | `mv_offer_effectiveness`, avec l'avertissement méthodologique (§ 6) |
| Quels secteurs présentent les plus fortes difficultés ? | Heatmap secteur × dimension (score moyen), cellules masquées si n < 5 | |
| Quelles PME nécessitent un accompagnement renforcé ? | Liste P1 / P2 avec motifs | Règles de priorité |
| Quelles PME progressent / stagnent ? | Distribution des Δ + listes « top progressions » et « stagnation » (< +2 points en 6 mois) | `mv_score_trajectories` |
| Quels livrables restent systématiquement non fournis ? | Taux de non-fourniture par type de livrable ou document, et délai moyen de fourniture | deliverables, deadlines |

### 4.3 Carte
Carte des régions de Côte d'Ivoire : nombre de PME, score moyen et part à risque (choroplèthe ; fond de carte à intégrer, par exemple GeoJSON administratif libre de droits).

## 5. Tableau de bord Auditeur (lecture seule)
Journal d'audit filtrable, échantillonnage de dossiers, statistiques de revue humaine vs IA (taux de modification des propositions IA par dimension), export.

## 6. Indicateurs d'impact et méthodologie

### 6.1 Indicateurs suivis
Évolution du score global et des dimensions · progression financière (CA, marge, autonomie) · formalisation (D01) · conformité (taux documentaire, D02, D03) · emplois (effectif déclaré ou justifié par la CNPS, **uniquement si données disponibles**) · évolution du CA · productivité (CA par employé) · maturité digitale (IMD) · accès au financement (financements obtenus déclarés et justifiés) · nouveaux marchés · certifications obtenues · amélioration organisationnelle (lentille O).

### 6.2 Règles de présentation (RM-09 : corrélation ≠ causalité)
- Les tableaux d'impact s'intitulent **« Évolutions observées chez les PME accompagnées »**, et non « Impact de GUDE-PME ».
- Chaque indicateur économique affiche : effectif (n), période, part de données vérifiées vs déclaratives.
- Pour toute analyse de **contribution**, la plateforme propose (V3) :
  1. **Comparaison de cohortes** : PME entrées plus tard dans le programme (liste d'attente) servant de groupe de comparaison au même moment ;
  2. **Différence de différences** simple sur les indicateurs disponibles pour les deux groupes ;
  3. Rappel des **biais connus** : sélection des PME, gain de preuve (Document 6, § 8), conjoncture sectorielle.
- Aucune formulation automatique du type « grâce à GUDE-PME » n'est générée par l'IA ; les prompts l'interdisent explicitement.

## 7. Rapports générés

| Rapport | Destinataire | Contenu | Déclenchement |
|---|---|---|---|
| **Rapport de diagnostic** | PME + GUDE | Les 16 sections du § 34 : présentation, méthodologie, score global, scores par dimension, forces, faiblesses, risques, anomalies, documents manquants, priorités, recommandations, plan, calendrier, indicateurs, conclusion, annexes (indicateurs financiers avec formules, sources, journal de validation) | Validation du diagnostic |
| Rapport de suivi | PME + GUDE | Évolution depuis le dernier rapport, actions, conformité | Trimestriel ou manuel |
| Rapport de conformité | PME + GUDE | État du dossier, échéances, anomalies | Manuel |
| Rapport annuel PME | PME + GUDE | Trajectoire sur 12 mois, explication des écarts | Annuel |
| **Rapport trimestriel de portefeuille** | Direction GUDE, bailleurs | Nombre de PME accompagnées, évolution des scores, principaux problèmes, besoins, actions réalisées ou en retard, progression par secteur et par région, recommandations de pilotage | Trimestriel |

Génération : données figées (`report.data_snapshot`) → sections narratives rédigées par l'IA **à partir des données figées uniquement** → relecture et validation → PDF (WeasyPrint) avec numéro de version, date et mention du niveau de confiance. Le rapport archivé n'est plus modifiable ; une correction produit une nouvelle version.
