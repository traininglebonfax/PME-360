import { expect, test } from "@playwright/test";

import { loginPme, loginStaff } from "./helpers";

const CNPS = "Attestation de situation ou de régularité CNPS";

/** PDF texte multi-lignes (lisible par l'extraction, contrairement à un scan). */
function textPdf(lines: string[]): Buffer {
  const backslash = String.fromCharCode(92);
  const escape = (line: string) => [...line].map((c) => (c === "(" || c === ")" || c === backslash ? backslash + c : c)).join("");
  const stream = `BT /F1 11 Tf 14 TL 60 780 Td ${lines.map((line) => `(${escape(line)}) Tj T*`).join(" ")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((offset) => `${offset.toString().padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
}

function cnpsAttestation(): Buffer {
  const today = new Date();
  const fr = (d: Date) => d.toLocaleDateString("fr-FR");
  const issued = new Date(today.getTime() - 10 * 86_400_000);
  const valid = new Date(today.getTime() + 80 * 86_400_000);
  return textPdf([
    "DOCUMENT DE DEMONSTRATION - FICTIF",
    "CAISSE NATIONALE DE PREVOYANCE SOCIALE (fictive)",
    "ATTESTATION DE SITUATION COTISANTE",
    "Numero employeur : DEMO100001",
    "Raison sociale : Boutik Plus Distribution SARL",
    "Effectif declare : 8",
    "Nous certifions que l'entreprise est a jour de ses cotisations sociales.",
    `Date de delivrance : ${fr(issued)}`,
    `Valable jusqu'au : ${fr(valid)}`,
  ]);
}

test("la dirigeante dépose une attestation CNPS, analysée par l'IA à la réception", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  await page.getByRole("link", { name: "Mes documents" }).click();
  const folder = page.locator("section").filter({ has: page.getByRole("heading", { name: "Mon dossier" }) });
  await expect(folder.getByText(/Dossier complet|%/).first()).toBeVisible();
  const cnps = folder.getByRole("listitem").filter({ hasText: CNPS });
  const upload = cnps.locator('input[type="file"]:not([capture])');
  test.skip((await upload.count()) === 0, "Attestation CNPS déjà déposée : relancer seed_demo sur une base neuve.");
  await upload.setInputFiles({ name: "attestation-cnps.pdf", mimeType: "application/pdf", buffer: cnpsAttestation() });
  await expect(cnps.getByText("En vérification")).toBeVisible();
});

test("le conseiller relit la lecture IA d'un document avant de décider", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "Documents à vérifier" }).click();
  await page.getByRole("main").getByRole("list").or(page.getByText("Aucun document en attente")).first().waitFor();
  const item = page.getByRole("link").filter({ hasText: "Attestation" }).filter({ hasText: "CNPS" }).filter({ hasText: "Boutik Plus" });
  test.skip((await item.count()) === 0, "Aucune attestation CNPS de Boutik Plus en attente : lancer d'abord le test de dépôt.");
  await expect(item.first().getByText(/IA : /)).toBeVisible();
  await item.first().click();

  const extraction = page.getByTestId("extraction-card");
  await expect(extraction).toBeVisible();
  await expect(extraction.getByText("N° employeur CNPS")).toBeVisible();
  await expect(extraction.getByText("DEMO100001")).toBeVisible();

  const validate = extraction.getByRole("button", { name: "Valider la lecture" });
  if (await validate.isVisible()) {
    // Une correction exige une justification (RM-06).
    await extraction.getByRole("button", { name: "Corriger" }).click();
    await extraction.getByLabel("Effectif déclaré").fill("9");
    await expect(extraction.getByLabel(/Justification de la correction/)).toHaveAttribute("required", "");
    await extraction.getByLabel(/Justification de la correction/).fill("Effectif confirmé par la DISA du trimestre.");
    await extraction.getByRole("button", { name: "Enregistrer les corrections" }).click();
    await expect(extraction.getByText("corrigé")).toBeVisible();
  }
  await expect(extraction.getByText(/Revue par/)).toBeVisible();
  // La lecture IA ne décide pas de la conformité : la décision humaine reste à prendre.
  await expect(page.getByRole("button", { name: "Enregistrer la décision" })).toBeVisible();
});

test("le conseiller consulte les finances et interroge le Copilot sur une PME", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: /Délices/ }).first().click();
  await page.getByRole("tab", { name: "Finances" }).click();
  await expect(page.getByRole("heading", { name: "États financiers" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Indicateurs au/ })).toBeVisible();
  const draft = page.getByRole("button", { name: "Rédiger un commentaire" });
  if (await draft.isEnabled()) {
    await draft.click();
    await expect(page.getByTestId("interpretation").getByText("Brouillon à relire")).toBeVisible();
  }

  await page.getByRole("link", { name: "Poser une question" }).click();
  await expect(page.getByRole("heading", { name: "Copilot" })).toBeVisible();
  await page.getByRole("button", { name: "Quels documents manquent ou sont expirés ?" }).click();
  const answer = page.getByTestId("assistant-answer").last();
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer.getByText(/Confiance (élevée|moyenne|faible)/)).toBeVisible();
  await expect(page).toHaveURL(/conversation=/);

  // Question de suivi dans la même conversation.
  await page.getByLabel("Votre question").fill("Quelles échéances arrivent dans les 30 prochains jours ?");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByTestId("assistant-answer")).toHaveCount(2, { timeout: 30_000 });
});

test("l'administrateur règle la politique IA, lance l'évaluation et trace une analyse", async ({ page }) => {
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Intelligence artificielle" }).click();
  await expect(page.getByRole("heading", { name: "Intelligence artificielle" })).toBeVisible();
  await expect(page.getByText("Politique IA de l'organisation")).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Paramètres enregistrés")).toBeVisible();

  await page.getByRole("button", { name: "Lancer l'évaluation" }).click();
  await expect(page.getByText("Seuils atteints")).toBeVisible({ timeout: 60_000 });

  const firstAnalysis = page.getByRole("table").last().getByRole("link").first();
  test.skip((await firstAnalysis.count()) === 0, "Aucune analyse tracée.");
  await firstAnalysis.click();
  await expect(page.getByRole("heading", { name: "Traçabilité" })).toBeVisible();
  await expect(page.getByText("Prompt")).toBeVisible();
});
