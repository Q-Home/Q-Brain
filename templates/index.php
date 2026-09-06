<div class="lb-content" style="max-width:960px;margin:auto">
  <h2>Q-Brain energie-assistent</h2>
  <p>Lokale analyse van je energiegegevens met Loxone en Ollama.</p>
  <p><strong>Observe-only:</strong> deze LoxBerry-versie geeft uitsluitend advies en stuurt geen apparaten aan.</p>
  <div id="notice" role="status" aria-live="polite"></div>
  <section aria-labelledby="status-title">
    <h3 id="status-title">Servicebeheer</h3>
    <p id="service-status">Status wordt geladen…</p>
    <p id="job-status"></p>
    <p id="pending-status"></p>
    <button class="lb-btn lb-btn-primary" type="button" data-operation="start">Start / pas instellingen toe</button>
    <button class="lb-btn" type="button" data-operation="stop">Stop</button>
    <button class="lb-btn" type="button" data-operation="pull">Download ingesteld AI-model</button>
    <p class="lb-form-help">Download het model na de eerste start. Download en opbouw kunnen enkele minuten duren; je kunt deze pagina sluiten.</p>
  </section>
  <form id="settings-form">
    <fieldset id="settings-fields" disabled>
    <legend><h3>Instellingen</h3></legend>
    <div class="lb-form-row">
      <label class="lb-form-label" for="demo_mode">Gegevensbron</label>
      <div class="lb-form-field"><select class="lb-select" id="demo_mode" name="demo_mode">
        <option value="true">Demo — fictieve meetwaarden</option><option value="false">Mijn Loxone-installatie</option>
      </select></div>
    </div>
    <?php
    $fields = [
      ['loxone_url', 'Loxone-adres', 'url', 'https://miniserver.local'],
      ['loxone_username', 'Loxone-gebruikersnaam', 'text', ''],
      ['loxone_password', 'Loxone-wachtwoord', 'password', 'Leeg laten om huidig wachtwoord te behouden'],
      ['loxone_grid_power', 'Netvermogen (W, positief = afname)', 'text', 'Naam of UUID van ingang/uitgang'],
      ['loxone_pv_power', 'PV-vermogen (W)', 'text', 'Naam of UUID van ingang/uitgang'],
      ['loxone_battery_soc', 'Batterijlading (%)', 'text', 'Naam of UUID van ingang/uitgang'],
      ['loxone_battery_power', 'Batterijvermogen (W, positief = laden)', 'text', 'Naam of UUID van ingang/uitgang'],
      ['loxone_ev_power', 'Laadpaalvermogen (W)', 'text', 'Naam of UUID van ingang/uitgang'],
      ['ollama_model', 'Ollama-model', 'text', 'qwen3:4b'],
      ['mcp_port', 'Lokale MCP-poort', 'number', '18080'],
      ['reasoning_interval_seconds', 'Analyse-interval (seconden)', 'number', '300'],
      ['ev_max_power_w', 'Maximaal EV-vermogen voor adviezen (W)', 'number', '11000'],
    ];
    foreach ($fields as [$name, $label, $type, $placeholder]): ?>
    <div class="lb-form-row">
      <label class="lb-form-label" for="<?= $name ?>"><?= htmlspecialchars($label, ENT_QUOTES, 'UTF-8') ?></label>
      <div class="lb-form-field"><input class="lb-input" id="<?= $name ?>" name="<?= $name ?>" type="<?= $type ?>"
          maxlength="512" autocomplete="<?= $type === 'password' ? 'new-password' : 'off' ?>"
          placeholder="<?= htmlspecialchars($placeholder, ENT_QUOTES, 'UTF-8') ?>"></div>
    </div>
    <?php endforeach; ?>
    <div class="lb-form-row">
      <label class="lb-form-label" for="loxone_allow_http">Oudere Miniserver</label>
      <div class="lb-form-field"><label><input type="checkbox" id="loxone_allow_http" name="loxone_allow_http"> Onversleuteld HTTP op lokaal netwerk toestaan</label></div>
    </div>
    <p id="password-status" class="lb-form-help"></p>
    <button class="lb-btn lb-btn-primary" type="submit">Instellingen opslaan</button>
    </fieldset>
  </form>
  <section aria-labelledby="log-title">
    <h3 id="log-title">Laatste beheerbewerking</h3>
    <button class="lb-btn" type="button" id="refresh-log">Log verversen</button>
    <pre id="operation-log" style="white-space:pre-wrap;max-height:20rem;overflow:auto" aria-live="polite"></pre>
  </section>
  <p><a href="https://github.com/Q-Home/Q-Brain/blob/main/docs/LOXBERRY.md" target="_blank" rel="noopener">Installatie, back-up en probleemoplossing</a></p>
