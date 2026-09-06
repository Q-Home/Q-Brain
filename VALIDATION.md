# Validatie van Q-Brain 0.4.0

84 tests geslaagd, 2 Linux-specifieke tests overgeslagen op Windows.
Nieuw getest: echte PHP WebSocket-client tegen een TLS-protocolfixture, SHA1/SHA256
JWT-authenticatie, numerieke UUID-tabellen met negatieve waarden, fragmentatie,
ping/pong en tokenintrekking. Modelvoorstellen met verzonnen states en instelsliders
worden geweigerd. Meerdere laadpunten en opslagmeters blijven aparte observaties.
De echte HTTP-MCP-integratie test nu ook discovery zonder bruikbare meetwaarden.
Ollama-antwoorden zijn fixtures; echte modelkwaliteit en de fysieke Miniserver zijn
hiermee nog niet gevalideerd. CI controleert ook PHP/Bash en bouwt/start Docker.

# Validatie van Q-Brain 0.3.3

78 tests geslaagd, 2 Linux-specifieke tests overgeslagen op Windows.
De compatibiliteitsreader is via echte HTTPS getest met een zelfondertekend
certificaat en afwijkende hostnaam. De native SDK-aanroep is gecontroleerd op
uitgeschakelde certificaat- en hostnaamverificatie. Fysieke installatie nog niet getest.

# Validatie van Q-Brain 0.3.2

77 tests geslaagd, 2 Linux-specifieke tests overgeslagen op Windows.
Nieuw: echte HTTP-uitlezing met een oudere SDK zonder mshttp_call2, HTTP 401 en
redirectweigering, geschoonde foutmeldingen en build-volgorde/pullbeleid.
De CI bouwt en start nu Q-Brain plus agent met het lokale image.
De fix is nog niet op de fysieke Miniserver van de gebruiker getest.

De aangeleverde startlog toont een pullpoging voor het lokale Q-Brain-image en
nog lopende Ollama-imagedownload. De SDK mshttp_call2 werd volgens de officiële
LoxBerry-commit e87dbbedffaba928d8a4de88a48efa30e35803d1 pas voor 4.0.1 toegevoegd;
4.0.0.15 heeft deze functie niet. Dit is een compatibiliteitsfout in Q-Brain 0.3.0/0.3.1.

# Validatie van Q-Brain 0.3.1

66 tests geslaagd, 2 Linux-specifieke tests overgeslagen op Windows.
De extra updatefeedtest controleert dat de aangeboden versie en HTTPS-download-URL
naar het gebouwde pluginpakket verwijzen, met dezelfde identiteit en updatebron.
De native update-installatie op de fysieke LoxBerry is nog niet uitgevoerd.

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
