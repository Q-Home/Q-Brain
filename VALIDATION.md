# Validatie van Q-Brain 0.2.1

Uitgevoerd op 6 september 2026 met Python 3.12 op Windows:

- **53 tests geslaagd, 2 Linux-specifieke tests overgeslagen**: `python -m pytest tests -q`.
- Dependencybootstrap getest met gesimuleerde hostcommando's: verse installatie,
  bestaande Docker, ontbrekende Compose, pakketconflicten, APT-fouten en onbekende Debian-versie.
  De repository-/signing-keytest en proceslocking draaien daarnaast op Linux CI.
- PHP 8.4: beide PHP-bestanden zonder syntaxfouten; echte HTTP-tests van formulier,
  sessiecookie en CSRF-blokkade met gestubde LoxBerry-libraries.
- Bash-syntax van installatie-, upgrade-, boot- en uninstall-hooks gecontroleerd.
- Plugin-ZIP gecontroleerd op rootmetadata, LF-regels, uitvoerrechten, afwezigheid
  van secrets en correcte opname van de backendbron.
- Controller gecontroleerd op configuratievalidatie, verplichte observe-only,
  behoud van secrets, Docker-argumenten, foutstatus, upgradebehoud en databehoud bij Stop.
- `pip check`: geen conflicterende of ontbrekende dependencies.
- Echt lokaal HTTP-verkeer voor MCP initialize, discovery, tool calls en periodieke agent.
- Beide configuraties getest: standaard observe-only en expliciet toegestane EV-writes.
- Loxone XML-webservices en Ollama chat-antwoorden zijn in tests gesimuleerd.
- Gecontroleerd: bearer-auth, afwezige write-tool in observe-only, inputgrenzen,
  ongeldige meetwaarden, verse data, cooldown, audit en geen retry na onzekere write.

Niet uitgevoerd in deze omgeving:

- Docker image bouwen/starten: Docker is niet geïnstalleerd.
- Echte Ollama-modelinference en prestaties op Q-Box-hardware.
- Aanroepen naar een fysieke Loxone Miniserver, laadpaal of installatie.
- Dependencyinstallatie van 0.2.1 op echte LoxBerry-hardware en upgrade/reboot/uninstall.
- Linux-proceslocking wordt door de meegeleverde GitHub Actions-workflow getest.

Voor ingebruikname: voer de README-startprocedure op de Q-Box uit, controleer
`/readyz`, vergelijk demo/real snapshots en adviezen, en valideer de Loxone-mappings
in observe-only. De LoxBerry-variant ondersteunt uitsluitend observe-only.

De aangeleverde installatielog bevestigt dat 0.2.0 succesvol geïnstalleerd werd op
LoxBerry 4.0.0.15 / aarch64 NanoPi R5S/R5C. De ontbrekende Docker-installatie uit
die log is de aanleiding voor de dependencybootstrap in 0.2.1.
