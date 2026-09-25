import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChangeExplanation } from "@/components/scoring/ChangeExplanation";
import { DimensionBars } from "@/components/scoring/HealthCheck";
import { type EngineResult, formatInput, formatMetric, formatPercent, formatScore } from "@/lib/scoring";

describe("formatage des scores et indicateurs", () => {
  it("arrondit les scores et gère les valeurs absentes", () => {
    expect(formatScore(51.8)).toBe("52");
    expect(formatScore("45.2")).toBe("45");
    expect(formatScore(null)).toBe("—");
    expect(formatPercent(0.555)).toBe("56 %");
  });

  it("formate chaque unité d'indicateur", () => {
    expect(formatMetric(0.0512, "PERCENT")).toBe("5,1 %");
    expect(formatMetric(1.234, "RATIO")).toBe("1,23");
    expect(formatMetric(61.4, "DAYS")).toBe("61 jours");
    expect(formatMetric(2.25, "YEARS")).toBe("2,3 ans");
    expect(formatMetric(null, "AMOUNT")).toBe("—");
    expect(formatInput("part_client_1", 30)).toBe("30 %");
    expect(formatInput("ca_n", 1500000)).toMatch(/^1\s500\s000 FCFA$/);
  });
});

describe("visualisations", () => {
  it("affiche les dimensions non évaluables sans barre ni chiffre inventé", () => {
    const result = {
      dimensions: [
        { code: "D01", name: "Formalisation", short_name: "Formalisation", pillar: "A", weight: 10, status: "EVALUE", coverage: 1,
          score: 62, raw_score: 62, confidence: 0.5, not_applicable_share: 0 },
        { code: "D03", name: "Social", short_name: "CNPS / Social", pillar: "A", weight: 10, status: "NON_EVALUABLE", coverage: 0.2,
          score: null, raw_score: 30, confidence: 0.1, not_applicable_share: 0 },
      ],
    } as unknown as EngineResult;
    render(<DimensionBars result={result} />);
    expect(screen.getByText("62")).toBeInTheDocument();
    expect(screen.getByText("Non évaluable")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("explique une évolution avec le signe, pas seulement la couleur", () => {
    render(
      <ChangeExplanation
        explanation={{
          before: { global_score: 54, reference_date: "2025-09-15", framework_version: "1.0.0" },
          after: { global_score: 68, reference_date: "2026-03-15", framework_version: "1.0.0" },
          delta_global: 14,
          other: 0,
          proof_gain: 3,
          reprojected_baseline: false,
          contributions: [
            { dimension: "D01", name: "Formalisation", before: 50, after: 90, contribution: 4.1, criteria: [] },
            { dimension: "D06", name: "Commercial", before: 80, after: 70, contribution: -0.8, criteria: [] },
          ],
        }}
      />,
    );
    expect(screen.getByText("+14,0 points")).toBeInTheDocument();
    expect(screen.getByText("+4,1")).toBeInTheDocument();
    expect(screen.getByText("−0,8")).toBeInTheDocument();
    expect(screen.getByText(/meilleure/)).toBeInTheDocument();
  });
});
