# Validatie van deze oplevering

Uitgevoerd op 6 september 2026 met Python 3.12 op Windows:

- **17 tests geslaagd**: `python -m pytest tests -q`.
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

Voor ingebruikname: voer de README-startprocedure op de Q-Box uit, controleer
`/readyz`, vergelijk demo/real snapshots en adviezen, en valideer de Loxone-mappings
in observe-only. Activeer writes pas na de beschreven watchdog- en installatietests.
