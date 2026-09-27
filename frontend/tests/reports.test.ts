import { describe, expect, it } from "vitest";

import { formatDate } from "@/lib/format";
import { reportLabel } from "@/lib/reports";

const d = formatDate;

describe("reportLabel", () => {
  it("lit une période de suivi ou annuelle", () => {
    expect(reportLabel("SUIVI", "2026-07-01_2026-09-27")).toBe(`Rapport de suivi du ${d("2026-07-01")} au ${d("2026-09-27")}`);
    expect(reportLabel("ANNUEL", "2025-09-28_2026-09-27")).toBe(`Rapport annuel du ${d("2025-09-28")} au ${d("2026-09-27")}`);
    expect(reportLabel("SUIVI", "2026-09-27_2026-09-27")).toBe(`Rapport de suivi du ${d("2026-09-27")}`);
  });

  it("lit une date de diagnostic ou de conformité", () => {
    expect(reportLabel("DIAGNOSTIC", "2026-03-15")).toBe(`Rapport de diagnostic du ${d("2026-03-15")}`);
    expect(reportLabel("CONFORMITE", "2026-09-27")).toBe(`Rapport de conformité au ${d("2026-09-27")}`);
  });
});
