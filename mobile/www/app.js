/**
 * The RSE demand-side mobile app
 * Talks ONLY to https://rse-api.com:5003 — never the marketing website.
 */
(function () {
  'use strict';

  const API_URL = 'https://rse-api.com:5003';
  /** Public profile pages live on the marketing site (opaque slug, not username). */
  const PUBLIC_PROFILE_BASE =
    'https://theservicesexchange.com/profile.html?pid=';
  /**
   * Hosted next to release APKs. Bump versionCode + apkUrl when shipping a build.
   * Must be HTTPS and publicly readable.
   */
  const UPDATE_MANIFEST_URL =
    'https://theservicesexchange.com/apk/version.json';
  const UPDATE_MANIFEST_FALLBACKS = [
    'https://www.theservicesexchange.com/apk/version.json',
  ];
  const STORAGE = {
    token: 'rse_app_token',
    username: 'rse_app_username',
    nearbyAddress: 'rse_nearby_address',
    nearbyRadius: 'rse_nearby_radius',
    nearbyLat: 'rse_nearby_lat',
    nearbyLon: 'rse_nearby_lon',
    updateDismissedCode: 'rse_update_dismissed_code',
  };

  const state = {
    token: localStorage.getItem(STORAGE.token) || null,
    username: localStorage.getItem(STORAGE.username) || null,
    account: null,
    profile: null,
    profileSlug: null,
    shareUrl: null,
    nearby: {
      lat: null,
      lon: null,
      address: localStorage.getItem(STORAGE.nearbyAddress) || '',
      radius: parseInt(localStorage.getItem(STORAGE.nearbyRadius) || '10', 10) || 10,
      lastMode: null, // 'gps' | 'address'
    },
    authMode: 'login', // login | register
    screen: 'request',
  };

  // Restore last GPS coords if present
  {
    const la = parseFloat(localStorage.getItem(STORAGE.nearbyLat) || '');
    const lo = parseFloat(localStorage.getItem(STORAGE.nearbyLon) || '');
    if (!Number.isNaN(la) && !Number.isNaN(lo)) {
      state.nearby.lat = la;
      state.nearby.lon = lo;
      state.nearby.lastMode = 'gps';
    }
  }

  // ── DOM ──────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const els = {
    body: document.body,
    header: $('appHeader'),
    headerUser: $('headerUser'),
    headerAccountBtn: $('headerAccountBtn'),
    screenAuth: $('screen-auth'),
    screenRequest: $('screen-request'),
    screenJobs: $('screen-jobs'),
    screenAccount: $('screen-account'),
    screenNearby: $('screen-nearby'),
    screenFeedback: $('screen-feedback'),
    nearbyRadius: $('nearbyRadius'),
    nearbyRadiusLabel: $('nearbyRadiusLabel'),
    nearbyAddress: $('nearbyAddress'),
    nearbyUseGps: $('nearbyUseGps'),
    nearbySearchBtn: $('nearbySearchBtn'),
    nearbyStatus: $('nearbyStatus'),
    nearbyError: $('nearbyError'),
    nearbyList: $('nearbyList'),
    refreshNearby: $('refreshNearby'),
    tabLogin: $('tabLogin'),
    tabRegister: $('tabRegister'),
    authForm: $('authForm'),
    authSubmit: $('authSubmit'),
    authError: $('authError'),
    registerHint: $('registerHint'),
    username: $('username'),
    password: $('password'),
    bidForm: $('bidForm'),
    bidSubmit: $('bidSubmit'),
    requestError: $('requestError'),
    requestSuccess: $('requestSuccess'),
    service: $('service'),
    price: $('price'),
    hours: $('hours'),
    locationType: $('locationType'),
    address: $('address'),
    payment: $('payment'),
    openBids: $('openBids'),
    refreshBids: $('refreshBids'),
    activeJobs: $('activeJobs'),
    completedJobs: $('completedJobs'),
    refreshJobs: $('refreshJobs'),
    jobsError: $('jobsError'),
    acctName: $('acctName'),
    acctDisplayName: $('acctDisplayName'),
    acctType: $('acctType'),
    acctRep: $('acctRep'),
    acctJobs: $('acctJobs'),
    acctFollowers: $('acctFollowers'),
    acctStars: $('acctStars'),
    acctAvatar: $('acctAvatar'),
    accountError: $('accountError'),
    accountSuccess: $('accountSuccess'),
    shareLinkInput: $('shareLinkInput'),
    copyShareBtn: $('copyShareBtn'),
    openShareBtn: $('openShareBtn'),
    profileForm: $('profileForm'),
    profileDisplayName: $('profileDisplayName'),
    profileAbout: $('profileAbout'),
    profileLocation: $('profileLocation'),
    profileContact: $('profileContact'),
    profileSaveBtn: $('profileSaveBtn'),
    logoutBtn: $('logoutBtn'),
    checkUpdateBtn: $('checkUpdateBtn'),
    appVersionLabel: $('appVersionLabel'),
    feedbackForm: $('feedbackForm'),
    feedbackMessage: $('feedbackMessage'),
    feedbackSubmit: $('feedbackSubmit'),
    feedbackError: $('feedbackError'),
    feedbackSuccess: $('feedbackSuccess'),
    feedbackAs: $('feedbackAs'),
    feedbackList: $('feedbackList'),
    refreshFeedback: $('refreshFeedback'),
    toast: $('toast'),
    updateOverlay: $('updateOverlay'),
    updateTitle: $('updateTitle'),
    updateMessage: $('updateMessage'),
    updateProgressBar: $('updateProgressBar'),
    updatePercent: $('updatePercent'),
    updateActions: $('updateActions'),
    updateRetryBtn: $('updateRetryBtn'),
    updateDismissBtn: $('updateDismissBtn'),
  };

  let pendingManifest = null;
  let updateInFlight = false;
  let updateProgressListenerReady = false;

  // ── Helpers ──────────────────────────────────────────────────────
  function toast(msg, type) {
    els.toast.textContent = msg;
    els.toast.className = 'toast show' + (type ? ' ' + type : '');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      els.toast.className = 'toast';
    }, 3200);
  }

  function showError(el, msg) {
    if (!el) return;
    if (!msg) {
      el.textContent = '';
      el.classList.remove('show');
      return;
    }
    el.textContent = msg;
    el.classList.add('show');
  }

  function showSuccess(el, msg) {
    if (!el) return;
    if (!msg) {
      el.textContent = '';
      el.classList.remove('show');
      return;
    }
    el.textContent = msg;
    el.classList.add('show');
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatMoney(price, currency) {
    const n = Number(price);
    if (Number.isNaN(n)) return String(price ?? '');
    return `$${n.toFixed(n % 1 ? 2 : 0)} ${currency || 'USD'}`;
  }

  function formatWhen(ts) {
    if (!ts) return '';
    const d = new Date(Number(ts) * (Number(ts) < 1e12 ? 1000 : 1));
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function formatIsoWhen(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function feedbackDisplayName() {
    return (state.username || '').trim() || 'Guest';
  }

  function updateFeedbackAsLabel() {
    if (!els.feedbackAs) return;
    const name = feedbackDisplayName();
    els.feedbackAs.textContent =
      name === 'Guest' ? 'Posting as Guest' : `Posting as @${name}`;
  }

  function setLoading(btn, loading, labelIdle) {
    if (!btn) return;
    btn.disabled = !!loading;
    if (loading) {
      btn.dataset.label = btn.textContent;
      btn.textContent = '…';
    } else {
      btn.textContent = labelIdle || btn.dataset.label || btn.textContent;
    }
  }

  // ── API ──────────────────────────────────────────────────────────
  async function api(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };
    if (state.token) {
      headers.Authorization = `Bearer ${state.token}`;
    }
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
    });

    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: text };
      }
    }

    if (res.status === 401 && state.token && path !== '/login') {
      clearSession();
      showAuth();
      throw new Error('Session expired — please log in again.');
    }

    if (!res.ok) {
      const msg =
        (data && (data.error || data.message)) ||
        `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function saveSession(token, username) {
    state.token = token;
    state.username = username;
    localStorage.setItem(STORAGE.token, token);
    localStorage.setItem(STORAGE.username, username);
  }

  function clearSession() {
    state.token = null;
    state.username = null;
    state.account = null;
    state.profile = null;
    state.profileSlug = null;
    state.shareUrl = null;
    localStorage.removeItem(STORAGE.token);
    localStorage.removeItem(STORAGE.username);
  }

  function publicShareUrl(slug) {
    if (!slug) return '';
    return PUBLIC_PROFILE_BASE + encodeURIComponent(slug);
  }

  async function copyText(text) {
    if (!text) throw new Error('Nothing to copy');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    if (!ok) throw new Error('Copy not supported');
  }

  function setAvatarEl(avatarUrl, displayName, username) {
    if (!els.acctAvatar) return;
    const label = (displayName || username || '?').trim();
    const initial = (label.replace(/^@/, '')[0] || '◎').toUpperCase();
    if (avatarUrl) {
      els.acctAvatar.style.backgroundImage = `url(${JSON.stringify(avatarUrl).slice(1, -1)})`;
      els.acctAvatar.textContent = '';
    } else {
      els.acctAvatar.style.backgroundImage = '';
      els.acctAvatar.textContent = initial;
    }
  }

  /** Client-side coarsening until server privacy dials land (Track F). */
  function coarsenAddress(addr) {
    if (!addr) return '';
    const parts = String(addr)
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length >= 2) return parts.slice(-2).join(', ');
    if (parts[0].length > 48) return parts[0].slice(0, 45) + '…';
    return parts[0];
  }

  function getDeviceLocation() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Geolocation is not available on this device.'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          resolve({
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
          });
        },
        (err) => {
          let msg = 'Could not get location.';
          if (err && err.code === 1) msg = 'Location permission denied.';
          else if (err && err.code === 2) msg = 'Location unavailable.';
          else if (err && err.code === 3) msg = 'Location request timed out.';
          reject(new Error(msg));
        },
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
      );
    });
  }

  function persistNearbyPrefs() {
    localStorage.setItem(STORAGE.nearbyRadius, String(state.nearby.radius));
    if (state.nearby.address) {
      localStorage.setItem(STORAGE.nearbyAddress, state.nearby.address);
    }
    if (state.nearby.lat != null && state.nearby.lon != null) {
      localStorage.setItem(STORAGE.nearbyLat, String(state.nearby.lat));
      localStorage.setItem(STORAGE.nearbyLon, String(state.nearby.lon));
    }
  }

  function updateNearbyRadiusLabel() {
    if (!els.nearbyRadiusLabel || !els.nearbyRadius) return;
    const r = parseInt(els.nearbyRadius.value, 10) || 10;
    state.nearby.radius = r;
    els.nearbyRadiusLabel.textContent = r + (r === 1 ? ' mile' : ' miles');
  }

  // ── Navigation ───────────────────────────────────────────────────
  function showAuth() {
    els.body.classList.add('auth-only');
    els.body.classList.remove('app-ready');
    els.header.hidden = true;
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    els.screenAuth.classList.add('active');
  }

  function showApp(screen) {
    els.body.classList.remove('auth-only');
    els.body.classList.add('app-ready');
    els.header.hidden = false;
    els.headerUser.textContent = state.username
      ? `@${state.username}`
      : 'Demand';
    navigate(screen || state.screen || 'request');
  }

  function navigate(name) {
    state.screen = name;
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    const el = document.getElementById(`screen-${name}`);
    if (el) el.classList.add('active');
    document.querySelectorAll('.bottom-nav button').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.screen === name);
    });
    if (name === 'request') loadOpenBids();
    if (name === 'jobs') loadJobs();
    if (name === 'nearby') initNearbyScreen();
    if (name === 'account') loadAccount();
    if (name === 'feedback') loadFeedback();
  }

  // ── Auth UI ──────────────────────────────────────────────────────
  function setAuthMode(mode) {
    state.authMode = mode;
    const isReg = mode === 'register';
    els.tabLogin.classList.toggle('active', !isReg);
    els.tabRegister.classList.toggle('active', isReg);
    els.tabLogin.setAttribute('aria-selected', String(!isReg));
    els.tabRegister.setAttribute('aria-selected', String(isReg));
    els.authSubmit.textContent = isReg ? 'Create demand account' : 'Log in';
    els.registerHint.hidden = !isReg;
    els.password.autocomplete = isReg ? 'new-password' : 'current-password';
    showError(els.authError, null);
  }

  async function handleAuth(e) {
    e.preventDefault();
    showError(els.authError, null);
    const username = els.username.value.trim();
    const password = els.password.value;
    if (!username || !password) {
      showError(els.authError, 'Username and password required.');
      return;
    }
    setLoading(els.authSubmit, true);
    try {
      if (state.authMode === 'register') {
        await api('/register', {
          method: 'POST',
          body: JSON.stringify({
            username,
            password,
            user_type: 'demand',
          }),
        });
      }
      const data = await api('/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      if (data.user_type && data.user_type !== 'demand') {
        throw new Error(
          'This app is for demand (buyer) accounts only. Supply / provider accounts should use the API or website Find Work tools.'
        );
      }
      saveSession(data.access_token, data.username || username);
      els.password.value = '';
      await bootstrapApp();
      toast('Logged in', 'ok');
    } catch (err) {
      showError(els.authError, err.message || 'Auth failed');
    } finally {
      setLoading(
        els.authSubmit,
        false,
        state.authMode === 'register' ? 'Create demand account' : 'Log in'
      );
    }
  }

  // ── Bids ─────────────────────────────────────────────────────────
  async function handleBid(e) {
    e.preventDefault();
    showError(els.requestError, null);
    showSuccess(els.requestSuccess, null);

    const service = els.service.value.trim();
    const price = parseFloat(els.price.value);
    const hours = parseInt(els.hours.value, 10) || 24;
    const location_type = els.locationType.value || 'physical';
    const address = els.address.value.trim();
    const payment_method = (els.payment.value || 'cash').trim() || 'cash';

    if (!service) {
      showError(els.requestError, 'Describe the service you need.');
      return;
    }
    if (!(price > 0)) {
      showError(els.requestError, 'Enter a price greater than zero.');
      return;
    }
    if (location_type !== 'remote' && !address) {
      showError(els.requestError, 'Address is required for physical/hybrid jobs.');
      return;
    }

    const end_time = Math.floor(Date.now() / 1000) + hours * 3600;
    const body = {
      service,
      price,
      currency: 'USD',
      payment_method,
      end_time,
      location_type,
    };
    if (address) body.address = address;

    setLoading(els.bidSubmit, true, 'Post request');
    try {
      const data = await api('/submit_bid', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      showSuccess(
        els.requestSuccess,
        `Request posted${data.bid_id ? ` (${String(data.bid_id).slice(0, 8)}…)` : ''}. Waiting for a provider.`
      );
      els.service.value = '';
      toast('Request posted', 'ok');
      await loadOpenBids();
    } catch (err) {
      showError(els.requestError, err.message || 'Could not post request');
    } finally {
      setLoading(els.bidSubmit, false, 'Post request');
    }
  }

  async function loadOpenBids() {
    if (!state.token) return;
    els.openBids.innerHTML = '<div class="loading">Loading…</div>';
    try {
      const data = await api('/my_bids');
      const bids = data.bids || [];
      if (!bids.length) {
        els.openBids.innerHTML =
          '<div class="empty">No open requests. Post one above.</div>';
        return;
      }
      els.openBids.innerHTML = bids
        .map((b) => {
          const id = escapeHtml(b.bid_id);
          return `
          <div class="card" data-bid="${id}">
            <div class="card-title">${escapeHtml(b.service)}</div>
            <div class="card-meta">
              <span class="badge active">${escapeHtml(b.status || 'active')}</span>
              · ${escapeHtml(formatMoney(b.price, b.currency))}
              · ${escapeHtml(b.location_type || '')}
              ${b.address ? ' · ' + escapeHtml(b.address) : ''}
              ${b.end_time ? '<br>Expires ' + escapeHtml(formatWhen(b.end_time)) : ''}
            </div>
            <div class="btn-row">
              <button type="button" class="btn btn-sm btn-danger" data-cancel="${id}">Delete</button>
            </div>
          </div>`;
        })
        .join('');
    } catch (err) {
      els.openBids.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
    }
  }

  async function cancelBid(bidId) {
    if (!bidId) return;
    if (
      !confirm(
        'Delete this open request? It will be removed from the exchange.'
      )
    ) {
      return;
    }

    const btn = document.querySelector(
      `[data-cancel="${CSS.escape(bidId)}"]`
    );
    if (btn && btn.disabled) return;
    setLoading(btn, true, 'Delete');

    try {
      await api('/cancel_bid', {
        method: 'POST',
        body: JSON.stringify({ bid_id: bidId }),
      });
      toast('Request deleted', 'ok');
      await loadOpenBids();
    } catch (err) {
      const accepted =
        err.status === 409 ||
        /already been accepted|already accepted/i.test(err.message || '');
      if (accepted) {
        toast(
          err.message ||
            'This request was already accepted — see Jobs.',
          'error'
        );
        await loadOpenBids();
        navigate('jobs');
      } else {
        toast(err.message || 'Delete failed', 'error');
        setLoading(btn, false, 'Delete');
      }
    }
  }

  // ── Jobs ─────────────────────────────────────────────────────────
  async function loadJobs() {
    if (!state.token) return;
    showError(els.jobsError, null);
    els.activeJobs.innerHTML = '<div class="loading">Loading…</div>';
    els.completedJobs.innerHTML = '<div class="loading">Loading…</div>';
    try {
      const data = await api('/my_jobs');
      renderJobList(els.activeJobs, data.active_jobs || [], true);
      renderJobList(els.completedJobs, data.completed_jobs || [], false);
    } catch (err) {
      showError(els.jobsError, err.message);
      els.activeJobs.innerHTML = '';
      els.completedJobs.innerHTML = '';
    }
  }

  function renderJobList(container, jobs, isActive) {
    if (!jobs.length) {
      container.innerHTML = `<div class="empty">${
        isActive ? 'No active jobs yet.' : 'No completed jobs yet.'
      }</div>`;
      return;
    }
    container.innerHTML = jobs
      .map((j) => {
        const jid = escapeHtml(j.job_id);
        const ratingId = `rating-${jid}`;
        return `
        <div class="card ${isActive ? 'highlight' : ''}" data-job="${jid}">
          <div class="card-title">${escapeHtml(j.service)}</div>
          <div class="card-meta">
            <span class="badge ${isActive ? 'active' : 'done'}">${escapeHtml(
              j.status || (isActive ? 'accepted' : 'completed')
            )}</span>
            · ${escapeHtml(formatMoney(j.price, j.currency))}
            ${j.provider_username ? ' · Provider @' + escapeHtml(j.provider_username) : ''}
            ${j.address ? '<br>' + escapeHtml(j.address) : ''}
            ${j.accepted_at ? '<br>Matched ' + escapeHtml(formatWhen(j.accepted_at)) : ''}
          </div>
          ${
            isActive
              ? `
          <p class="muted small">When the work is done, rate the provider (both sides must sign).</p>
          <div class="star-picker" data-for="${jid}" id="${ratingId}">
            ${[1, 2, 3, 4, 5]
              .map(
                (n) =>
                  `<button type="button" data-star="${n}" aria-label="${n} stars">★</button>`
              )
              .join('')}
          </div>
          <button type="button" class="btn btn-primary btn-sm" data-sign="${jid}" style="width:100%;margin-top:8px">Rate &amp; complete</button>
          `
              : ''
          }
        </div>`;
      })
      .join('');
  }

  function getSelectedRating(jobId) {
    const picker = document.querySelector(`.star-picker[data-for="${jobId}"]`);
    if (!picker) return 0;
    return parseInt(picker.dataset.rating || '0', 10) || 0;
  }

  async function signJob(jobId) {
    const rating = getSelectedRating(jobId);
    if (rating < 1 || rating > 5) {
      toast('Pick a star rating first', 'error');
      return;
    }
    try {
      await api('/sign_job', {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId, rating }),
      });
      toast('Rating submitted', 'ok');
      await loadJobs();
      await loadAccount();
    } catch (err) {
      toast(err.message || 'Sign failed', 'error');
    }
  }

  // ── Nearby ───────────────────────────────────────────────────────
  function initNearbyScreen() {
    if (els.nearbyRadius) {
      els.nearbyRadius.value = String(state.nearby.radius || 10);
      updateNearbyRadiusLabel();
    }
    if (els.nearbyAddress && !els.nearbyAddress.value) {
      els.nearbyAddress.value = state.nearby.address || '';
    }
    // Auto-search if we already have a location or address
    if (
      (state.nearby.lat != null && state.nearby.lon != null) ||
      (state.nearby.address && state.nearby.address.trim())
    ) {
      loadNearby();
    }
  }

  async function useNearbyGps() {
    showError(els.nearbyError, null);
    setLoading(els.nearbyUseGps, true, 'Use my location');
    if (els.nearbyStatus) {
      els.nearbyStatus.textContent = 'Getting device location…';
    }
    try {
      const { lat, lon } = await getDeviceLocation();
      state.nearby.lat = lat;
      state.nearby.lon = lon;
      state.nearby.lastMode = 'gps';
      // GPS search should not be overridden by a stale address field
      if (els.nearbyAddress) els.nearbyAddress.value = '';
      state.nearby.address = '';
      localStorage.removeItem(STORAGE.nearbyAddress);
      persistNearbyPrefs();
      if (els.nearbyStatus) {
        els.nearbyStatus.textContent = `Using GPS (~${lat.toFixed(3)}, ${lon.toFixed(3)})`;
      }
      await loadNearby({ preferGps: true });
    } catch (err) {
      showError(els.nearbyError, err.message || 'Location failed');
      if (els.nearbyStatus) {
        els.nearbyStatus.textContent =
          'GPS failed — enter an address or city instead.';
      }
    } finally {
      setLoading(els.nearbyUseGps, false, 'Use my location');
    }
  }

  async function loadNearby(opts) {
    if (!els.nearbyList) return;
    const preferGps = opts && opts.preferGps;
    showError(els.nearbyError, null);
    updateNearbyRadiusLabel();

    const address = (els.nearbyAddress && els.nearbyAddress.value.trim()) || '';
    if (address) {
      state.nearby.address = address;
    }

    const body = { radius: state.nearby.radius };
    // Prefer GPS when explicitly requested; else typed address; else last GPS
    if (preferGps && state.nearby.lat != null && state.nearby.lon != null) {
      body.lat = state.nearby.lat;
      body.lon = state.nearby.lon;
      state.nearby.lastMode = 'gps';
    } else if (address) {
      body.address = address;
      state.nearby.lastMode = 'address';
    } else if (state.nearby.lat != null && state.nearby.lon != null) {
      body.lat = state.nearby.lat;
      body.lon = state.nearby.lon;
      state.nearby.lastMode = 'gps';
    } else {
      showError(
        els.nearbyError,
        'Enter an address/city or tap Use my location.'
      );
      els.nearbyList.innerHTML =
        '<div class="empty">Set a location to discover open requests.</div>';
      return;
    }

    persistNearbyPrefs();
    els.nearbyList.innerHTML = '<div class="loading">Loading nearby…</div>';
    setLoading(els.nearbySearchBtn, true, 'Search nearby');
    try {
      const data = await api('/nearby', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      const services = data.services || [];
      if (els.nearbyStatus) {
        const where = address
          ? address
          : `GPS (${Number(body.lat).toFixed(3)}, ${Number(body.lon).toFixed(3)})`;
        els.nearbyStatus.textContent = `${services.length} open within ${state.nearby.radius} mi of ${where}`;
      }
      if (!services.length) {
        els.nearbyList.innerHTML =
          '<div class="empty">No open physical/hybrid requests in this radius.</div>';
        return;
      }
      els.nearbyList.innerHTML = services
        .map((s) => {
          const dist =
            s.distance != null ? Number(s.distance).toFixed(1) + ' mi' : '';
          const area = coarsenAddress(s.address);
          const rep =
            s.buyer_reputation != null
              ? Number(s.buyer_reputation).toFixed(1)
              : '—';
          return `
          <div class="card">
            <div class="card-title">${escapeHtml(
              typeof s.service === 'string'
                ? s.service
                : JSON.stringify(s.service)
            )}</div>
            <div class="card-meta">
              ${
                dist
                  ? `<span class="nearby-dist">${escapeHtml(dist)}</span> · `
                  : ''
              }
              ${escapeHtml(formatMoney(s.price, s.currency))}
              · buyer rep ${escapeHtml(rep)}
              ${area ? '<br>' + escapeHtml(area) : ''}
            </div>
          </div>`;
        })
        .join('');
    } catch (err) {
      els.nearbyList.innerHTML = `<div class="empty">${escapeHtml(
        err.message || 'Nearby search failed'
      )}</div>`;
      showError(els.nearbyError, err.message);
    } finally {
      setLoading(els.nearbySearchBtn, false, 'Search nearby');
    }
  }

  // ── Feedback ─────────────────────────────────────────────────────
  async function loadFeedback() {
    updateFeedbackAsLabel();
    showError(els.feedbackError, null);
    if (!els.feedbackList) return;
    els.feedbackList.innerHTML = '<div class="loading">Loading…</div>';
    try {
      const data = await api('/feedback');
      const posts = data.posts || [];
      if (!posts.length) {
        els.feedbackList.innerHTML =
          '<div class="empty">No feedback yet. Be the first!</div>';
        return;
      }
      els.feedbackList.innerHTML = posts.map(renderFeedbackPost).join('');
    } catch (err) {
      els.feedbackList.innerHTML = `<div class="empty">${escapeHtml(
        err.message || 'Could not load feedback'
      )}</div>`;
    }
  }

  function renderFeedbackPost(post) {
    const id = escapeHtml(post.id);
    const user = escapeHtml(post.username || 'Guest');
    const when = escapeHtml(formatIsoWhen(post.created));
    const message = escapeHtml(post.message || '');
    const replies = Array.isArray(post.replies) ? post.replies : [];
    const repliesHtml = replies.length
      ? `<div class="fb-replies">${replies
          .map(
            (r) => `
          <div class="fb-reply">
            <div class="card-meta">
              <span class="fb-user">@${escapeHtml(r.username || 'Guest')}</span>
              · ${escapeHtml(formatIsoWhen(r.created))}
            </div>
            <p class="fb-body" style="margin:0">${escapeHtml(r.message || '')}</p>
          </div>`
          )
          .join('')}</div>`
      : '';

    return `
      <div class="card fb-post" data-fb-post="${id}">
        <div class="card-meta">
          <span class="fb-user">@${user}</span>
          ${when ? ' · ' + when : ''}
        </div>
        <p class="fb-body">${message}</p>
        ${repliesHtml}
        <button type="button" class="btn btn-sm" data-fb-reply-toggle="${id}">Reply</button>
        <div class="fb-reply-form" id="fb-reply-form-${id}" data-fb-reply-form="${id}">
          <input type="text" maxlength="2000" placeholder="Write a reply…" data-fb-reply-input="${id}" autocomplete="off">
          <button type="button" class="btn btn-primary btn-sm" data-fb-reply-send="${id}">Send</button>
        </div>
      </div>`;
  }

  async function handleFeedbackSubmit(e) {
    e.preventDefault();
    showError(els.feedbackError, null);
    showSuccess(els.feedbackSuccess, null);
    const message = (els.feedbackMessage.value || '').trim();
    if (!message) {
      showError(els.feedbackError, 'Please enter a message.');
      return;
    }
    setLoading(els.feedbackSubmit, true, 'Post feedback');
    try {
      await api('/feedback', {
        method: 'POST',
        body: JSON.stringify({
          message,
          username: feedbackDisplayName(),
        }),
      });
      els.feedbackMessage.value = '';
      showSuccess(els.feedbackSuccess, 'Thanks — feedback posted.');
      toast('Feedback posted', 'ok');
      await loadFeedback();
    } catch (err) {
      showError(els.feedbackError, err.message || 'Could not post feedback');
    } finally {
      setLoading(els.feedbackSubmit, false, 'Post feedback');
    }
  }

  function toggleFeedbackReply(postId) {
    const form = document.getElementById(`fb-reply-form-${postId}`);
    if (!form) return;
    const open = form.classList.toggle('open');
    if (open) {
      const input = form.querySelector('[data-fb-reply-input]');
      if (input) input.focus();
    }
  }

  async function sendFeedbackReply(postId) {
    if (!postId) return;
    const form = document.getElementById(`fb-reply-form-${postId}`);
    const input = form && form.querySelector('[data-fb-reply-input]');
    const sendBtn = form && form.querySelector('[data-fb-reply-send]');
    const message = (input && input.value.trim()) || '';
    if (!message) {
      toast('Write a reply first', 'error');
      return;
    }
    setLoading(sendBtn, true, 'Send');
    try {
      await api(`/feedback/${encodeURIComponent(postId)}/reply`, {
        method: 'POST',
        body: JSON.stringify({
          message,
          username: feedbackDisplayName(),
        }),
      });
      toast('Reply posted', 'ok');
      await loadFeedback();
    } catch (err) {
      toast(err.message || 'Reply failed', 'error');
      setLoading(sendBtn, false, 'Send');
    }
  }

  // ── Account ──────────────────────────────────────────────────────
  async function loadAccount() {
    if (!state.token) return;
    showError(els.accountError, null);
    showSuccess(els.accountSuccess, null);
    try {
      const [account, profile, share] = await Promise.all([
        api('/account'),
        api('/profile'),
        api('/profile/share_link'),
      ]);

      if (account.user_type && account.user_type !== 'demand') {
        clearSession();
        showAuth();
        showError(
          els.authError,
          'This app is for demand accounts only.'
        );
        return;
      }

      state.account = account;
      state.profile = profile;
      const username = account.username || profile.username || state.username;
      state.username = username;
      state.profileSlug = share.profile_slug || profile.profile_slug || null;
      state.shareUrl = publicShareUrl(state.profileSlug);

      const displayName =
        profile.display_name || username || '—';
      if (els.acctDisplayName) {
        els.acctDisplayName.textContent = displayName;
      }
      els.acctName.textContent = '@' + username;
      els.acctType.textContent = account.user_type || 'demand';
      els.acctRep.textContent =
        (profile.reputation_score != null
          ? profile.reputation_score
          : account.reputation_score) != null
          ? Number(
              profile.reputation_score != null
                ? profile.reputation_score
                : account.reputation_score
            ).toFixed(2)
          : '—';
      els.acctJobs.textContent =
        account.completed_jobs != null ? account.completed_jobs : '—';
      if (els.acctFollowers) {
        els.acctFollowers.textContent =
          profile.follower_count != null ? profile.follower_count : '0';
      }
      const stars =
        (profile.stars != null ? profile.stars : account.stars) != null
          ? Number(profile.stars != null ? profile.stars : account.stars).toFixed(
              1
            )
          : '—';
      const total =
        profile.total_ratings != null
          ? profile.total_ratings
          : account.total_ratings != null
            ? account.total_ratings
            : 0;
      els.acctStars.textContent = `Stars ${stars} · ${total} rating${
        total === 1 ? '' : 's'
      }`;
      els.headerUser.textContent = '@' + username;
      setAvatarEl(profile.avatar_url, profile.display_name, username);

      if (els.shareLinkInput) {
        els.shareLinkInput.value = state.shareUrl || '';
      }

      if (els.profileDisplayName) {
        els.profileDisplayName.value = profile.display_name || '';
        els.profileAbout.value = profile.about || '';
        els.profileLocation.value = profile.location || '';
        els.profileContact.value = profile.contact_info || '';
      }
      refreshAppVersionLabel();
    } catch (err) {
      showError(els.accountError, err.message);
    }
  }

  async function refreshAppVersionLabel() {
    if (!els.appVersionLabel) return;
    const plugin = getAppUpdatePlugin();
    if (!plugin || !isNativeAndroid()) {
      els.appVersionLabel.textContent =
        'Version (web shell) · auto-update is for the Android APK';
      return;
    }
    try {
      const info = await plugin.getInfo();
      els.appVersionLabel.textContent =
        'Version ' +
        (info.versionName || '?') +
        ' (build ' +
        (info.versionCode != null ? info.versionCode : '?') +
        ')';
    } catch {
      els.appVersionLabel.textContent = 'Version unknown';
    }
  }

  async function handleProfileSave(e) {
    e.preventDefault();
    if (!state.token) return;
    showError(els.accountError, null);
    showSuccess(els.accountSuccess, null);
    setLoading(els.profileSaveBtn, true, 'Save profile');
    try {
      await api('/profile', {
        method: 'POST',
        body: JSON.stringify({
          display_name: (els.profileDisplayName.value || '').trim(),
          about: (els.profileAbout.value || '').trim(),
          location: (els.profileLocation.value || '').trim(),
          contact_info: (els.profileContact.value || '').trim(),
        }),
      });
      showSuccess(els.accountSuccess, 'Profile saved.');
      toast('Profile saved', 'ok');
      await loadAccount();
    } catch (err) {
      showError(els.accountError, err.message || 'Could not save profile');
    } finally {
      setLoading(els.profileSaveBtn, false, 'Save profile');
    }
  }

  async function handleCopyShare() {
    try {
      let url = state.shareUrl || (els.shareLinkInput && els.shareLinkInput.value);
      if (!url) {
        const share = await api('/profile/share_link');
        state.profileSlug = share.profile_slug;
        state.shareUrl = publicShareUrl(state.profileSlug);
        url = state.shareUrl;
        if (els.shareLinkInput) els.shareLinkInput.value = url;
      }
      await copyText(url);
      toast('Link copied', 'ok');
    } catch (err) {
      toast(err.message || 'Could not copy link', 'error');
    }
  }

  function handleOpenShare() {
    const url = state.shareUrl || (els.shareLinkInput && els.shareLinkInput.value);
    if (!url) {
      toast('Share link not ready', 'error');
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  async function bootstrapApp() {
    await loadAccount();
    if (!state.token) return;
    showApp('request');
  }

  // ── Events ───────────────────────────────────────────────────────
  function bindEvents() {
    els.tabLogin.addEventListener('click', () => setAuthMode('login'));
    els.tabRegister.addEventListener('click', () => setAuthMode('register'));
    els.authForm.addEventListener('submit', handleAuth);
    els.bidForm.addEventListener('submit', handleBid);
    els.refreshBids.addEventListener('click', loadOpenBids);
    els.refreshJobs.addEventListener('click', loadJobs);
    if (els.refreshFeedback) {
      els.refreshFeedback.addEventListener('click', loadFeedback);
    }
    if (els.feedbackForm) {
      els.feedbackForm.addEventListener('submit', handleFeedbackSubmit);
    }
    if (els.refreshNearby) {
      els.refreshNearby.addEventListener('click', loadNearby);
    }
    if (els.nearbySearchBtn) {
      els.nearbySearchBtn.addEventListener('click', loadNearby);
    }
    if (els.nearbyUseGps) {
      els.nearbyUseGps.addEventListener('click', useNearbyGps);
    }
    if (els.nearbyRadius) {
      els.nearbyRadius.addEventListener('input', updateNearbyRadiusLabel);
      els.nearbyRadius.addEventListener('change', () => {
        updateNearbyRadiusLabel();
        persistNearbyPrefs();
      });
    }
    if (els.nearbyAddress) {
      els.nearbyAddress.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          loadNearby();
        }
      });
    }
    if (els.headerAccountBtn) {
      els.headerAccountBtn.addEventListener('click', () => navigate('account'));
    }
    if (els.profileForm) {
      els.profileForm.addEventListener('submit', handleProfileSave);
    }
    if (els.copyShareBtn) {
      els.copyShareBtn.addEventListener('click', handleCopyShare);
    }
    if (els.openShareBtn) {
      els.openShareBtn.addEventListener('click', handleOpenShare);
    }
    if (els.checkUpdateBtn) {
      els.checkUpdateBtn.addEventListener('click', () => {
        checkForAppUpdate({ force: true });
      });
    }
    els.logoutBtn.addEventListener('click', () => {
      clearSession();
      showAuth();
      toast('Logged out');
    });

    document.querySelectorAll('.bottom-nav button').forEach((btn) => {
      btn.addEventListener('click', () => navigate(btn.dataset.screen));
    });

    document.addEventListener('click', (e) => {
      const cancel = e.target.closest('[data-cancel]');
      if (cancel) {
        cancelBid(cancel.getAttribute('data-cancel'));
        return;
      }
      const sign = e.target.closest('[data-sign]');
      if (sign) {
        signJob(sign.getAttribute('data-sign'));
        return;
      }
      const star = e.target.closest('[data-star]');
      if (star) {
        const n = parseInt(star.getAttribute('data-star'), 10);
        const picker = star.closest('.star-picker');
        if (!picker) return;
        picker.dataset.rating = String(n);
        picker.querySelectorAll('button').forEach((b) => {
          const sn = parseInt(b.getAttribute('data-star'), 10);
          b.classList.toggle('on', sn <= n);
        });
        return;
      }
      const replyToggle = e.target.closest('[data-fb-reply-toggle]');
      if (replyToggle) {
        toggleFeedbackReply(replyToggle.getAttribute('data-fb-reply-toggle'));
        return;
      }
      const replySend = e.target.closest('[data-fb-reply-send]');
      if (replySend) {
        sendFeedbackReply(replySend.getAttribute('data-fb-reply-send'));
      }
    });

    els.locationType.addEventListener('change', () => {
      const need =
        els.locationType.value === 'physical' ||
        els.locationType.value === 'hybrid';
      els.address.required = need;
    });
  }

  // ── Auto-update (native Android APK) ─────────────────────────────
  function isNativeAndroid() {
    try {
      return !!(
        window.Capacitor &&
        typeof window.Capacitor.isNativePlatform === 'function' &&
        window.Capacitor.isNativePlatform() &&
        (window.Capacitor.getPlatform?.() === 'android' ||
          /android/i.test(navigator.userAgent || ''))
      );
    } catch {
      return false;
    }
  }

  function getAppUpdatePlugin() {
    try {
      const plugins = window.Capacitor && window.Capacitor.Plugins;
      return (plugins && plugins.AppUpdate) || null;
    } catch {
      return null;
    }
  }

  function showUpdateOverlay(opts) {
    if (!els.updateOverlay) return;
    els.updateOverlay.hidden = false;
    if (opts.title && els.updateTitle) els.updateTitle.textContent = opts.title;
    if (opts.message != null && els.updateMessage) {
      els.updateMessage.textContent = opts.message;
    }
    if (els.updateActions) {
      els.updateActions.hidden = !opts.showActions;
    }
    if (els.updateDismissBtn) {
      const mandatory = !!(pendingManifest && pendingManifest.mandatory);
      els.updateDismissBtn.hidden = mandatory;
      els.updateDismissBtn.style.display = mandatory ? 'none' : '';
    }
    if (opts.percent != null && els.updateProgressBar) {
      const p = Math.max(0, Math.min(100, opts.percent));
      els.updateProgressBar.style.width = p + '%';
      if (els.updatePercent) {
        els.updatePercent.textContent =
          opts.percentLabel != null ? opts.percentLabel : p + '%';
      }
    }
  }

  function hideUpdateOverlay() {
    if (!els.updateOverlay) return;
    els.updateOverlay.hidden = true;
    if (els.updateActions) els.updateActions.hidden = true;
    if (els.updateProgressBar) els.updateProgressBar.style.width = '0%';
    if (els.updatePercent) els.updatePercent.textContent = '';
  }

  async function fetchUpdateManifest() {
    const urls = [UPDATE_MANIFEST_URL, ...UPDATE_MANIFEST_FALLBACKS];
    let lastErr = null;
    for (const url of urls) {
      try {
        const res = await fetch(url + (url.includes('?') ? '&' : '?') + 't=' + Date.now(), {
          cache: 'no-store',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (data && (data.versionCode != null || data.versionName)) {
          return data;
        }
        throw new Error('Invalid manifest');
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('Could not fetch update manifest');
  }

  async function applyApkUpdate(manifest) {
    const plugin = getAppUpdatePlugin();
    if (!plugin) throw new Error('AppUpdate plugin unavailable');
    if (!manifest || !manifest.apkUrl) throw new Error('Manifest missing apkUrl');

    updateInFlight = true;
    showUpdateOverlay({
      title: 'Updating The RSE',
      message:
        'Downloading v' +
        (manifest.versionName || manifest.versionCode) +
        '… Android will ask you to confirm install.',
      percent: 0,
      showActions: false,
    });

    // Progress events from native plugin (attach once)
    if (!updateProgressListenerReady && plugin.addListener) {
      try {
        await plugin.addListener('downloadProgress', (ev) => {
          const pct = ev && ev.percent != null ? Number(ev.percent) : 0;
          showUpdateOverlay({
            title: 'Updating The RSE',
            message: 'Downloading update…',
            percent: pct,
            showActions: false,
          });
        });
        updateProgressListenerReady = true;
      } catch {
        /* optional */
      }
    }

    // Ensure install-unknown-apps permission
    try {
      const can = await plugin.canInstallPackages();
      if (can && can.allowed === false) {
        showUpdateOverlay({
          title: 'Allow app installs',
          message:
            'Android needs permission for The RSE to install updates. Enable it, then return here.',
          percent: 0,
          showActions: true,
        });
        await plugin.openInstallPermissionSettings();
        // Brief pause so user can grant; then continue
        await new Promise((r) => setTimeout(r, 1500));
      }
    } catch {
      /* continue; downloadAndInstall will re-check */
    }

    const payload = { url: manifest.apkUrl };
    if (manifest.sha256) payload.sha256 = String(manifest.sha256);

    let result = await plugin.downloadAndInstall(payload);
    if (result && result.needsPermission) {
      showUpdateOverlay({
        title: 'Allow app installs',
        message:
          result.message ||
          'Enable install permission for The RSE, then tap Retry update.',
        percent: 0,
        showActions: true,
      });
      try {
        await plugin.openInstallPermissionSettings();
      } catch {
        /* ignore */
      }
      updateInFlight = false;
      return;
    }

    showUpdateOverlay({
      title: 'Install ready',
      message:
        'System installer opened. Confirm Install to finish updating to v' +
        (manifest.versionName || manifest.versionCode) +
        '.',
      percent: 100,
      showActions: true,
    });
    if (els.updateRetryBtn) els.updateRetryBtn.textContent = 'Install again';
    updateInFlight = false;
  }

  async function checkForAppUpdate(opts) {
    const force = opts && opts.force;
    if (!isNativeAndroid()) return;
    const plugin = getAppUpdatePlugin();
    if (!plugin || typeof plugin.getInfo !== 'function') return;
    if (updateInFlight) return;

    try {
      const info = await plugin.getInfo();
      const currentCode = Number(info.versionCode) || 0;
      const manifest = await fetchUpdateManifest();
      pendingManifest = manifest;
      const remoteCode = Number(manifest.versionCode) || 0;
      if (!(remoteCode > currentCode)) {
        if (force) toast('You are on the latest version', 'ok');
        return;
      }

      const dismissed = parseInt(
        localStorage.getItem(STORAGE.updateDismissedCode) || '0',
        10
      );
      const mandatory = !!manifest.mandatory;
      if (!force && !mandatory && dismissed === remoteCode) {
        return;
      }

      // Automatic: download + launch installer (system still confirms install)
      await applyApkUpdate(manifest);
    } catch (err) {
      console.warn('App update check failed', err);
      if (force) {
        showUpdateOverlay({
          title: 'Update failed',
          message: (err && err.message) || 'Could not update',
          percent: 0,
          showActions: true,
        });
      }
      updateInFlight = false;
    }
  }

  // ── Boot ─────────────────────────────────────────────────────────
  async function init() {
    bindEvents();
    setAuthMode('login');
    if (state.username) els.username.value = state.username;

    if (els.updateRetryBtn) {
      els.updateRetryBtn.addEventListener('click', async () => {
        if (!pendingManifest) {
          await checkForAppUpdate({ force: true });
          return;
        }
        try {
          await applyApkUpdate(pendingManifest);
        } catch (err) {
          showUpdateOverlay({
            title: 'Update failed',
            message: (err && err.message) || 'Could not update',
            percent: 0,
            showActions: true,
          });
          updateInFlight = false;
        }
      });
    }
    if (els.updateDismissBtn) {
      els.updateDismissBtn.addEventListener('click', () => {
        if (
          pendingManifest &&
          pendingManifest.mandatory &&
          pendingManifest.versionCode != null
        ) {
          toast('This update is required', 'error');
          return;
        }
        if (pendingManifest && pendingManifest.versionCode != null) {
          localStorage.setItem(
            STORAGE.updateDismissedCode,
            String(pendingManifest.versionCode)
          );
        }
        hideUpdateOverlay();
        updateInFlight = false;
      });
    }

    // Quick connectivity check (non-blocking)
    fetch(`${API_URL}/ping`).catch(() => {
      /* offline — user will see errors on actions */
    });

    // Auto-update check as early as possible on native builds
    checkForAppUpdate().catch(() => {});

    if (state.token) {
      try {
        await bootstrapApp();
      } catch {
        clearSession();
        showAuth();
      }
    } else {
      showAuth();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
