import { describe, expect, it } from "vitest";

import {
  buildApplicability,
  buildFrequencyRule,
  describeApplicability,
  parseApplicability,
  parseFrequencyRule,
} from "@/lib/profileRules";

describe("règles de profil des obligations", () => {
  it("fait l'aller-retour constructeur ↔ JSON Logic", () => {
    const logic = { and: [{ ">=": [{ var: "headcount" }, 5] }, { in: [{ var: "size_category" }, ["PETITE", "MOYENNE"]] }] };
    const clauses = parseApplicability(logic)!;
    expect(clauses).toHaveLength(2);
    expect(buildApplicability(clauses)).toEqual(logic);
    expect(describeApplicability(clauses, { size_category: { PETITE: "Petite", MOYENNE: "Moyenne" } })).toBe(
      "Effectif au moins 5 ET Taille parmi Petite, Moyenne",
    );
  });

  it("une seule condition n'est pas enveloppée dans un ET ; aucune condition = toutes les PME", () => {
    expect(buildApplicability([{ kind: "boolean", key: "is_company", value: true }])).toEqual({ "==": [{ var: "is_company" }, true] });
    expect(buildApplicability([{ kind: "list", key: "sector", values: [] }])).toBeNull();
    expect(parseApplicability(null)).toEqual([]);
    expect(describeApplicability([], {})).toBe("Toutes les PME");
  });

  it("renvoie null pour une règle hors constructeur (OU, NON…)", () => {
    expect(parseApplicability({ or: [{ ">=": [{ var: "headcount" }, 1] }] })).toBeNull();
    expect(parseApplicability("invalide")).toBeNull();
  });

  it("construit et relit la périodicité selon l'effectif", () => {
    const rule = { threshold: 20, above: "MENSUELLE", below: "TRIMESTRIELLE" };
    const logic = buildFrequencyRule(rule);
    expect(logic).toEqual({ if: [{ ">=": [{ var: "headcount" }, 20] }, "MENSUELLE", "TRIMESTRIELLE"] });
    expect(parseFrequencyRule(logic)).toEqual(rule);
    expect(parseFrequencyRule({ if: [{ "<": [{ var: "headcount" }, 20] }, "MENSUELLE", "ANNUELLE"] })).toBeNull();
  });
});
