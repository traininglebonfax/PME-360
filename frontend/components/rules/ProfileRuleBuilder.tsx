"use client";

/**
 * Constructeur visuel d'une règle de profil (« à qui cela s'applique ») : conditions reliées par ET, lecture en
 * français, repli JSON Logic pour les règles avancées. Utilisé par les obligations et par les critères du référentiel.
 */
import { useState } from "react";

import { buildApplicability, type Clause, describeApplicability, newClause, parseApplicability, type VarDef } from "@/lib/profileRules";

export interface RuleState {
  clauses: Clause[];
  /** ``null`` = constructeur visuel ; texte = règle avancée en JSON. */
  json: string | null;
}

export function initialRuleState(logic: unknown, variables: VarDef[]): RuleState {
  const clauses = parseApplicability(logic, variables);
  return clauses ? { clauses, json: null } : { clauses: [], json: logic ? JSON.stringify(logic, null, 2) : "" };
}

/** Règle à envoyer au serveur ; lève une erreur si le JSON avancé est invalide. */
export function ruleValue(state: RuleState): unknown {
  if (state.json === null) return buildApplicability(state.clauses);
  if (!state.json.trim()) return null;
  return JSON.parse(state.json);
}

function safeParse(text: string | null): unknown {
  if (!text?.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return "invalide";
  }
}

export function ProfileRuleBuilder({
  legend,
  variables,
  listOptions,
  state,
  onChange,
  error,
  everyone = "Toutes les PME",
}: {
  legend: string;
  variables: VarDef[];
  listOptions: Record<string, { value: string; label: string }[]>;
  state: RuleState;
  onChange: (state: RuleState) => void;
  error?: string;
  everyone?: string;
}) {
  const [adding, setAdding] = useState("");
  const labels = Object.fromEntries(Object.entries(listOptions).map(([key, options]) => [key, Object.fromEntries(options.map((o) => [o.value, o.label]))]));
  const setClauses = (clauses: Clause[]) => onChange({ ...state, clauses });
  const updateClause = (index: number, clause: Clause) => setClauses(state.clauses.map((c, i) => (i === index ? clause : c)));
  const backToBuilder = parseApplicability(safeParse(state.json), variables);

  return (
    <fieldset className="space-y-2 rounded-lg border border-line p-3">
      <legend className="px-1 text-sm font-medium">{legend}</legend>
      {state.json === null ? (
        <>
          {state.clauses.length === 0 && <p className="text-sm text-muted">{everyone}.</p>}
          {state.clauses.map((clause, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2 text-sm" data-testid="applicability-clause">
              {index > 0 && <span className="text-xs font-semibold text-muted">ET</span>}
              <span className="font-medium">{variables.find((v) => v.key === clause.key)?.label ?? clause.key}</span>
              {clause.kind === "number" && (
                <>
                  <select
                    aria-label="Comparaison"
                    className="rounded-md border border-line px-2 py-1"
                    value={clause.op}
                    onChange={(e) => updateClause(index, { ...clause, op: e.target.value as ">=" })}
                  >
                    <option value=">=">au moins</option>
                    <option value="<=">au plus</option>
                    <option value=">">supérieur à</option>
                    <option value="<">inférieur à</option>
                  </select>
                  <input
                    type="number"
                    min={0}
                    step="any"
                    aria-label="Valeur"
                    className="w-24 rounded-md border border-line px-2 py-1"
                    value={clause.value}
                    onChange={(e) => updateClause(index, { ...clause, value: Number(e.target.value) })}
                  />
                </>
              )}
              {clause.kind === "boolean" && (
                <select
                  aria-label="Valeur"
                  className="rounded-md border border-line px-2 py-1"
                  value={clause.value ? "oui" : "non"}
                  onChange={(e) => updateClause(index, { ...clause, value: e.target.value === "oui" })}
                >
                  <option value="oui">oui</option>
                  <option value="non">non</option>
                </select>
              )}
              {clause.kind === "list" && (
                <span className="flex flex-wrap gap-x-3 gap-y-1">
                  parmi
                  {(listOptions[clause.key] ?? []).map((option) => (
                    <label key={option.value} className="flex items-center gap-1">
                      <input
                        type="checkbox"
                        className="accent-brand-600"
                        checked={clause.values.includes(option.value)}
                        onChange={(e) =>
                          updateClause(index, {
                            ...clause,
                            values: e.target.checked ? [...clause.values, option.value] : clause.values.filter((v) => v !== option.value),
                          })
                        }
                      />
                      {option.label}
                    </label>
                  ))}
                </span>
              )}
              <button type="button" className="text-xs text-red-700 hover:underline" onClick={() => setClauses(state.clauses.filter((_, i) => i !== index))}>
                Retirer
              </button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <select
              aria-label="Ajouter une condition"
              className="rounded-md border border-line px-2 py-1 text-sm"
              value={adding}
              onChange={(e) => {
                if (e.target.value) setClauses([...state.clauses, newClause(e.target.value, variables)]);
                setAdding("");
              }}
            >
              <option value="">+ Ajouter une condition…</option>
              {variables.map((v) => (
                <option key={v.key} value={v.key}>
                  {v.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="text-xs text-muted hover:underline"
              onClick={() => {
                const logic = buildApplicability(state.clauses);
                onChange({ ...state, json: logic ? JSON.stringify(logic, null, 2) : "" });
              }}
            >
              Règle avancée (JSON)
            </button>
          </div>
          <p className="text-xs text-muted" data-testid="applicability-preview">
            Lecture : {describeApplicability(state.clauses, labels, variables, everyone)}
          </p>
        </>
      ) : (
        <>
          <textarea
            aria-label={`${legend} (JSON Logic)`}
            className="h-28 w-full rounded-md border border-line p-2 font-mono text-xs"
            value={state.json}
            onChange={(e) => onChange({ ...state, json: e.target.value })}
            placeholder='{"and": [{">=": [{"var": "headcount"}, 1]}]}'
          />
          <p className="text-xs text-muted">
            Variables : {variables.map((v) => v.key).join(", ")}. Laisser vide pour « {everyone.toLowerCase()} ».
            {backToBuilder && (
              <button type="button" className="ml-2 text-brand-700 hover:underline" onClick={() => onChange({ clauses: backToBuilder, json: null })}>
                Revenir au constructeur
              </button>
            )}
          </p>
        </>
      )}
      {error && (
        <p className="text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
