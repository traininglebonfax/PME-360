import { describe, expect, it } from "vitest";

import { DEADLINE_STATUS, DOCUMENT_STATUS, FOLDER_STATE, formatSize } from "@/lib/documents";

describe("formatSize", () => {
  it("affiche octets, Ko et Mo à la française", () => {
    expect(formatSize(512)).toBe("512 o");
    expect(formatSize(2048)).toBe("2 Ko");
    expect(formatSize(3.5 * 1024 * 1024)).toBe("3,5 Mo");
  });
});

describe("libellés", () => {
  it("couvrent les statuts clés du dossier", () => {
    for (const code of ["A_VERIFIER", "CONFORME", "NON_CONFORME", "REJETE_SECURITE"]) expect(DOCUMENT_STATUS[code]?.label).toBeTruthy();
    for (const code of ["CONFORME", "EN_VERIFICATION", "MANQUANT"]) expect(FOLDER_STATE[code]?.label).toBeTruthy();
    for (const code of ["A_FOURNIR", "EN_RETARD", "DISPENSE"]) expect(DEADLINE_STATUS[code]?.label).toBeTruthy();
  });
});
