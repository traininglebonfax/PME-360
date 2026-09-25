# Décisions ouvertes et registre des choix

Ce fichier recense les **choix structurants** à valider avant de lancer la phase 1, ainsi que les hypothèses retenues par défaut. Chaque décision validée est ensuite consignée en ADR (Document 2, § 12) avec sa date et son décideur.

## 1. Décisions à trancher avant la phase 1

| ID | Décision | Recommandation | Alternatives | Impact si non tranché |
|---|---|---|---|---|
| **D-01** | Stack technique | Django/DRF + Next.js + PostgreSQL (ADR-002) | NestJS de bout en bout ; Laravel | Bloque la phase 1 |
| **D-02** | Hébergement de production | Hébergeur ou datacenter **en Côte d'Ivoire** si l'offre couvre stockage objet, sauvegardes et supervision ; sinon cloud international avec formalités de transfert | Cloud international (Europe) ; hybride (données en CI, calcul IA à l'étranger) | Bloque le pilote (formalités de protection des données) |
| **D-03** | Usage d'un LLM hébergé hors de Côte d'Ivoire | Autorisé avec pseudonymisation, types de documents sensibles exclus, fournisseur sans entraînement sur les données, paramètre par tenant | Modèle auto-hébergé (qualité moindre, coût GPU) ; IA limitée à l'OCR et aux règles | Bloque la phase 4 |
| **D-04** | Validation du référentiel GUDE-360 v1 (12 dimensions, poids, critères) | Atelier de 2 demi-journées avec 3 à 5 conseillers et 1 expert-comptable | — | Bloque la seed de la phase 2 |
| **D-05** | Nomenclature des niveaux de maturité | Fragile / En structuration / Structurée / Maîtrisée / Prête pour la croissance | Libellés du cahier des charges (Émergent, Mature) | Faible (configurable) |
| **D-06** | Vérification réglementaire | Mandater un juriste et un expert-comptable ivoiriens pour valider le registre (Document 8, § 2) | — | Bloque l'activation des obligations réglementaires |
| **D-07** | Canal d'authentification des PME | E-mail + OTP (MVP), SMS OTP en V1 | Mot de passe seul | Faible |
| **D-08** | Langue | Français uniquement (MVP) ; i18n prévue dans le code | — | Faible |

### 1.1 Arbitrage du 25/09/2026

Le porteur du projet a **accepté l'ensemble des recommandations** (D-01 à D-08) le 25/09/2026 pour lancer la phase 1. Statut : **retenu à titre provisoire**, en attente de validation formelle par GUDE-PME. Conséquences :

- D-01 : la phase 1 est développée en Django/DRF + Next.js + PostgreSQL (ADR-002 → *Accepté (provisoire)*).
- D-02 et D-03 restent à **instruire** (offres d'hébergement en Côte d'Ivoire, formalités de protection des données) avant le pilote ; elles n'affectent pas le code de la phase 1, conçu pour tourner dans les deux cas.
- D-04 et D-06 : le référentiel GUDE-360 v1 et le registre réglementaire sont chargés en seed avec leurs statuts « à valider » / « à vérifier ».

## 2. Hypothèses retenues par défaut

- Plusieurs milliers de PME à terme ; dimensionnement pour 5 000 PME actives.
- Les PME utilisent majoritairement un smartphone ; les conseillers, un ordinateur.
- GUDE-PME fournit un product owner disponible au moins 2 jours par semaine.
- Aucune intégration avec les systèmes de la DGI, de la CNPS ou du CEPICI au MVP (pas d'API officielle supposée).
- Devise unique XOF.
- La plateforme **vérifie des preuves** : elle ne certifie pas une conformité légale.

## 3. Données de démonstration
Toutes les données de seed sont fictives (préfixe `DEMO-` pour les identifiants). Aucune donnée réelle n'est utilisée hors de la production.
