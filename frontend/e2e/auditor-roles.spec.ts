import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

test("l'auditeur contrôle le journal, vérifie la chaîne et tire un échantillon reproductible", async ({ page }) => {
  const seed = `controle-${Date.now().toString().slice(-6)}`;
  await loginStaff(page, "auditeur@demo.test");
  await page.getByRole("link", { name: "Tableau de bord auditeur" }).click();
  await expect(page.getByRole("heading", { name: "Tableau de bord auditeur" })).toBeVisible();
  await expect(page.getByText("Entrées du journal")).toBeVisible();
  await expect(page.getByRole("list", { name: "Activité par domaine" })).toBeVisible();

  await page.getByRole("button", { name: "Vérifier la chaîne" }).click();
  await expect(page.getByTestId("chain-status")).toContainText("Chaîne intègre");

  await page.getByLabel("Graine (facultatif)").fill(seed);
  await page.getByLabel("Taille").fill("3");
  await page.getByRole("button", { name: "Tirer un échantillon" }).click();
  const sample = page.getByTestId("audit-sample");
  await expect(sample).toContainText(seed);
  const first = await sample.getByRole("link").allTextContents();
  expect(first.length).toBeGreaterThan(0);
  await page.getByLabel("Taille").fill("3");
  await page.getByLabel("Graine (facultatif)").fill("");
  await page.getByLabel("Graine (facultatif)").fill(seed);
  await page.getByRole("button", { name: "Tirer un échantillon" }).click();
  await expect(sample.getByRole("link")).toHaveText(first);

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Exporter le journal (CSV)" }).click();
  expect((await download).suggestedFilename()).toBe("journal-audit.csv");

  // Lecture seule : ni configuration ni gestion des utilisateurs.
  await expect(page.getByRole("link", { name: "Utilisateurs" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Workflows" })).toHaveCount(0);
});

test("l'administrateur crée un rôle personnalisé à partir d'un rôle système puis le supprime", async ({ page }) => {
  const code = `E2E_${Date.now().toString().slice(-6)}`;
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Utilisateurs" }).click();
  await page.getByRole("tab", { name: "Rôles et permissions" }).click();
  await page.getByRole("button", { name: "Partir de Expert" }).click();
  await page.getByLabel("Code").fill(code);
  await page.getByLabel("Libellé").fill("Expert financier externe");
  await page.getByLabel("Utiliser Ask AI").uncheck();
  await page.getByLabel("Consulter le journal d'audit").check();
  await page.getByRole("button", { name: "Créer le rôle" }).click();

  const list = page.getByRole("list", { name: "Rôles personnalisés" });
  const item = list.getByRole("listitem").filter({ hasText: code });
  await expect(item).toContainText("Consulter le journal d'audit");
  await expect(item).not.toContainText("Utiliser Ask AI");

  // Le rôle est proposé à l'invitation.
  await page.getByRole("tab", { name: "Membres et invitations" }).click();
  await expect(page.getByLabel("Rôle").locator("option", { hasText: "Expert financier externe" })).toHaveCount(1);

  await page.getByRole("tab", { name: "Rôles et permissions" }).click();
  await item.getByRole("button", { name: "Supprimer" }).click();
  await item.getByRole("button", { name: "Oui" }).click();
  await expect(list.getByRole("listitem").filter({ hasText: code })).toHaveCount(0);
});
