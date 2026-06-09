/**
 * Flight Price Tracker — minimalist SPA
 */

import './src/style.css';
import { Capacitor } from '@capacitor/core';
import { Browser } from '@capacitor/browser';
import { PushNotifications } from '@capacitor/push-notifications';

const STORAGE_API = 'flightTrackerApiBase';
const STORAGE_EMAIL = 'flightTrackerEmail';
const STORAGE_DEVICE_TOKEN = 'flightTrackerDeviceToken';
const STORAGE_TOKEN = 'flightTrackerAuthToken';
const IS_PRODUCTION_BUILD = import.meta.env.PROD && Boolean(import.meta.env.VITE_API_BASE_URL);

const CURRENCY_FORMAT = {
  USD: { symbol: '$', decimals: 2, position: 'before' },
  EUR: { symbol: '€', decimals: 2, position: 'before' },
  GBP: { symbol: '£', decimals: 2, position: 'before' },
  BGN: { symbol: 'лв', decimals: 2, position: 'after' },
  HUF: { symbol: 'Ft', decimals: 0, position: 'after' },
  JPY: { symbol: '¥', decimals: 0, position: 'before' },
};

/** @type {string[]} */
let supportedCurrencies = ['USD', 'EUR', 'GBP', 'BGN', 'HUF', 'JPY'];

/** @type {Record<string, string>} */
let stopsLabels = {
  any: 'Any',
  direct: 'Direct',
  connecting: 'Layover',
};

function getDefaultApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured.replace(/\/$/, '');

  if (Capacitor.isNativePlatform()) {
    if (Capacitor.getPlatform() === 'android') {
      return 'http://10.0.2.2:8000/api';
    }
    return 'http://localhost:8000/api';
  }
  if (import.meta.env.DEV) {
    return '/api';
  }
  if (window.location.protocol === 'file:' || !window.location.hostname) {
    return 'http://localhost:8000/api';
  }
  return `${window.location.origin}/api`;
}

function getApiBase() {
  if (IS_PRODUCTION_BUILD) return getDefaultApiBase();
  const saved = localStorage.getItem(STORAGE_API);
  if (saved) return saved.replace(/\/$/, '');
  return getDefaultApiBase();
}

function getAuthToken() {
  return localStorage.getItem(STORAGE_TOKEN);
}

function setAuthToken(token) {
  localStorage.setItem(STORAGE_TOKEN, token);
}

function clearAuthSession() {
  localStorage.removeItem(STORAGE_TOKEN);
}

function showAuthScreen() {
  document.getElementById('auth-screen').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
}

function showAppScreen() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
}

function logout() {
  clearAuthSession();
  showAuthScreen();
}

function setApiBase(url) {
  localStorage.setItem(STORAGE_API, url.replace(/\/$/, ''));
}

function formatPrice(amount, currency = 'USD') {
  if (amount == null || Number.isNaN(amount)) return '—';
  const code = String(currency).toUpperCase();
  const cfg = CURRENCY_FORMAT[code];
  const zeroDecimals = cfg?.decimals === 0;
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: code,
      minimumFractionDigits: zeroDecimals ? 0 : 2,
      maximumFractionDigits: zeroDecimals ? 0 : 2,
    }).format(amount);
  } catch {
    const fallback = cfg || { symbol: code, decimals: 2, position: 'after' };
    const value = zeroDecimals
      ? Math.round(amount).toLocaleString()
      : amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return fallback.position === 'before' ? `${fallback.symbol}${value}` : `${value} ${fallback.symbol}`;
  }
}

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function showError(message) {
  const el = document.getElementById('global-error');
  el.textContent = message;
  el.classList.toggle('hidden', !message);
}

function showRefreshStatus(message, isError = false) {
  const el = document.getElementById('refresh-status');
  el.textContent = message;
  el.classList.toggle('hidden', !message);
  el.classList.toggle('text-red-400', isError);
  el.classList.toggle('text-green-400', !isError && !!message);
  el.classList.toggle('text-slate-500', !message);
}

