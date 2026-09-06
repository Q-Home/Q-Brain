# Wijzigingen

## 0.5.0

- Hollama-chat ingebed in de LoxBerry-plugin, met lokale browsergeschiedenis.
- Automatische actuele energiecontext en vaste lokale Ollama-verbinding.
- Achtergrondvragen, annuleren, begrensde context en gedeelde inferencelock.
- Geen extra container, nieuwe openbare poort of uitvoerende modeltools.
- Aangepaste Hollama-broncode, statische bundel en licentievermeldingen meegeleverd.

## 0.4.2

- Compacte modelcontext en korte ontdekkingsantwoorden voor beperkte hardware.
- LoxBerry: één geladen model en één aanvraag tegelijk, 300 seconden analysetimeout.
- Gerichte, geschoonde meldingen voor geheugenproblemen en gestopte modelprocessen.
- Handleiding voor kleiner model op NanoPi R5C.

## 0.4.1

- EnergyManager2: Gpwr/Ppwr/Spwr/Ssoc rechtstreeks herkennen en normaliseren, inclusief omgekeerd laadteken.
- Expliciet ongeldige opslaginputs en meerdere managers blijven onbekend.
- Gevonden globale waarden met eenheden zichtbaar in de plugin.
- Agentstart na modelvoorbereiding; begrensde ontdekkingsantwoorden en gerichte AI-foutmeldingen.
- Lege PHP-detailslijsten maken metingen per apparaat niet langer ongeldig.

## 0.4.0

- Numerieke WebSocket-states voor Meter, Wallbox2 en andere ondersteunde velden, met centrale LoxBerry-credentials.
- Apart lokaal ontdekkingsprofiel qbrain-discovery:latest dat bestaande modelgewichten hergebruikt.
- AI-ontdekking van rollen en ontbrekende informatie, ook zonder complete meetwaarden.
- Analyse per laadpunt en batterij; geen onbewezen optelling, tekenrichting of SOC-conversie.
- Gevalideerde voorstellen in de pluginpagina en MCP-tool analyze_installation.
- Observe-only behouden; model krijgt geen credentials of uitvoerende tools.

## 0.3.3

Certificaat- en hostnaamcontrole uitgeschakeld voor de lokale Miniserver, zowel
via de nieuwere SDK als de LoxBerry 4.0.0-reader. HTTPS blijft behouden wanneer
dit centraal is ingesteld. De controle van update-downloads blijft ongewijzigd.

## 0.3.2

- Ondersteuning voor de PHP SDK van LoxBerry 4.0.0 zonder mshttp_call2.
- Specifieke, geschoonde foutmeldingen voor verbinding, certificaat, rechten en configuratie.
- Eerst het lokale image bouwen; Q-Brain en agent proberen dat image niet meer te downloaden.
- Docker CI start nu beide services na de build, zonder Ollama-modeldownload.

## 0.3.1

- Native LoxBerry-updates ingeschakeld via de stabiele release.cfg-updatebron.
- Het updatebestand verwijst naar het gebouwde installatiepakket, niet naar een broncode-ZIP.
- Eenmalige handmatige upgrade nodig vanaf 0.2.x of 0.3.0; die versies hebben nog geen updatebron.
- Alle SDK- en analysefuncties van 0.3.0 blijven behouden.

## 0.3.0

LoxBerry SDK-koppeling, automatische ontdekking van ondersteunde analoge meetpunten,
periodieke lokale analyse, modeldownload en vereenvoudigde bediening.

## 0.2.1

Automatische installatie van ontbrekende hostdependencies, Docker, Compose en Buildx.