</div>
<script>
(() => {
  'use strict';
  const csrf = <?= json_encode($csrf, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
  const form = document.getElementById('settings-form');
  const fields = document.getElementById('settings-fields');
  const notice = document.getElementById('notice');
  const operationButtons = [...document.querySelectorAll('[data-operation]')];
  operationButtons.forEach(b => { b.disabled = true; });
  let configured = false;
  let jobRunning = false;
  async function api(action, payload) {
    const mutate = ['save', 'start', 'stop', 'pull'].includes(action);
    const response = await fetch('index.php?action=' + action, {
      method: mutate ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-QBrain-CSRF': csrf},
      body: mutate ? JSON.stringify(payload || {}) : undefined
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || 'Bewerking mislukt.');
    return data;
  }
  function message(text) { notice.textContent = text; }
  async function loadSettings() {
    const settings = await api('config');
    for (const input of form.elements) {
      if (!input.name || input.name === 'loxone_password') continue;
      if (input.type === 'checkbox') input.checked = settings[input.name] === true;
      else input.value = String(settings[input.name]);
    }
    document.getElementById('password-status').textContent = settings.loxone_password_set ?
      'Er is een wachtwoord opgeslagen. Het wordt niet teruggestuurd naar de browser.' : 'Nog geen Loxone-wachtwoord ingesteld.';
    configured = true;
    fields.disabled = false;
  }
  async function status() {
    const data = await api('status');
    document.getElementById('service-status').textContent = !data.docker_available ?
      'Docker Engine met Compose v2 ontbreekt of is niet bereikbaar.' :
      (data.ready ? 'Gereed — ' + (data.demo_mode ? 'demogegevens' : 'Loxone-gegevens') :
       'Nog niet gereed. Controleer of services draaien, het model is gedownload en Loxone bereikbaar is.');
    jobRunning = data.job.status === 'running';
    document.getElementById('job-status').textContent = data.job.action ?
      'Laatste bewerking: ' + data.job.action + ' — ' + data.job.status : 'Nog geen beheerbewerking uitgevoerd.';
    document.getElementById('pending-status').textContent = data.pending_changes ?
      'Opgeslagen instellingen zijn nog niet toegepast. Gebruik Start / pas instellingen toe.' : '';
    fields.disabled = jobRunning || !configured;
    operationButtons.forEach(b => { b.disabled = jobRunning || !data.docker_available || !configured; });
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const payload = {};
    for (const input of form.elements) {
      if (!input.name) continue;
      payload[input.name] = input.type === 'checkbox' ? input.checked :
        (input.type === 'number' ? Number(input.value) : input.value);
    }
    payload.demo_mode = payload.demo_mode === 'true';
    try {
      fields.disabled = true;
      await api('save', payload);
      form.elements.loxone_password.value = '';
      message('Instellingen opgeslagen. Klik op Start / pas instellingen toe om ze te gebruiken.');
      await loadSettings();
      await status();
    } catch (error) { message(error.message); fields.disabled = false; }
  });
  for (const button of operationButtons) button.addEventListener('click', async () => {
    operationButtons.forEach(b => { b.disabled = true; });
    try { await api(button.dataset.operation); message('Bewerking gestart. Je kunt deze pagina sluiten.'); await status(); }
    catch (error) { message(error.message); await status().catch(() => {}); }
  });
  document.getElementById('refresh-log').addEventListener('click', async () => {
    try { document.getElementById('operation-log').textContent = (await api('logs')).text; }
    catch (error) { message(error.message); }
  });
  // Schedule the next status request after completion; no overlapping polling.
  async function poll() {
    try { await status(); } catch (error) { message(error.message); }
    window.setTimeout(poll, 15000);
  }
  loadSettings().then(poll).catch(error => message(error.message));
})();
</script>
