/**
 * Constructeur visuel des règles de recommandation (Document 7, § 3.3) : « SI … ET/OU … ALORS proposer … ».
 * Traduit des clauses simples en JSON Logic (le format stocké) et inversement ; miroir de
 * ``pme360/plans/rule_labels.py`` pour l'aperçu en direct (le serveur reste la référence).
 */

export type VariableType = "score" | "level" | "boolean" | "rate" | "count" | "maturity";

export interface RuleVariable {
  key: string;
  label: string;
  type: VariableType;
  group: string;
}

export type Operator = "<=" | "<" | ">=" | ">" | "==" | "!=";
export type Combinator = "and" | "or";

export interface Clause {
  key: string;
  op: Operator;
  value: number | boolean;
}

export const OPERATOR_LABELS: Record<Operator, string> = {
  "<=": "au plus",
  "<": "inférieur à",
  ">=": "au moins",
  ">": "supérieur à",
  "==": "égal à",
  "!=": "différent de",
};

export const COMBINATOR_LABELS: Record<Combinator, string> = { and: "ET", or: "OU" };

/** Bornes et pas de saisie d'une valeur selon le type de variable. */
export function valueRange(type: VariableType): { min: number; max: number; step: number } {
  switch (type) {
    case "level":
      return { min: 0, max: 4, step: 1 };
    case "maturity":
      return { min: 1, max: 5, step: 1 };
    case "rate":
      return { min: 0, max: 1, step: 0.05 };
    case "count":
      return { min: 0, max: 100, step: 1 };
    default:
      return { min: 0, max: 100, step: 1 };
  }
}

export function defaultClause(variable: RuleVariable): Clause {
  if (variable.type === "boolean") return { key: variable.key, op: "==", value: true };
  if (variable.type === "maturity") return { key: variable.key, op: ">=", value: 3 };
  if (variable.type === "level") return { key: variable.key, op: "<=", value: 1 };
  if (variable.type === "rate") return { key: variable.key, op: "<", value: 0.5 };
  return { key: variable.key, op: "<", value: 50 };
}

type Logic = Record<string, unknown>;

function isComparison(node: unknown): node is Logic {
  if (!node || typeof node !== "object" || Array.isArray(node)) return false;
  const entries = Object.entries(node);
  if (entries.length !== 1) return false;
  const [op, args] = entries[0];
  return (
    op in OPERATOR_LABELS &&
    Array.isArray(args) &&
    args.length === 2 &&
    typeof args[0] === "object" &&
    args[0] !== null &&
    "var" in (args[0] as object) &&
    (typeof args[1] === "number" || typeof args[1] === "boolean")
  );
}

function toClause(node: Logic): Clause {
  const [op, args] = Object.entries(node)[0] as [Operator, [{ var: string }, number | boolean]];
  return { key: args[0].var, op, value: args[1] };
}

/** Condition stockée → clauses éditables ; ``null`` si elle dépasse le constructeur (édition technique). */
export function parseCondition(condition: unknown): { combinator: Combinator; clauses: Clause[] } | null {
  if (isComparison(condition)) return { combinator: "and", clauses: [toClause(condition)] };
  if (condition && typeof condition === "object" && !Array.isArray(condition)) {
    const entries = Object.entries(condition);
    if (entries.length === 1 && (entries[0][0] === "and" || entries[0][0] === "or") && Array.isArray(entries[0][1])) {
      const items = entries[0][1] as unknown[];
      if (items.length > 0 && items.every(isComparison)) {
        return { combinator: entries[0][0] as Combinator, clauses: items.map((item) => toClause(item as Logic)) };
      }
    }
  }
  return null;
}

/** Clauses → JSON Logic (format stocké et exécuté par le serveur). */
export function buildCondition(combinator: Combinator, clauses: Clause[]): Logic {
  const logic = clauses.map((c) => ({ [c.op]: [{ var: c.key }, c.value] }));
  return logic.length === 1 ? logic[0] : { [combinator]: logic };
}

function formatValue(value: number | boolean): string {
  if (value === true) return "oui";
  if (value === false) return "non";
  return String(value).replace(".", ",");
}

/** Phrase française d'une clause (miroir de ``describe`` côté serveur). */
export function describeClause(clause: Clause, labels: Record<string, string>): string {
  const label = labels[clause.key] ?? clause.key;
  if (clause.value === true && clause.op === "==") return label;
  return `${label} ${OPERATOR_LABELS[clause.op]} ${formatValue(clause.value)}`;
}

export function describeCondition(combinator: Combinator, clauses: Clause[], labels: Record<string, string>): string {
  return clauses.map((c) => describeClause(c, labels)).join(` ${COMBINATOR_LABELS[combinator]} `);
}

const SHORT_GENERAL: Record<string, string> = {
  global_score: "score global",
  risk_index: "exposition au risque",
  imo: "IMO",
  ipe: "IPE",
  maturity_level: "niveau de maturité",
  compliance_rate: "taux de conformité",
  "deadlines.overdue.count": "obligations en retard",
};

/** Libellé court d'une variable dans une justification (miroir de ``short_label``). */
export function shortLabel(key: string, labels: Record<string, string>): string {
  if (SHORT_GENERAL[key]) return SHORT_GENERAL[key];
  const parts = key.split(".");
  if (parts.length === 3 && parts[0] === "criterion") return parts[2] === "level" ? `niveau ${parts[1]}` : `${parts[1]} plafonné`;
  if (parts.length === 3 && parts[0] === "dimension") {
    const match = /^Score (.+) \(D\d{2}\)$/.exec(labels[key] ?? "");
    return match ? `score ${match[1]}` : `score ${parts[1]}`;
  }
  return labels[key] ?? key;
}

/** Gabarit de justification → texte lisible, les valeurs devenant « [niveau COM-01] ». */
export function readableTemplate(template: string, labels: Record<string, string>): string {
  return template.replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key: string) => `[${shortLabel(key, labels)}]`);
}
