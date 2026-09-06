# Validatie van Q-Brain 0.3.0

Uitgevoerd op 6 september 2026 met Python 3.12 en PHP 8.4 op Windows:

- **65 tests geslaagd, 2 Linux-specifieke tests overgeslagen.**
- Echte PHP SDK-reader uitgevoerd met fixture-LoxBerry-libraries: lijst zonder
  credentials, keuze bij meerdere Miniservers, uitsluitend ontdekte lees-UUIDs,
  scalar/nulwaarde-uitlezing, weigeren van blokoutputs en controle van TLS/timeouts.
- Detectie getest op W/kW/%, dubbele kandidaten, ontbrekende eenheid, kWh,
  polariteit, ongeldige waarden, gedeeltelijke en verouderde telemetrie.
- Volledige MCP-cyclus via lokaal HTTP getest in demo-, gecontroleerde standalone
  write- en SDK-modus. Bearer-beveiliging geldt ook voor het nieuwe overview-endpoint.
- Gedeeltelijke gegevens dwingen lage advieszekerheid en geen EV-vermogensadvies af.
- Rootcontroller: SDK-migratie, credentialvrije containerconfiguratie, read-only
  mount, collector/modelstart, offline aanwezig model en download bij ontbrekend model.
- PHP HTTP-tests: formulier, sessiecookie, CSRF en onbekende acties.
- Bestaande tests voor dependencybootstrap, Docker-argumenten, configuratievalidatie,
  audit, cooldown, onzekere writes, archiefmetadata en behoud van data blijven slagen.
- PHP- en Bash-syntax, pakketopbouw en Python-dependencies gecontroleerd.

De meegeleverde GitHub Actions-workflow voert de tests op Linux uit, controleert
PHP/Bash, bouwt het Docker-image en maakt het plugin-ZIP. Zie de workflow bij de
0.3.0-commit voor het daadwerkelijke buildresultaat.

Nog niet uitgevoerd: 0.3.0 installeren/upgraden/rebooten op fysieke LoxBerry,
SDK-uitlezing op een echte Miniserver en lokale Ollama-inference op de Q-Box.
Fixtures bewijzen het softwarecontract, niet de beschikbaarheid van iedere
Loxone-control via HTTP. Samengestelde energieblokken hebben nog geen reader.

De gebruikerslog HqzgySsqKa.log bevestigt dat **0.2.1 inclusief hostdependencies,
Docker, Compose en Buildx succesvol geïnstalleerd is**. De screenshot toont een
runtime/webinterfaceprobleem; de precieze oorzaak van “Failed to fetch” is niet
bewezen zonder browsernetwerklog. 0.3.0 gebruikt expliciete same-origin API-URLs,
begrensde timeouts en begrijpelijke foutmeldingen.
