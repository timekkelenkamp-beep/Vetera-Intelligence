# Vetera Intelligence online zetten (Render)

Hiermee draait de app op internet en open je hem met een gewone link in elke browser, beveiligd met een
wachtwoord. Je hoeft niets op je eigen computer te installeren.

**Kosten (indicatief):** Render *Starter* ongeveer $7 per maand plus opslag van ongeveer $0,25 per GB per maand.
De database, documenten en back-ups staan op een vaste schijf van 1 GB (later uit te breiden).

**Let op privacy:** online staan de gegevens bij Render (regio Frankfurt) in plaats van op je eigen computer.
Gaan er interne Vetera-documenten of niet-openbare premiegegevens in, overleg dan eerst met IT of compliance.

## Stappen (ongeveer 10 minuten)

1. **Account aanmaken** op https://render.com (inloggen met GitHub is het makkelijkst).
2. Klik rechtsboven op **New → Blueprint**.
3. **Koppel GitHub** als Render daarom vraagt en geef toegang tot de repository
   `timekkelenkamp-beep/Vetera-Intelligence`.
4. Kies de repository. Kies bij **Branch** `claude/vetera-intelligence-platform-7y23zw`
   (of `main`, als de code daarnaartoe is samengevoegd). Render leest het bestand `render.yaml` en toont één
   web service *vetera-intelligence* met een schijf.
5. Vul de gevraagde waarden in:
   - **VETERA_APP_PASSWORD** — het wachtwoord waarmee jij (en collega's) inloggen. Kies een lang wachtwoord,
     bijvoorbeeld vier losse woorden.
   - **ANTHROPIC_API_KEY** — optioneel, voor de AI-functies. Leeg laten mag.
   - *VETERA_SESSION_SECRET* maakt Render zelf aan; daar hoef je niets mee.
6. Klik op **Apply** (of *Deploy Blueprint*). De eerste keer bouwen duurt een paar minuten.
7. Open de link die Render toont, iets als `https://vetera-intelligence.onrender.com`, en log in met je
   wachtwoord.

## Daarna

- **Updates:** elke nieuwe versie op de gekozen branch wordt automatisch opnieuw uitgerold. Je gegevens blijven
  staan (ze staan op de schijf, niet in de app zelf).
- **Wachtwoord wijzigen:** Render → *vetera-intelligence* → **Environment** → `VETERA_APP_PASSWORD` aanpassen →
  *Save*. Iedereen moet daarna opnieuw inloggen.
- **AI-sleutel later toevoegen:** zelfde plek, variabele `ANTHROPIC_API_KEY`.
- **Wekelijkse broncontrole:** gebeurt online automatisch; de server kijkt elk uur of een controle aan de beurt is.
- **Back-up:** in de app via *Instellingen → Data & back-up*. Download de ZIP regelmatig naar een veilige plek.
- **Eigen domeinnaam** (bijv. `intelligence.vetera.nl`): Render → *Settings → Custom Domains*.

## Beveiliging

- Alles achter het wachtwoord; zonder ingesteld wachtwoord blokkeert de app alle toegang.
- Versleutelde verbinding (HTTPS) via Render; sessiecookie is HttpOnly en Secure en verloopt na 30 dagen.
- Maximaal 8 foute inlogpogingen per 5 minuten per IP-adres.
- Er is één gedeeld wachtwoord, geen gebruikersbeheer. Deel het alleen met mensen die toegang mogen hebben.

## Lokaal blijft ook werken

`install.bat` en `start.bat` werken nog steeds. Lokaal is er geen wachtwoord nodig, omdat de app dan alleen
vanaf je eigen computer bereikbaar is.
