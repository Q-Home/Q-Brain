<div class="lb-content" style="max-width:960px;margin:auto">
  <h2>Q-Brain energie-assistent</h2>
  <p><strong>Observe-only:</strong> lokale analyse en advies, zonder apparaten aan te sturen.</p>
  <div id="notice" role="status" aria-live="polite"></div>
  <form id="settings-form">
    <fieldset id="settings-fields" disabled>
      <legend>Je installatie</legend>
      <p id="miniserver-info">LoxBerry-Miniservers worden geladen…</p>
      <div class="lb-form-row" id="miniserver-row" hidden>
        <label class="lb-form-label" for="miniserver_id">Miniserver</label>
        <select class="lb-select" id="miniserver_id" name="miniserver_id"></select>
      </div>
      <p>Q-Brain gebruikt de verbinding uit LoxBerry en zoekt automatisch naar leesbare energiemeetpunten. Je hoeft geen adres of wachtwoord opnieuw in te vullen.</p>
      <details><summary>Geavanceerde instellingen</summary>
        <div class="lb-form-row"><label class="lb-form-label" for="demo_mode">Gegevensbron</label>
          <select class="lb-select" id="demo_mode" name="demo_mode"><option value="false">LoxBerry Miniserver</option><option value="true">Demo — fictieve waarden</option></select></div>
        <?php foreach ([['ollama_model', 'AI-model', 'text'], ['reasoning_interval_seconds', 'Analyse-interval (seconden)', 'number'], ['mcp_port', 'Lokale MCP-poort', 'number']] as [$name, $label, $type]): ?>
        <div class="lb-form-row"><label class="lb-form-label" for="<?= $name ?>"><?= $label ?></label>
          <input class="lb-input" id="<?= $name ?>" name="<?= $name ?>" type="<?= $type ?>" maxlength="128"></div>
        <?php endforeach; ?>
      </details>
      <button class="lb-btn lb-btn-primary" type="submit">Start en analyseer automatisch</button>
    </fieldset>
  </form>
  <p id="service-status">Status wordt geladen…</p><p id="job-status"></p><p id="pending-status"></p>
  <p>De eerste start bouwt de services en downloadt het AI-model. Dit kan enkele minuten duren; je kunt deze pagina sluiten.</p>
  <button class="lb-btn" type="button" id="stop">Stop</button>
  <section><h3>Gevonden energiegegevens</h3><p id="discovery-status"></p>
    <ul id="signals"></ul><details><summary>Gevonden meetpunten en ondersteuning</summary><ul id="readings"></ul></details>
  </section>
  <section><h3>AI-ontdekking van je installatie</h3>
    <p id="discovery-ai">De ontdekkingsassistent onderzoekt je installatie na de start.</p>
    <p id="discovery-ai-time"></p><ul id="discovery-proposals"></ul><ul id="discovery-missing"></ul>
  </section>
  <section><h3>Laatste analyse</h3><p id="advice">Er is nog geen analyse beschikbaar.</p><p id="advice-time"></p></section>
  <section><h3>Installatie- en servicelog</h3><button class="lb-btn" type="button" id="refresh-log">Log verversen</button>
    <pre id="operation-log" style="white-space:pre-wrap;max-height:20rem;overflow:auto"></pre></section>
  <p><a href="https://github.com/Q-Home/Q-Brain/blob/main/docs/LOXBERRY.md">Hulp en ondersteunde meetpunten</a></p>
