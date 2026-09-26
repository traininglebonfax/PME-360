/**
 * Règles de profil des obligations (Document 8) : « à qui s'applique l'obligation » et « à quelle périodicité ».
 * Constructeur visuel ↔ JSON Logic stocké (le serveur valide et reste la référence).
 */

export type ProfileVar = "headcount" | "size_category" | "sector" | "lifecycle_status" | "is_company";

export type Clause =
  | { kind: "number"; key: "headcount"; op: ">=" | "<=" | ">" | "<"; value: number }
  | { kind: "list"; key: "size_category" | "sector" | "lifecycle_status"; values: string[] }
  | { kind: "boolean"; key: "is_company"; value: boolean };

export const PROFILE_VARIABLES: { key: ProfileVar; label: string }[] = [
  { key: "headcount", label: "Effectif" },
  { key: "size_category", label: "Taille" },
  { key: "sector", label: "Secteur" },
  { key: "lifecycle_status", label: "Statut de la PME" },
  { key: "is_company", label: "Société (personne morale)" },
];

export function newClause(key: ProfileVar): Clause {
  if (key === "headcount") return { kind: "number", key, op: ">=", value: 1 };
  if (key === "is_company") return { kind: "boolean", key, value: true };
  return { kind: "list", key, values: [] };
}

type Logic = Record<string, unknown>;

function parseClause(node: unknown): Clause | null {
  if (!node || typeof node !== "object" || Array.isArray(node)) return null;
  const entries = Object.entries(node as Logic);
  if (entries.length !== 1) return null;
  const [op, args] = entries[0];
  if (!Array.isArray(args) || args.length !== 2 || typeof args[0] !== "object" || args[0] === null || !("var" in args[0])) return null;
  const key = (args[0] as { var: string }).var;
  if (key === "headcount" && [">=", "<=", ">", "<"].includes(op) && typeof args[1] === "number") {
    return { kind: "number", key, op: op as ">=", value: args[1] };
  }
  if (key === "is_company" && op === "==" && typeof args[1] === "boolean") return { kind: "boolean", key, value: args[1] };
  if (["size_category", "sector", "lifecycle_status"].includes(key) && op === "in" && Array.isArray(args[1])) {
    return { kind: "list", key: key as "sector", values: args[1].map(String) };
  }
  return null;
}

/** Applicabilité stockée → clauses reliées par ET ; ``null`` si la règle dépasse le constructeur. */
export function parseApplicability(logic: unknown): Clause[] | null {
  if (logic === null || logic === undefined) return [];
  const single = parseClause(logic);
  if (single) return [single];
  if (logic && typeof logic === "object" && !Array.isArray(logic)) {
    const entries = Object.entries(logic as Logic);
    if (entries.length === 1 && entries[0][0] === "and" && Array.isArray(entries[0][1])) {
      const clauses = (entries[0][1] as unknown[]).map(parseClause);
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
  const condition = parseClause(args[0]);
  if (!condition || condition.kind !== "number" || condition.op !== ">=") return null;
  return { threshold: condition.value, above: args[1], below: args[2] };
}

export function buildFrequencyRule(rule: FrequencyByHeadcount): Logic {
  return { if: [{ ">=": [{ var: "headcount" }, rule.threshold] }, rule.above, rule.below] };
}

const NUMBER_OPS: Record<string, string> = { ">=": "au moins", "<=": "au plus", ">": "supérieur à", "<": "inférieur à" };

/** Lecture française de l'applicabilité (miroir de ``describe_logic`` côté serveur). */
export function describeApplicability(clauses: Clause[], labels: Partial<Record<ProfileVar, Record<string, string>>>): string {
  const parts = clauses
    .filter((c) => c.kind !== "list" || c.values.length > 0)
    .map((c) => {
      const name = PROFILE_VARIABLES.find((v) => v.key === c.key)?.label ?? c.key;
      if (c.kind === "number") return `${name} ${NUMBER_OPS[c.op]} ${c.value}`;
      if (c.kind === "boolean") return `${name} égal à ${c.value ? "oui" : "non"}`;
      return `${name} parmi ${c.values.map((v) => labels[c.key]?.[v] ?? v).join(", ")}`;
    });
  return parts.length ? parts.join(" ET ") : "Toutes les PME";
}
