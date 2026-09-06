# Wijzigingen

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
