/**
 * Règles de profil en JSON Logic (Document 8 pour les obligations, Document 5 pour les critères) : « à qui cela
 * s'applique ». Constructeur visuel ↔ JSON Logic stocké ; le serveur valide et reste la référence.
 * Les variables disponibles dépendent du contexte (obligation ou critère du référentiel).
 */

export type VarKind = "number" | "list" | "boolean";

export interface VarDef {
  key: string;
  label: string;
  kind: VarKind;
}

export type NumberOp = ">=" | "<=" | ">" | "<";

export type Clause =
  | { kind: "number"; key: string; op: NumberOp; value: number }
  | { kind: "list"; key: string; values: string[] }
  | { kind: "boolean"; key: string; value: boolean };

/** Profil utilisé par le planificateur d'obligations. */
export const PROFILE_VARIABLES: VarDef[] = [
  { key: "headcount", label: "Effectif", kind: "number" },
  { key: "size_category", label: "Taille", kind: "list" },
  { key: "sector", label: "Secteur", kind: "list" },
  { key: "lifecycle_status", label: "Statut de la PME", kind: "list" },
  { key: "is_company", label: "Société (personne morale)", kind: "boolean" },
];

/** Profil utilisé par le moteur de scoring pour l'applicabilité d'un critère. */
export const CRITERION_VARIABLES: VarDef[] = [
  { key: "headcount", label: "Effectif", kind: "number" },
  { key: "company_age_years", label: "Âge de l'entreprise (années)", kind: "number" },
  { key: "size_category", label: "Taille", kind: "list" },
  { key: "sector", label: "Secteur", kind: "list" },
  { key: "region", label: "Région", kind: "list" },
  { key: "is_company", label: "Société (personne morale)", kind: "boolean" },
  { key: "is_family_business", label: "Entreprise familiale", kind: "boolean" },
  { key: "has_stock", label: "Gère un stock", kind: "boolean" },
  { key: "has_production", label: "Activité de production", kind: "boolean" },
];

export function newClause(key: string, variables: VarDef[] = PROFILE_VARIABLES): Clause {
  const kind = variables.find((v) => v.key === key)?.kind ?? "list";
  if (kind === "number") return { kind, key, op: ">=", value: 1 };
  if (kind === "boolean") return { kind, key, value: true };
  return { kind, key, values: [] };
}

type Logic = Record<string, unknown>;

function parseClause(node: unknown, variables: VarDef[]): Clause | null {
  if (!node || typeof node !== "object" || Array.isArray(node)) return null;
  const entries = Object.entries(node as Logic);
  if (entries.length !== 1) return null;
  const [op, args] = entries[0];
  if (!Array.isArray(args) || args.length !== 2 || typeof args[0] !== "object" || args[0] === null || !("var" in args[0])) return null;
  const key = (args[0] as { var: string }).var;
  const kind = variables.find((v) => v.key === key)?.kind;
  if (kind === "number" && [">=", "<=", ">", "<"].includes(op) && typeof args[1] === "number") {
    return { kind, key, op: op as NumberOp, value: args[1] };
  }
  if (kind === "boolean" && op === "==" && typeof args[1] === "boolean") return { kind, key, value: args[1] };
  if (kind === "list" && op === "in" && Array.isArray(args[1])) return { kind, key, values: args[1].map(String) };
  return null;
}

/** Règle stockée → clauses reliées par ET ; ``null`` si la règle dépasse le constructeur. */
export function parseApplicability(logic: unknown, variables: VarDef[] = PROFILE_VARIABLES): Clause[] | null {
  if (logic === null || logic === undefined) return [];
  const single = parseClause(logic, variables);
  if (single) return [single];
  if (logic && typeof logic === "object" && !Array.isArray(logic)) {
    const entries = Object.entries(logic as Logic);
    if (entries.length === 1 && entries[0][0] === "and" && Array.isArray(entries[0][1])) {
      const clauses = (entries[0][1] as unknown[]).map((node) => parseClause(node, variables));
      if (clauses.every(Boolean)) return clauses as Clause[];
    }
  }
  return null;
}

function toLogic(clause: Clause): Logic {
  if (clause.kind === "number") return { [clause.op]: [{ var: clause.key }, clause.value] };
  if (clause.kind === "boolean") return { "==": [{ var: clause.key }, clause.value] };
  return { in: [{ var: clause.key }, clause.values] };
}

export function buildApplicability(clauses: Clause[]): Logic | null {
  const valid = clauses.filter((c) => c.kind !== "list" || c.values.length > 0);
  if (valid.length === 0) return null;
  return valid.length === 1 ? toLogic(valid[0]) : { and: valid.map(toLogic) };
}

/** Périodicité selon l'effectif : « MENSUELLE si effectif ≥ N, sinon TRIMESTRIELLE ». */
export interface FrequencyByHeadcount {
  threshold: number;
  above: string;
  below: string;
}

export function parseFrequencyRule(logic: unknown): FrequencyByHeadcount | null {
  if (!logic || typeof logic !== "object" || Array.isArray(logic)) return null;
  const args = (logic as Logic).if;
  if (!Array.isArray(args) || args.length !== 3 || typeof args[1] !== "string" || typeof args[2] !== "string") return null;
  const condition = parseClause(args[0], PROFILE_VARIABLES);
  if (!condition || condition.kind !== "number" || condition.key !== "headcount" || condition.op !== ">=") return null;
  return { threshold: condition.value, above: args[1], below: args[2] };
}

export function buildFrequencyRule(rule: FrequencyByHeadcount): Logic {
  return { if: [{ ">=": [{ var: "headcount" }, rule.threshold] }, rule.above, rule.below] };
}

const NUMBER_OPS: Record<NumberOp, string> = { ">=": "au moins", "<=": "au plus", ">": "supérieur à", "<": "inférieur à" };

/** Lecture française (miroir de ``describe_logic`` côté serveur). */
export function describeApplicability(
  clauses: Clause[],
  labels: Record<string, Record<string, string>>,
  variables: VarDef[] = PROFILE_VARIABLES,
  everyone = "Toutes les PME",
): string {
  const parts = clauses
    .filter((c) => c.kind !== "list" || c.values.length > 0)
    .map((c) => {
      const name = variables.find((v) => v.key === c.key)?.label ?? c.key;
      if (c.kind === "number") return `${name} ${NUMBER_OPS[c.op]} ${c.value}`;
      if (c.kind === "boolean") return `${name} égal à ${c.value ? "oui" : "non"}`;
      return `${name} parmi ${c.values.map((v) => labels[c.key]?.[v] ?? v).join(", ")}`;
    });
  return parts.length ? parts.join(" ET ") : everyone;
}
