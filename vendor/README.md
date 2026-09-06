# Hollama-integratie

Upstream: https://github.com/fmaclen/hollama
Basiscommit: 78c63850fa9fdb3dc4ce447c6b0e86c3af926123 (0.35.4)
Licentie: MIT; LICENSE-HOLLAMA.txt en THIRD-PARTY-NOTICES.txt zitten in de webbundel.

hollama-source.zip bevat de aangepaste frontendbroncode en pnpm-lock.yaml.
Node_modules, upstream screenshots/tests, desktopbestanden en ongebruikte losse
fonts zijn weggelaten. hollama-ui.zip is de gebouwde statische distributie.
De pluginbouwer neemt die bundel bytegetrouw op onder webfrontend/htmlauth/chat.

Aanpassingen: statische SvelteKit-hashrouter, relatieve assets, vaste Q-Brain-server,
OllamaStrategy via parent.qbrainChat, korte pollingverzoeken, contextlimiet, beperkte
instellingen en CSP die verbindingen met externe modelservers blokkeert. De
Hollama-interface behoudt naamsvermelding, Markdown-weergave en browsergeschiedenis.

Opnieuw bouwen (Node 22+ en pnpm 11):

1. Pak hollama-source.zip uit in een werkmap.
2. Voer daar `pnpm install --frozen-lockfile --ignore-scripts --shamefully-hoist` uit.
3. Voer `pnpm run build` uit.
4. Voer in de Q-Brain-bronmap `python scripts/package_hollama.py PAD_NAAR_WERKMAP` uit.
5. Bouw de plugin met `python scripts/build_loxberry.py`.

Voor een nieuwe upstreamversie: beoordeel wijzigingen en bouw/test opnieuw. Q-Brain
haalt geen willekeurige laatste Hollama-versie op tijdens installatie.
