import { expect, test } from "@playwright/test";

import { loginPme, loginStaff } from "./helpers";

test("le conseiller lit les indicateurs définis et les analyses de portefeuille", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await expect(page.getByRole("heading", { name: "Vue d'ensemble du portefeuille" })).toBeVisible();
  await expect(page.getByRole("img", { name: /^Définition : PME ayant un plan/ })).toBeVisible();

  await page.getByRole("link", { name: "Analyses détaillées" }).click();
  await expect(page.getByRole("heading", { name: "Analyses de portefeuille" })).toBeVisible();
  for (const title of [
    "Quels problèmes sont les plus fréquents ?",
    "Quels accompagnements sont les plus demandés ?",
    "Quels secteurs présentent les plus fortes difficultés ?",
    "Quelles PME progressent ou stagnent ?",
    "Quelles PME nécessitent un accompagnement renforcé ?",
  ]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
  await expect(page.getByText(/ne prouvent pas, à elles seules, l'effet/)).toBeVisible(); // RM-09
  const heatmap = page.locator("section").filter({ has: page.getByRole("heading", { name: /secteurs/ }) });
  await heatmap.getByRole("button", { name: "Voir le tableau" }).click();
  await expect(heatmap.getByRole("columnheader", { name: "Score moyen" })).toBeVisible();
});

test("le conseiller filtre son portefeuille et l'exporte", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "Portefeuille", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tableau du portefeuille" })).toBeVisible();
  const table = page.getByRole("table").first();
  await expect(table.getByRole("link", { name: "Boutik Plus Distribution SARL" })).toBeVisible();
  await page.getByLabel("Rechercher").fill("Délices");
  await expect(table.getByRole("link", { name: "Boutik Plus Distribution SARL" })).toHaveCount(0);
  await expect(table.getByRole("link", { name: /Délices du Bandama/ })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Exporter en CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(/^portefeuille-.*\.csv$/);
  await expect(page.getByRole("img", { name: /Maturité \(IMO\) en abscisse/ })).toBeVisible();
});

test("le conseiller télécharge le rapport PDF et en édite une nouvelle version", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: /Boutik Plus/ }).first().click();
  await page.getByRole("tab", { name: "Rapports" }).click();
  const list = page.getByRole("list", { name: "Rapports" });
  await expect(list.getByRole("link", { name: "Télécharger le PDF" }).first()).toBeVisible();
  const before = await list.getByRole("listitem").count();
  const download = page.waitForEvent("download");
  await list.getByRole("link", { name: "Télécharger le PDF" }).first().click();
  expect((await download).suggestedFilename()).toMatch(/^rapport-diagnostic-v\d+-.*\.pdf$/);
  await page.getByRole("button", { name: "Éditer une nouvelle version" }).click();
  await expect(list.getByRole("listitem")).toHaveCount(before + 1);
});

test("la dirigeante voit son évolution et récupère son rapport", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  await expect(page.getByRole("heading", { name: "Mon évolution par domaine" })).toBeVisible();
  await expect(page.getByText("Au départ").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Mes rapports" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Télécharger le PDF" }).first().click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
});

test("l'administrateur édite le rapport trimestriel de portefeuille, anonymisé par défaut", async ({ page }) => {
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Rapports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Rapports de portefeuille" })).toBeVisible();
  const list = page.getByRole("list", { name: "Rapports de portefeuille" });
  const before = await list.getByRole("listitem").count().catch(() => 0);
  await page.getByRole("button", { name: "Éditer le rapport" }).click();
  await expect(list.getByRole("listitem")).toHaveCount(before + 1, { timeout: 30_000 });
  const first = list.getByRole("listitem").first();
  await expect(first.getByText("Anonymisé")).toBeVisible();
  const download = page.waitForEvent("download");
  await first.getByRole("link", { name: "Télécharger le PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/^rapport-portefeuille-v\d+-\d{4}-T\d\.pdf$/);
});