</div>
<script>
(() => {
  'use strict';
  const csrf = <?= json_encode($csrf, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
  const form = document.getElementById('settings-form');
  const fields = document.getElementById('settings-fields');
  const text = (id, value) => { document.getElementById(id).textContent = value; };
  let configured = false;
  async function api(action, payload) {
    // Ignore any LoxBerry <base> tag. Keep authentication and reverse-proxy prefix.
    const url = new URL(window.location.href);
    if (url.pathname.endsWith('/')) url.pathname += 'index.php';
    url.search = ''; url.hash = ''; url.searchParams.set('action', action);
    const mutate = ['save', 'start', 'stop'].includes(action);
    const abort = new AbortController();
    const timeout = window.setTimeout(() => abort.abort(), 45000);
    try {
      const response = await fetch(url.href, {method: mutate ? 'POST' : 'GET',
        credentials: 'same-origin', cache: 'no-store', signal: abort.signal,
        headers: {'Content-Type': 'application/json', 'X-QBrain-CSRF': csrf},
        body: mutate ? JSON.stringify(payload || {}) : undefined});
      if (!(response.headers.get('content-type') || '').includes('application/json'))
        throw new Error('Geen geldig antwoord van LoxBerry. Herlaad de pagina en controleer of je bent ingelogd.');
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || 'Bewerking mislukt.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('LoxBerry antwoordt niet op tijd. Controleer de servicelog.');
      if (error instanceof TypeError) throw new Error('Verbinding met de pluginpagina mislukt. Herlaad de pagina en controleer de LoxBerry-verbinding.');
      throw error;
    } finally { window.clearTimeout(timeout); }
  }
  async function loadSettings() {
    const data = await api('config');
    const servers = data.miniservers || [];
    const select = form.elements.miniserver_id;
    select.replaceChildren();
    if (servers.length !== 1) select.add(new Option('Kies een Miniserver', ''));
    for (const server of servers) select.add(new Option(server.name, server.id));
    for (const input of form.elements) if (input.name && input.name !== 'miniserver_id') input.value = String(data[input.name]);
    select.value = data.miniserver_id || (servers.length === 1 ? servers[0].id : '');
    document.getElementById('miniserver-row').hidden = servers.length < 2;
    text('miniserver-info', data.sdk_error || (servers.length === 1 ? 'Miniserver: ' + servers[0].name : servers.length ? 'Kies de Miniserver die je wilt analyseren.' : 'Voeg eerst een Miniserver toe in de algemene LoxBerry-instellingen.'));
    configured = true; fields.disabled = false;
  }
  function list(id, rows) {
    const target = document.getElementById(id); target.replaceChildren();
    for (const row of rows) { const li = document.createElement('li'); li.textContent = row; target.append(li); }
  }
  async function status() {
    const data = await api('status');
    text('service-status', data.service_available ? 'Service actief — ' + (data.demo_mode ? 'demogegevens' : 'LoxBerry-gegevens') : 'Service nog niet bereikbaar. Gebruik Start of bekijk de log.');
    text('job-status', data.job.action ? 'Laatste bewerking: ' + data.job.action + ' — ' + data.job.status : '');
    text('pending-status', data.pending_changes ? 'Instellingen nog niet toegepast.' : '');
    fields.disabled = !configured || data.job.status === 'running';
    document.getElementById('stop').disabled = data.job.status === 'running';
    const discovery = data.overview?.discovery || {};
    text('discovery-status', data.sdk?.error || discovery.error || (data.demo_mode ? 'Fictieve demowaarden.' : 'Ontbrekende of dubbelzinnige meetpunten blijven onbekend. Vermogensrichting moet expliciet bekend zijn.'));
    const labels = {grid_power: 'Netvermogen', pv_power: 'Zonnepanelen', battery_soc: 'Batterijlading', battery_power: 'Batterijvermogen', ev_power: 'Laadpaal'};
    const states = {found: 'gevonden', missing: 'niet herkend', ambiguous: 'meerdere kandidaten', invalid: 'ongeldige waarde'};
    list('signals', Object.entries(discovery.signals || {}).map(([key, value]) => labels[key] + ': ' + (states[value.status] || value.status) + (value.value != null ? ' — ' + value.value.toLocaleString() + ' ' + value.unit : '')));
    list('readings', (discovery.readings || []).map(x => x.name + ' (' + x.type + '): ' +
      (x.status === 'read' ? (Object.entries(x.state_values || {}).filter(([,v]) => v !== null).map(([k,v]) => k + '=' + v).join(', ') || String(x.value)) + ' / ' + x.format :
       x.status === 'state_missing' ? 'wacht op actuele Loxone-statuswaarden' : x.status === 'unsupported_control' ? 'alleen metadata beschikbaar' : 'niet leesbaar')));
    if (discovery.websocket?.error) text('discovery-status', 'WebSocket-uitlezing: ' + discovery.websocket.error + '. De AI kan de gevonden configuratie wel onderzoeken.');
    const analysis = data.overview?.installation_analysis;
    text('discovery-ai', analysis ? analysis.payload.summary : (data.overview?.discovery_error?.payload?.message || 'Nog geen ontdekkingsanalyse. Het model wordt voorbereid; de agent probeert automatisch opnieuw.'));
    text('discovery-ai-time', analysis ? 'Model: ' + analysis.payload.model + ' — ' + new Date(analysis.timestamp * 1000).toLocaleString() + ' — voorstellen, geen automatische configuratiewijzigingen' : '');
    list('discovery-proposals', (analysis?.payload?.proposals || []).map(x => x.name + ' / ' + x.state + ' → ' + x.role + ': ' + x.reason));
    list('discovery-missing', analysis?.payload?.missing_information || []);
    const latest = (data.overview?.history || []).find(x => x.kind === 'advice');
    text('advice', latest ? latest.payload.advice.summary : (data.overview?.analysis_error?.payload?.message || 'Nog geen analyse. Q-Brain wacht op leesbare meetwaarden en het AI-model.'));
    text('advice-time', latest ? 'Bron: ' + latest.payload.source + ' — analyse van ' + new Date(latest.timestamp * 1000).toLocaleString() + ' — zekerheid: ' + latest.payload.advice.confidence : '');
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); fields.disabled = true;
    const payload = {loxberry_sdk: true};
    for (const input of form.elements) if (input.name) payload[input.name] = input.type === 'number' ? Number(input.value) : input.value;
    payload.demo_mode = payload.demo_mode === 'true';
    try { await api('save', payload); await api('start'); text('notice', 'Gestart. Modeldownload, gegevens zoeken en analyse verlopen automatisch.'); }
    catch (error) { text('notice', error.message); fields.disabled = false; }
    await status().catch(error => text('notice', error.message));
  });
  document.getElementById('stop').addEventListener('click', async () => {
    try { await api('stop'); await status(); } catch (error) { text('notice', error.message); }
  });
  document.getElementById('refresh-log').addEventListener('click', async () => {
    try { text('operation-log', (await api('logs')).text); } catch (error) { text('notice', error.message); }
  });
  async function poll() {
    try { await status(); } catch (error) { text('notice', error.message); }
    window.setTimeout(poll, 15000);
  }
  loadSettings().then(poll).catch(error => { text('notice', error.message); window.setTimeout(() => location.reload(), 60000); });
})();
</script>
