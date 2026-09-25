import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LifecycleBadge } from "@/components/LifecycleBadge";
import { PendingKpi } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatRelative, initials } from "@/lib/format";
import { LIFECYCLE_LABELS, LIFECYCLE_NEXT } from "@/lib/labels";

describe("ApiError", () => {
  it("aplatit les erreurs de validation imbriquées (RFC 9457 + DRF)", () => {
    const error = new ApiError(400, {
      code: "validation_error",
      detail: "Certaines données sont invalides.",
      errors: { legal_name: ["Raison sociale trop courte."], primary_person: { email: ["Adresse invalide."] } },
    });
    expect(error.code).toBe("validation_error");
    expect(error.fieldErrors()).toEqual({
      legal_name: "Raison sociale trop courte.",
      "primary_person.email": "Adresse invalide.",
    });
  });
});

describe("format", () => {
  it("formate les dates relatives en français", () => {
    const now = new Date("2026-09-25T12:00:00Z");
    expect(formatRelative("2026-09-24T12:00:00Z", now)).toBe("hier");
    expect(formatRelative(null, now)).toBe("jamais");
  });

  it("calcule les initiales", () => {
    expect(initials("Konan Brou")).toBe("KB");
    expect(initials("  Aya  ")).toBe("A");
  });
});

describe("cycle de vie", () => {
  it("n'autorise que des transitions vers des statuts connus", () => {
    for (const targets of Object.values(LIFECYCLE_NEXT)) {
      for (const target of targets) expect(LIFECYCLE_LABELS[target]).toBeDefined();
    }
  });

  it("affiche le libellé français du statut", () => {
    render(<LifecycleBadge status="ACCOMPAGNEMENT_ACTIF" />);
    expect(screen.getByText("Accompagnement actif")).toBeInTheDocument();
  });
});

describe("indicateurs en attente", () => {
  it("n'affiche jamais de chiffre inventé", () => {
    render(<PendingKpi label="Score moyen" phase={2} />);
    expect(screen.getByText("Disponible en phase 2")).toBeInTheDocument();
  });
});
