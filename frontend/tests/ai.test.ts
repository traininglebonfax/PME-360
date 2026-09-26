import { describe, expect, it } from "vitest";

import { confidenceTone, fieldInputValue, formatFieldValue, parseFieldValue, parseSse } from "@/lib/ai";

describe("parseSse", () => {
  it("découpe les événements complets et conserve le reste", () => {
    const buffer =
      'event: status\ndata: {"type":"status","text":"Lecture…"}\n\n' +
      'event: delta\ndata: {"type":"delta","text":"Bon"}\n\n' +
      'event: delta\ndata: {"type":"del';
    const { events, rest } = parseSse(buffer);
    expect(events).toEqual([
      { type: "status", text: "Lecture…" },
      { type: "delta", text: "Bon" },
    ]);
    expect(rest).toBe('event: delta\ndata: {"type":"del');
  });

  it("accepte les fins de ligne CRLF", () => {
    const { events } = parseSse('data: {"type":"error","text":"x"}\r\n\r\n');
    expect(events).toEqual([{ type: "error", text: "x" }]);
  });
});

describe("corrections d'extraction", () => {
  it("convertit la saisie selon le type du champ", () => {
    expect(parseFieldValue("12 500 000", "number")).toBe(12500000);
    expect(parseFieldValue("3,5", "number")).toBe(3.5);
    expect(parseFieldValue("12", "integer")).toBe(12);
    expect(parseFieldValue("  ", "string")).toBeNull();
    expect(parseFieldValue("a, b", "list")).toEqual(["a", "b"]);
    expect(parseFieldValue("oui", "boolean")).toBe(true);
  });

  it("affiche et réédite les valeurs", () => {
    expect(formatFieldValue(null, "string")).toBe("—");
    expect(formatFieldValue(["x", "y"], "list")).toBe("x, y");
    expect(fieldInputValue(["x", "y"])).toBe("x, y");
    expect(fieldInputValue(true)).toBe("oui");
  });

  it("colore la confiance selon le seuil", () => {
    expect(confidenceTone(0.95)).toBe("brand");
    expect(confidenceTone(0.88, 0.9)).toBe("warning");
    expect(confidenceTone(0.3)).toBe("danger");
    expect(confidenceTone(null)).toBe("muted");
  });
});
