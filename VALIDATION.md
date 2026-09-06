# Validatie van Q-Brain 0.2.0

Uitgevoerd op 6 september 2026 met Python 3.12 op Windows:

- **47 tests geslaagd, 1 Linux-specifieke test overgeslagen**: `python -m pytest tests -q`.
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
- Een echte LoxBerry-installatie, upgrade, reboot en uninstall.
- Linux-proceslocking wordt door de meegeleverde GitHub Actions-workflow getest.

Voor ingebruikname: voer de README-startprocedure op de Q-Box uit, controleer
`/readyz`, vergelijk demo/real snapshots en adviezen, en valideer de Loxone-mappings
in observe-only. De LoxBerry-variant ondersteunt uitsluitend observe-only.
