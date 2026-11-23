import { test, expect } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("dashboard toont lege installatie met onboarding en zonder AI-sleutel", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Vetera Intelligence" })).toBeVisible();
  await expect(page.getByPlaceholder("Wat wil je onderzoeken?")).toBeVisible();
  await expect(page.getByText("Aan de slag")).toBeVisible();
  await expect(page.getByText("AI is niet gekoppeld")).toBeVisible();
  for (const nav of ["Concurrenten", "Voorwaardenvergelijker", "Premielab", "Marktmonitor", "Verbeterradar", "Rapportages", "Bronnen & documenten", "Instellingen"]) {
    await expect(page.getByRole("link", { name: nav })).toBeVisible();
  }
});

test("concurrent en product toevoegen via de interface", async ({ page }) => {
  await page.goto("/concurrenten");
  await page.getByRole("button", { name: "Nieuwe aanbieder" }).click();
  await page.getByLabel("Naam").fill("E2E Testverzekeraar");
  await page.getByRole("button", { name: "Opslaan" }).click();
  await expect(page.getByRole("heading", { name: "E2E Testverzekeraar" })).toBeVisible();
  await page.getByRole("tab", { name: /Producten/ }).click();
  await page.getByRole("button", { name: "Product toevoegen" }).click();
  await page.getByLabel("Productnaam").fill("E2E Oldtimerpolis");
  await page.getByRole("button", { name: "Opslaan" }).click();
  await expect(page.getByText("E2E Oldtimerpolis")).toBeVisible();
  await page.goto("/voorwaarden");
  await expect(page.getByRole("button", { name: /E2E Testverzekeraar · E2E Oldtimerpolis/ })).toBeVisible();
  await expect(page.getByText("Minimale voertuigleeftijd")).toBeVisible();
});

test("premie vastleggen en vergelijken", async ({ page }) => {
  await page.goto("/premielab");
  await page.getByRole("button", { name: "Premie vastleggen" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Aanbieder").selectOption({ label: "E2E Testverzekeraar" });
  await dialog.getByLabel("Premiebedrag (€)").fill("240");
  await dialog.getByRole("button", { name: "Opslaan" }).click();
  await expect(page.getByText("€ 240,00").first()).toBeVisible();
});

test("Excel Import Studio herkent kolommen en valideert", async ({ page }) => {
  await page.goto("/premielab?tab=import");
  const csv = "Verzekeraar;Jaarpremie;Datum;Dekking\nE2E Testverzekeraar;125,50;01-03-2022;WA\nOnbekend BV;abc;01-03-2022;WA\n";
  await page.locator('input[type="file"]').setInputFiles({ name: "premies.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("Kolommen koppelen")).toBeVisible();
  await page.getByRole("button", { name: /Controleren/ }).click();
  await expect(page.getByText("Importresultaat ter goedkeuring")).toBeVisible();
  await expect(page.getByText("geen geldig bedrag")).toBeVisible();
  await page.getByRole("button", { name: /Goedkeuren en 1 rijen importeren/ }).click();
  await expect(page.getByText("1 premies geïmporteerd")).toBeVisible();
});

test("AI-actie toont eerst wat er verstuurd wordt", async ({ page }) => {
  await page.goto("/onderzoek?q=Welke%20concurrenten%20bieden%20een%20collectiepolis");
  await page.getByRole("button", { name: "Analyseer met AI" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Wat wordt verstuurd")).toBeVisible();
  await expect(dialog.getByText("AI is niet beschikbaar")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Versturen en analyseren" })).toBeDisabled();
});
