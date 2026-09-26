import { describe, expect, it } from "vitest";

import { buildCondition, describeCondition, parseCondition, readableTemplate, shortLabel } from "@/lib/ruleBuilder";

const labels = {
  "criterion.COM-01.level": "Connaissance et suivi du portefeuille clients (COM-01) — niveau",
  "criterion.COM-02.level": "Processus de vente et pipeline suivis (COM-02) — niveau",
  "criterion.SOC-03.capped": "Déclarations CNPS (SOC-03) plafonné faute de preuve",
  "dimension.D04.score": "Score Finance (D04)",
};

describe("constructeur de règles", () => {
  it("fait l'aller-retour entre JSON Logic et clauses", () => {
    const stored = { or: [{ "<=": [{ var: "criterion.COM-01.level" }, 2] }, { "<=": [{ var: "criterion.COM-02.level" }, 2] }] };
    const parsed = parseCondition(stored)!;
    expect(parsed.combinator).toBe("or");
    expect(parsed.clauses).toHaveLength(2);
    expect(buildCondition(parsed.combinator, parsed.clauses)).toEqual(stored);
    const single = { "<": [{ var: "dimension.D04.score" }, 60] };
    expect(buildCondition("and", parseCondition(single)!.clauses)).toEqual(single);
  });

  it("renvoie null pour une formule trop complexe (édition technique)", () => {
    expect(parseCondition({ and: [{ or: [{ "<=": [{ var: "x" }, 1] }] }] })).toBeNull();
    expect(parseCondition({ exec: ["rm"] })).toBeNull();
  });

  it("écrit la condition en français", () => {
    const parsed = parseCondition({
      or: [{ "<=": [{ var: "criterion.COM-01.level" }, 2] }, { "==": [{ var: "criterion.SOC-03.capped" }, true] }],
    })!;
    expect(describeCondition(parsed.combinator, parsed.clauses, labels)).toBe(
      "Connaissance et suivi du portefeuille clients (COM-01) — niveau au plus 2 OU Déclarations CNPS (SOC-03) plafonné faute de preuve",
    );
  });

  it("rend les justifications lisibles", () => {
    expect(shortLabel("dimension.D04.score", labels)).toBe("score Finance");
    expect(readableTemplate("Finance à {{dimension.D04.score}}/100, FIN-04 niveau {{criterion.FIN-04.level}}", labels)).toBe(
      "Finance à [score Finance]/100, FIN-04 niveau [niveau FIN-04]",
    );
  });
});
