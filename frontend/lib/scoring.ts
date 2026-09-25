/** Types du résultat du moteur de scoring (backend `pme360/scoring/engine.py`) et libellés d'affichage. */

export interface CriterionResult {
  code: string;
  name: string;
  dimension: string;
  lens: "C" | "O" | "P" | "R";
  weight: number;
  is_critical: boolean;
  sector_module: string;
  status: "EVALUE" | "NON_EVALUE" | "NON_APPLICABLE";
  score: number | null;
  level: number | null;
  level_uncapped: number | null;
  capped: boolean;
  proven: boolean;
  source: string | null;
  confidence: number;
  reviewed: boolean;
  effective_weight: number;
  reason?: string;
  metrics?: string[];
}

export interface DimensionResult {
  code: string;
  name: string;
  short_name: string;
  pillar: string;
  weight: number;
  status: "EVALUE" | "PROVISOIRE" | "NON_EVALUABLE" | "EXCLUE";
  coverage: number;
  score: number | null;
  raw_score: number | null;
  confidence: number | null;
  not_applicable_share: number;
}

export interface MetricResult {
  code: string;
  name: string;
  criterion: string | null;
  formula: string;
  unit: "PERCENT" | "RATIO" | "DAYS" | "YEARS" | "AMOUNT";
  inputs: Record<string, number | null>;
  sources: string[];
  value: number | null;
  points: number | null;
  band: string | null;
  confidence: number;
  status: string;
  missing?: string;
}

export interface GateFailure {
  level: number;
  rule: string;
  message: string;
  criteria?: string[];
  dimensions?: string[];
}

export interface Gap {
  criterion: string;
  name: string;
  dimension: string;
  score: number;
  potential_gain: number;
  is_critical: boolean;
  capped: boolean;
}

export interface EngineResult {
  engine_version: string;
  framework_version: string;
  reference_date: string;
  criteria?: CriterionResult[];
  dimensions: DimensionResult[];
  pillars: { code: string; name: string; score: number | null }[];
  lenses: Record<"C" | "O" | "P" | "R", number | null>;
  global_score: number | null;
  imo: number | null;
  ipe: number | null;
  risk_index: number | null;
  confidence: number;
  confidence_label: string;
  maturity: {
    level: number | null;
    level_uncapped: number | null;
    label: string | null;
    message: string | null;
    capped: boolean;
    gates_failed: GateFailure[];
  };
  quadrant: string;
  digital: { index: number | null; label: string | null };
  priority: { priority: string; label: string };
  gaps: Gap[];
  metrics: MetricResult[];
}

export interface ChangeExplanation {
  before: { global_score: number | null; reference_date: string; framework_version: string; original_global_score?: number };
  after: { global_score: number | null; reference_date: string; framework_version: string };
  delta_global: number | null;
  other: number | null;
  proof_gain: number;
  reprojected_baseline: boolean;
  contributions: {
    dimension: string;
    name: string;
    before: number;
    after: number;
    contribution: number;
    criteria: { criterion: string; name: string; before: number; after: number; nature: string; contribution: number }[];
  }[];
}

export const QUADRANT_LABELS: Record<string, string> = {
  CHAMPIONNE_STRUCTUREE: "Championne structurée",
  STRUCTUREE_A_DEVELOPPER: "Structurée, performance à développer",
  PERFORMANTE_FRAGILE: "Performante mais fragile",
  A_CONSOLIDER: "À consolider en priorité",
  NON_DETERMINE: "Performance non évaluée",
};

export const LENS_LABELS: Record<string, string> = {
  C: "Conformité",
  O: "Organisation",
  P: "Performance",
  R: "Maîtrise des risques",
};

export const SOURCE_LABELS: Record<string, string> = {
  DECLARATIF: "Déclaratif PME",
  DECLARATIF_CORROBORE: "Déclaratif corroboré",
  DOCUMENT_VERIFIE: "Document vérifié",
  DOCUMENT_IA: "Document analysé par l'IA",
  INFERE: "Inféré",
  INDICATEURS: "Indicateurs calculés",
  PME: "Réponse de la PME",
  CONSEILLER: "Saisi par le conseiller",
  REPRISE: "Repris du diagnostic précédent",
  IA_PREREMPLI: "Pré-rempli par l'IA",
};

export const PRIORITY_TONES: Record<string, "danger" | "warning" | "neutral" | "brand"> = {
  P1: "danger",
  P2: "warning",
  P3: "neutral",
  P4: "brand",
};

export const PRIORITY_LABELS: Record<string, string> = {
  P1: "P1 · Urgente",
  P2: "P2 · Renforcée",
  P3: "P3 · Standard",
  P4: "P4 · Veille",
};

export const DIMENSION_STATUS_LABELS: Record<string, string> = {
  EVALUE: "Évaluée",
  PROVISOIRE: "Provisoire",
  NON_EVALUABLE: "Non évaluable",
  EXCLUE: "Non applicable",
};

export const DIAGNOSTIC_TYPE_LABELS: Record<string, string> = {
  INITIAL: "Diagnostic initial",
  SUIVI: "Diagnostic de suivi",
  REEVALUATION: "Réévaluation complète",
  CLOTURE: "Diagnostic de clôture",
};

export const DIAGNOSTIC_STATUS_LABELS: Record<string, string> = {
  BROUILLON: "Brouillon",
  EN_COLLECTE: "En collecte",
  ANALYSE_IA: "Analyse IA",
  EN_REVUE: "En revue",
  VALIDE: "Validé",
  ANNULE: "Annulé",
};

export const SNAPSHOT_KIND_LABELS: Record<string, string> = {
  BASELINE: "Référence",
  FOLLOW_UP: "Suivi",
  CLOTURE: "Clôture",
  LIVE: "Courant",
};

const amount = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const ratio = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export function formatScore(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(Math.round(Number(value)));
}

export function formatPercent(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(digits).replace(".", ",")} %`;
}

export function formatAmount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${amount.format(value)} FCFA`;
}

export function formatMetric(value: number | null, unit: MetricResult["unit"]): string {
  if (value === null) return "—";
  switch (unit) {
    case "PERCENT":
      return `${decimal.format(value * 100)} %`;
    case "RATIO":
      return ratio.format(value);
    case "DAYS":
      return `${Math.round(value)} jours`;
    case "YEARS":
      return `${decimal.format(value)} ans`;
    default:
      return formatAmount(value);
  }
}

/** Libellé humain d'une donnée financière (clés `input.*` du référentiel). */
export const INPUT_LABELS: Record<string, string> = {
  ca_n: "CA N",
  ca_n1: "CA N-1",
  ebe: "EBE",
  resultat_net: "Résultat net",
  dotations: "Dotations",
  capitaux_propres: "Capitaux propres",
  total_passif: "Total du bilan",
  dettes_financieres: "Dettes financières",
  actif_circulant: "Actif circulant",
  passif_circulant: "Passif circulant",
  creances_clients: "Créances clients",
  part_client_1: "Part 1er client (%)",
  part_clients_top5: "Part 5 premiers clients (%)",
  part_fournisseur_1: "Part 1er fournisseur (%)",
};

export function formatInput(key: string, value: number | null): string {
  if (value === null) return "non renseigné";
  return key.startsWith("part_") ? `${value} %` : formatAmount(value);
}
