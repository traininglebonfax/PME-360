import { describe, expect, it } from "vitest";

import { ACTION_STATUS, formatCost, PHASES, priorityLabel } from "@/lib/plans";

describe("plans", () => {
  it("classe la priorité PS selon les seuils d'horizon", () => {
    expect(priorityLabel(88).label).toBe("Élevée");
    expect(priorityLabel(55).label).toBe("Moyenne");
    expect(priorityLabel(20).label).toBe("Normale");
  });

  it("affiche le coût estimatif en FCFA", () => {
    expect(formatCost(0, 0)).toBe("Inclus dans l'accompagnement");
    expect(formatCost(0, 500000)).toMatch(/^0 à 500.000 FCFA$/);
  });

  it("donne un libellé PME en langage simple à chaque statut", () => {
    expect(ACTION_STATUS.BLOQUE.pme).toBe("Disponible plus tard");
    expect(Object.values(ACTION_STATUS).every((s) => s.pme.length > 0)).toBe(true);
    expect(PHASES.map((p) => p.key)).toEqual(["J1_30", "J31_60", "J61_90", "M6", "M12"]);
  });
});
