import { describe, expect, it } from "vitest";

import { checkTemplate, insertVariable, renderTemplate } from "@/lib/notificationTemplates";

describe("modèles de notification", () => {
  it("rend les variables comme le serveur", () => {
    expect(renderTemplate("{pme} : {{ok}} {absent}", { pme: "Alpha" })).toBe("Alpha : {ok} ");
  });

  it("signale variables inconnues et accolades isolées", () => {
    expect(checkTemplate("{pme} {nom}", ["pme"])).toEqual(["Variable(s) inconnue(s) : {nom}."]);
    expect(checkTemplate("Bonjour {pme", ["pme"])).toHaveLength(1);
    expect(checkTemplate("{pme.__class__}", ["pme"])).toHaveLength(1);
    expect(checkTemplate("Plan de {pme}", ["pme"])).toEqual([]);
  });

  it("insère une variable au curseur", () => {
    expect(insertVariable("Bonjour !", "pme", 8, 8)).toEqual({ text: "Bonjour {pme}!", caret: 13 });
  });
});
