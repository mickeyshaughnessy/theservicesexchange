/**
 * The RSE demand-side mobile app
 * Talks ONLY to https://rse-api.com:5003 — never the marketing website.
 */
(function () {
  'use strict';

  const API_URL = 'https://rse-api.com:5003';
  const STORAGE = {
    token: 'rse_app_token',
    username: 'rse_app_username',
  };

  const state = {
    token: localStorage.getItem(STORAGE.token) || null,
    username: localStorage.getItem(STORAGE.username) || null,
    account: null,
    authMode: 'login', // login | register
    screen: 'request',
  };

  // ── DOM ──────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const els = {
    body: document.body,
    header: $('appHeader'),
    headerUser: $('headerUser'),
    screenAuth: $('screen-auth'),
    screenRequest: $('screen-request'),
    screenJobs: $('screen-jobs'),
    screenAccount: $('screen-account'),
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
    acctType: $('acctType'),
    acctRep: $('acctRep'),
    acctJobs: $('acctJobs'),
    acctStars: $('acctStars'),
    accountError: $('accountError'),
    logoutBtn: $('logoutBtn'),
    toast: $('toast'),
  };

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
    localStorage.removeItem(STORAGE.token);
    localStorage.removeItem(STORAGE.username);
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
    if (name === 'account') loadAccount();
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
      toast('Signed in', 'ok');
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
              <button type="button" class="btn btn-sm btn-danger" data-cancel="${id}">Cancel</button>
            </div>
          </div>`;
        })
        .join('');
    } catch (err) {
      els.openBids.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
    }
  }

  async function cancelBid(bidId) {
    if (!confirm('Cancel this open request?')) return;
    try {
      await api('/cancel_bid', {
        method: 'POST',
        body: JSON.stringify({ bid_id: bidId }),
      });
      toast('Request cancelled', 'ok');
      await loadOpenBids();
    } catch (err) {
      toast(err.message || 'Cancel failed', 'error');
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

  // ── Account ──────────────────────────────────────────────────────
  async function loadAccount() {
    if (!state.token) return;
    showError(els.accountError, null);
    try {
      const data = await api('/account');
      if (data.user_type && data.user_type !== 'demand') {
        clearSession();
        showAuth();
        showError(
          els.authError,
          'This app is for demand accounts only.'
        );
        return;
      }
      state.account = data;
      els.acctName.textContent = '@' + (data.username || state.username);
      els.acctType.textContent = data.user_type || 'demand';
      els.acctRep.textContent =
        data.reputation_score != null
          ? Number(data.reputation_score).toFixed(2)
          : '—';
      els.acctJobs.textContent =
        data.completed_jobs != null ? data.completed_jobs : '—';
      const stars = data.stars != null ? Number(data.stars).toFixed(1) : '—';
      const total = data.total_ratings != null ? data.total_ratings : 0;
      els.acctStars.textContent = `Stars ${stars} · ${total} rating${total === 1 ? '' : 's'}`;
      els.headerUser.textContent = '@' + (data.username || state.username);
    } catch (err) {
      showError(els.accountError, err.message);
    }
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
      }
    });

    els.locationType.addEventListener('change', () => {
      const need =
        els.locationType.value === 'physical' ||
        els.locationType.value === 'hybrid';
      els.address.required = need;
    });
  }

  // ── Boot ─────────────────────────────────────────────────────────
  async function init() {
    bindEvents();
    setAuthMode('login');
    if (state.username) els.username.value = state.username;

    // Quick connectivity check (non-blocking)
    fetch(`${API_URL}/ping`).catch(() => {
      /* offline — user will see errors on actions */
    });

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
