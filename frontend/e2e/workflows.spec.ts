import { expect, type Page, test } from "@playwright/test";

import { loginStaff } from "./helpers";

async function openDraft(page: Page) {
  await page.getByRole("link", { name: "Workflows" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  const create = page.getByRole("button", { name: "Modifier (créer un brouillon)" });
  if (await create.isVisible()) await create.click();
  await expect(page.getByTestId("workflow-status")).toBeVisible();
}

test("l'administrateur configure le workflow des actions, contrôlé avant activation", async ({ page }) => {
  const stamp = Date.now().toString().slice(-5);
  await loginStaff(page, "admin@demo.test");
  await openDraft(page);
  const status = page.getByTestId("workflow-status");
  const pmeLabel = page.getByLabel("Libellé PME EN_ATTENTE_PME");
  const original = await pmeLabel.inputValue();

  // Un libellé vide est refusé à l'activation.
  await page.getByLabel("Libellé équipe EN_COURS").fill("");
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  await expect(status.getByText("EN_COURS : libellé obligatoire (60 caractères au plus).")).toBeVisible();
  await page.getByLabel("Libellé équipe EN_COURS").fill("En cours");

  // Nouveau libellé côté PME et motif exigé pour la mise en attente de la PME.
  await pmeLabel.fill(`Nous attendons votre retour ${stamp}`);
  const wait = page.getByTestId("transition-EN_COURS-EN_ATTENTE_PME");
  await wait.getByLabel("Motif obligatoire").check();
  // L'abandon reste obligatoire et non modifiable.
  await expect(page.getByTestId("transition-EN_COURS-ABANDONNE").getByLabel("Motif obligatoire")).toBeDisabled();
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  await expect(page.getByText("Prêt à activer")).toBeVisible();

  await page.getByRole("button", { name: "Activer cette version" }).click();
  await expect(page.getByRole("button", { name: "Modifier (créer un brouillon)" })).toBeVisible();
  await expect(page.getByRole("cell", { name: `Nous attendons votre retour ${stamp}` })).toBeVisible();
  const version = await page.getByText(/En vigueur : version \d+/).textContent();

  // Remise en état de la démo : nouvelle version avec le libellé d'origine.
  await openDraft(page);
  await page.getByLabel("Libellé PME EN_ATTENTE_PME").fill(original);
  await page.getByTestId("transition-EN_COURS-EN_ATTENTE_PME").getByLabel("Motif obligatoire").uncheck();
  await page.getByRole("button", { name: "Activer cette version" }).click();
  await expect(page.getByRole("cell", { name: original, exact: true })).toBeVisible();
  await expect(page.getByText(/En vigueur : version \d+/)).not.toHaveText(version!);
});