async function refreshNow() {
  const btn = document.getElementById('btn-refresh');
  btn.disabled = true;
  btn.textContent = 'Checking…';
  showError('');
  showRefreshStatus('');

  try {
    const result = await api('/refresh', { method: 'POST' });
    await loadTracks();

    if (result.errors > 0 && result.routes_checked === 0) {
      showRefreshStatus('No active routes to check.', true);
    } else if (result.errors > 0) {
      showRefreshStatus(
        `Checked ${result.routes_checked} route(s). ${result.errors} failed.`,
        true,
      );
    } else if (result.drops_detected > 0) {
      showRefreshStatus(
        `Checked ${result.routes_checked} route(s). ${result.drops_detected} price drop(s) detected!`,
      );
    } else if (result.routes_checked === 0) {
      showRefreshStatus('No active routes to check.');
    } else {
      showRefreshStatus(`Checked ${result.routes_checked} route(s). No drops.`);
    }
  } catch (err) {
    showError(err.message);
    showRefreshStatus('Refresh failed.', true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh now';
  }
}

async function api(path, options = {}) {
  const { skipAuth, headers: extraHeaders, ...fetchOptions } = options;
  const base = getApiBase();
  const headers = { 'Content-Type': 'application/json', ...(extraHeaders || {}) };
  const token = getAuthToken();
  if (token && !skipAuth) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${base}${path}`, {
    headers,
    ...fetchOptions,
  });

  if (res.status === 401 && token) {
    logout();
    throw new Error('Session expired. Please sign in again.');
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function getOrCreateDeviceToken() {
  return localStorage.getItem(STORAGE_DEVICE_TOKEN);
}

function setDeviceToken(token) {
  if (token) localStorage.setItem(STORAGE_DEVICE_TOKEN, token);
}

async function initPushNotifications() {
  if (!Capacitor.isNativePlatform() || !getAuthToken()) return;

  let perm = await PushNotifications.checkPermissions();
  if (perm.receive === 'prompt') {
    perm = await PushNotifications.requestPermissions();
  }
  if (perm.receive !== 'granted') return;

  await PushNotifications.removeAllListeners();
  PushNotifications.addListener('registration', async (token) => {
    setDeviceToken(token.value);
    try {
      await api('/devices/register', {
        method: 'POST',
        body: JSON.stringify({
          fcm_token: token.value,
          email: localStorage.getItem(STORAGE_EMAIL) || null,
        }),
      });
    } catch (err) {
      console.warn('Device registration failed:', err.message);
    }
  });
  PushNotifications.addListener('registrationError', (err) => {
    console.warn('Push registration error:', err);
  });

  await PushNotifications.register();
}

async function registerDeviceForNotifications() {
  const token = getOrCreateDeviceToken();
  if (!token || !getAuthToken()) return null;
  await api('/devices/register', {
    method: 'POST',
    body: JSON.stringify({
      fcm_token: token,
      email: localStorage.getItem(STORAGE_EMAIL) || null,
    }),
  });
}

/**
 * Open the flight booking page on the airline or aggregator site.
 * @param {number} trackId
 */
async function openFlightBooking(trackId) {
  const btn = document.querySelector(`[data-book="${trackId}"]`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Opening…';
  }

  try {
    const booking = await api(`/tracks/${trackId}/booking`);
    const url = booking.url;
    if (!url) throw new Error('No booking URL returned');

    if (Capacitor.isNativePlatform()) {
      await Browser.open({ url });
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  } catch (err) {
    showError(err.message || 'Could not open booking link');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Book flight';
    }
  }
}

function drawSparkline(canvas, points) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  if (!points || points.length < 2) {
    ctx.strokeStyle = '#334155';
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();
    return;
  }

  const prices = points.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pad = 4;

  const coords = prices.map((price, i) => ({
    x: pad + (i / (prices.length - 1)) * (w - pad * 2),
    y: pad + (1 - (price - min) / range) * (h - pad * 2),
  }));

  const trendDown = prices[prices.length - 1] < prices[0];
  ctx.strokeStyle = trendDown ? '#4ade80' : '#94a3b8';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  coords.forEach((c, i) => (i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y)));
  ctx.stroke();

  const last = coords[coords.length - 1];
  ctx.fillStyle = trendDown ? '#4ade80' : '#cbd5e1';
  ctx.beginPath();
  ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
  ctx.fill();
}

function formatStopsCount(stopsCount) {
  if (stopsCount == null) return '';
  return stopsCount === 0 ? 'Direct' : `${stopsCount} stop${stopsCount === 1 ? '' : 's'}`;
}

function trackMetaLine(track) {
  const parts = [];
  if (track.provider_label) parts.push(track.provider_label);
  if (track.airline) parts.push(track.airline);
  const stopsText = formatStopsCount(track.stops_count);
  if (stopsText) parts.push(stopsText);
  if (!parts.length) return '';
  return `<p class="text-xs text-slate-500 mt-1">${parts.join(' · ')}</p>`;
}

function trackCardHtml(track, history) {
  const drop = track.lowest_price != null && track.current_price != null && track.current_price <= track.lowest_price;
  const priceClass = drop ? 'text-green-400' : 'text-white';
  const meta = trackMetaLine(track);
  const stopsPref = track.stops && track.stops !== 'any'
    ? `<span class="text-slate-600"> · ${stopsLabels[track.stops] || track.stops}</span>`
    : '';

  return `
    <article class="bg-slate-850/60 border border-slate-800 rounded-2xl p-5 fade-in" data-id="${track.id}">
      <div class="flex justify-between items-start gap-3">
        <div>
          <p class="text-lg font-medium tracking-tight text-white">
            ${track.departure_city}
            <span class="text-slate-600 font-light mx-1">→</span>
            ${track.destination_city}
          </p>
          <p class="text-xs text-slate-500 mt-1 font-light">
            ${formatDate(track.departure_date)}${track.return_date ? ` – ${formatDate(track.return_date)}` : ''}${stopsPref}
          </p>
          ${meta}
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <button type="button" data-edit="${track.id}"
            class="text-slate-600 hover:text-white text-xs transition" aria-label="Edit">Edit</button>
          <button type="button" data-delete="${track.id}"
            class="text-slate-600 hover:text-red-400 text-xs transition" aria-label="Delete">Remove</button>
        </div>
      </div>

      <div class="mt-5 flex items-end justify-between gap-4">
        <div>
          <p class="text-xs text-slate-500 uppercase tracking-wider">Current</p>
          <p class="text-2xl font-semibold ${priceClass} mt-0.5">
            ${formatPrice(track.current_price, track.currency)}
          </p>
          ${track.lowest_price != null ? `
            <p class="text-xs text-slate-500 mt-1">Low ${formatPrice(track.lowest_price, track.currency)}</p>
          ` : '<p class="text-xs text-slate-600 mt-1">Awaiting first check</p>'}
        </div>
        <canvas class="sparkline shrink-0" width="96" height="40" data-spark="${track.id}"></canvas>
      </div>

      <div class="mt-4 flex gap-2">
        <button type="button" data-book="${track.id}"
          class="flex-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl py-2.5 transition">
          Book flight
        </button>
      </div>
    </article>
  `;
}

async function loadTracks() {
  const list = document.getElementById('tracks-list');
  const empty = document.getElementById('tracks-empty');
  showError('');

  try {
    const tracks = await api('/tracks');
    list.innerHTML = '';

    if (!tracks.length) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');

    for (const track of tracks) {
      let history = [];
      try {
        history = await api(`/tracks/${track.id}/history`);
      } catch (_) { /* no history yet */ }

      list.insertAdjacentHTML('beforeend', trackCardHtml(track, history));
      const canvas = list.querySelector(`[data-spark="${track.id}"]`);
      if (canvas) drawSparkline(canvas, history);
    }
  } catch (err) {
    showError(`Failed to load routes: ${err.message}`);
    empty.classList.remove('hidden');
  }
}

async function loadStops() {
  try {
    const data = await api('/stops');
    stopsLabels = data.labels || stopsLabels;
    const select = document.getElementById('stops');
    select.innerHTML = (data.options || ['any', 'direct', 'connecting'])
      .map((value) => `<option value="${value}"${value === data.default ? ' selected' : ''}>${stopsLabels[value] || value}</option>`)
      .join('');
  } catch {
    const select = document.getElementById('stops');
    select.innerHTML = Object.entries(stopsLabels)
      .map(([value, label]) => `<option value="${value}"${value === 'any' ? ' selected' : ''}>${label}</option>`)
      .join('');
  }
}

async function loadCurrencies() {
  try {
    const data = await api('/currencies');
    supportedCurrencies = data.currencies || supportedCurrencies;
    const select = document.getElementById('currency');
    select.innerHTML = supportedCurrencies
      .map((c) => `<option value="${c}"${c === data.default ? ' selected' : ''}>${c}</option>`)
      .join('');
  } catch (_) {
    const select = document.getElementById('currency');
    select.innerHTML = supportedCurrencies
      .map((c) => `<option value="${c}"${c === 'USD' ? ' selected' : ''}>${c}</option>`)
      .join('');
  }
}

/** @type {{ hide: () => void }[]} */
const airportAutocompleteControllers = [];

function hideAirportSuggestions(input, list) {
  list.classList.add('hidden');
  list.innerHTML = '';
  input.setAttribute('aria-expanded', 'false');
}

function hideAllAirportSuggestions() {
  airportAutocompleteControllers.forEach((controller) => controller.hide());
}

function setupAirportAutocomplete(inputId, listId) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  /** @type {{ iata: string, name: string, city: string, country: string }[]} */
  let results = [];
  let activeIndex = -1;
  let debounceTimer = null;
  /** @type {() => void} */
  let closeOther = () => {};

  function selectAirport(airport) {
    input.value = airport.iata;
    hideAirportSuggestions(input, list);
    activeIndex = -1;
    results = [];
  }

  function render() {
    list.innerHTML = '';
    if (!results.length) {
      hideAirportSuggestions(input, list);
      return;
    }

    results.forEach((airport, index) => {
      const item = document.createElement('li');
      item.setAttribute('role', 'option');
      item.className = 'airport-suggestion px-3 py-2.5 cursor-pointer hover:bg-slate-800 transition text-left';
      item.setAttribute('aria-selected', String(index === activeIndex));
      item.innerHTML = `
        <span class="text-sm font-medium text-white tracking-wide">${airport.iata}</span>
        <span class="text-xs text-slate-400 block truncate">${airport.city} · ${airport.country}</span>
      `;
      item.addEventListener('mousedown', (e) => {
        e.preventDefault();
        selectAirport(airport);
      });
      list.appendChild(item);
    });

    list.classList.remove('hidden');
    input.setAttribute('aria-expanded', 'true');
  }

  async function runSearch(query) {
    const q = query.trim();
    if (q.length < 1) {
      results = [];
      hideAirportSuggestions(input, list);
      return;
    }

    try {
      results = await api(`/airports/search?q=${encodeURIComponent(q)}&limit=8`);
      activeIndex = results.length ? 0 : -1;
      render();
    } catch {
      hideAirportSuggestions(input, list);
    }
  }

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => runSearch(input.value), 200);
  });

  input.addEventListener('focus', () => {
    closeOther();
    if (input.value.trim()) runSearch(input.value);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && results.length) {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, results.length - 1);
      render();
      return;
    }
    if (e.key === 'ArrowUp' && results.length) {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      render();
      return;
    }
    if (e.key === 'Enter' && activeIndex >= 0 && results[activeIndex]) {
      e.preventDefault();
      selectAirport(results[activeIndex]);
      return;
    }
    if (e.key === 'Escape') {
      hideAirportSuggestions(input, list);
    }
  });

  input.addEventListener('blur', () => {
    setTimeout(() => hideAirportSuggestions(input, list), 150);
  });

  return {
    hide: () => hideAirportSuggestions(input, list),
    setCloseOtherHandler(fn) {
      closeOther = fn;
    },
  };
}

function initAirportAutocompletes() {
  const departure = setupAirportAutocomplete('departure', 'departure-suggestions');
  const destination = setupAirportAutocomplete('destination', 'destination-suggestions');
  departure.setCloseOtherHandler(() => destination.hide());
  destination.setCloseOtherHandler(() => departure.hide());
  airportAutocompleteControllers.push(departure, destination);
}

function resetRouteForm() {
  document.getElementById('form-add').reset();
  document.getElementById('track-id').value = '';
  document.getElementById('modal-title').textContent = 'Track a route';
  document.getElementById('form-submit').textContent = 'Start tracking';
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('departure-date').min = today;
  hideAllAirportSuggestions();
}

function openModal() {
  resetRouteForm();
  document.getElementById('modal').classList.remove('hidden');
  document.getElementById('form-error').classList.add('hidden');
}

async function openEditModal(trackId) {
  resetRouteForm();
  document.getElementById('form-error').classList.add('hidden');

  try {
    const track = await api(`/tracks/${trackId}`);
    document.getElementById('track-id').value = String(track.id);
    document.getElementById('departure').value = track.departure_city;
    document.getElementById('destination').value = track.destination_city;
    document.getElementById('departure-date').value = track.departure_date;
    document.getElementById('return-date').value = track.return_date || '';
    document.getElementById('target-price').value = track.target_price ?? '';
    document.getElementById('currency').value = track.currency;
    document.getElementById('stops').value = track.stops || 'any';
    document.getElementById('modal-title').textContent = 'Edit route';
    document.getElementById('form-submit').textContent = 'Save changes';
    document.getElementById('modal').classList.remove('hidden');
  } catch (err) {
    showError(err.message);
  }
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
  resetRouteForm();
}

function openSettingsModal() {
  const apiField = document.getElementById('settings-api-wrap');
  if (apiField) apiField.classList.toggle('hidden', IS_PRODUCTION_BUILD);
  document.getElementById('settings-api').value = getApiBase();
  document.getElementById('settings-email').value = localStorage.getItem(STORAGE_EMAIL) || '';
  document.getElementById('settings-status').classList.add('hidden');
  document.getElementById('settings-modal').classList.remove('hidden');
}

function closeSettingsModal() {
  document.getElementById('settings-modal').classList.add('hidden');
}

async function saveSettings() {
  const email = document.getElementById('settings-email').value.trim();
  const apiBase = document.getElementById('settings-api').value.trim();
  const status = document.getElementById('settings-status');

  if (apiBase) setApiBase(apiBase);
  if (email) localStorage.setItem(STORAGE_EMAIL, email);

  try {
    await registerDeviceForNotifications();
    status.textContent = 'Settings saved';
    status.classList.remove('hidden', 'text-red-400');
    status.classList.add('text-green-400');
    setTimeout(closeSettingsModal, 800);
  } catch (err) {
    status.textContent = err.message;
    status.classList.remove('hidden', 'text-green-400');
    status.classList.add('text-red-400');
  }
}

async function handleAuthSubmit(mode) {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const errEl = document.getElementById('auth-error');
  errEl.classList.add('hidden');

  try {
    const path = mode === 'register' ? '/auth/register' : '/auth/login';
    const data = await api(path, {
      method: 'POST',
      skipAuth: true,
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(data.access_token);
    if (email) localStorage.setItem(STORAGE_EMAIL, email);
    showAppScreen();
    await bootstrapApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  }
}

function bindEvents() {
  initAirportAutocompletes();

  document.getElementById('btn-auth-login').addEventListener('click', () => handleAuthSubmit('login'));
  document.getElementById('btn-auth-register').addEventListener('click', () => handleAuthSubmit('register'));
  document.getElementById('btn-logout').addEventListener('click', logout);
  document.getElementById('btn-add').addEventListener('click', openModal);
  document.getElementById('btn-refresh').addEventListener('click', refreshNow);
  document.getElementById('btn-settings').addEventListener('click', openSettingsModal);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('settings-modal-close').addEventListener('click', closeSettingsModal);
  document.getElementById('modal').addEventListener('click', (e) => {
    if (e.target.id === 'modal') closeModal();
  });
  document.getElementById('settings-modal').addEventListener('click', (e) => {
    if (e.target.id === 'settings-modal') closeSettingsModal();
  });

  document.getElementById('form-add').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('form-error');
    errEl.classList.add('hidden');

    const payload = {
      departure_city: document.getElementById('departure').value.trim(),
      destination_city: document.getElementById('destination').value.trim(),
      departure_date: document.getElementById('departure-date').value,
      return_date: document.getElementById('return-date').value || null,
      target_price: document.getElementById('target-price').value
        ? Number(document.getElementById('target-price').value)
        : null,
      currency: document.getElementById('currency').value,
      stops: document.getElementById('stops').value,
    };

    const trackId = document.getElementById('track-id').value;
    const method = trackId ? 'PUT' : 'POST';
    const path = trackId ? `/tracks/${trackId}` : '/tracks';

    try {
      await api(path, { method, body: JSON.stringify(payload) });
      closeModal();
      await loadTracks();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  });

  document.getElementById('tracks-list').addEventListener('click', async (e) => {
    const editId = e.target.closest('[data-edit]')?.dataset.edit;
    const deleteId = e.target.closest('[data-delete]')?.dataset.delete;
    const bookId = e.target.closest('[data-book]')?.dataset.book;

    if (editId) {
      await openEditModal(Number(editId));
    }

    if (deleteId) {
      if (!confirm('Stop tracking this route?')) return;
      try {
        await api(`/tracks/${deleteId}`, { method: 'DELETE' });
        await loadTracks();
      } catch (err) {
        showError(err.message);
      }
    }

    if (bookId) {
      await openFlightBooking(Number(bookId));
    }
  });

  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
}

async function bootstrapApp() {
  await Promise.all([loadCurrencies(), loadStops()]);
  const me = await api('/auth/me');
  const userLabel = document.getElementById('user-email');
  if (userLabel) userLabel.textContent = me.email;
  await initPushNotifications();
  await loadTracks();
}

async function init() {
  bindEvents();

  if (IS_PRODUCTION_BUILD) {
    document.getElementById('settings-api-wrap')?.classList.add('hidden');
  }

  if (!getAuthToken()) {
    showAuthScreen();
    return;
  }

  showAppScreen();
  try {
    await bootstrapApp();
  } catch (err) {
    clearAuthSession();
    showAuthScreen();
    const errEl = document.getElementById('auth-error');
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  }
}

init();

// Export for Capacitor / testing
window.openFlightBooking = openFlightBooking;
