import { describe, expect, it } from "vitest";

import { DEFAULT_BRAND, orgLabel, palette } from "@/lib/brand";

describe("marque blanche", () => {
  it("dérive une palette claire → foncée de la couleur principale", () => {
    const colors = palette("#0055A4");
    expect(colors["600"]).toBe("#0055A4");
    expect(colors["50"]).toBe("#edf3f9");
    expect(colors["800"]).toBe("#003669");
  });

  it("identité neutre PME360 par défaut, sans nom d'organisation", () => {
    expect(DEFAULT_BRAND.product_name).toBe("PME360");
    expect(orgLabel(DEFAULT_BRAND)).toBe("l'équipe");
    expect(orgLabel({ ...DEFAULT_BRAND, short_name: "Banque Atlantique" })).toBe("Banque Atlantique");
  });
});
