/**
 * Service Exchange Frontend Script
 * -------------------------------
 * Handles all frontend interactions, API calls, and UI updates.
 */

const API_URL = 'https://rse-api.com:5003';
const STORAGE_KEYS = {
    AUTH_TOKEN: 'auth_token',
    USERNAME: 'current_username',
    PROVIDER_PROFILE: 'provider_capabilities_profile',
    PENDING_SERVICE: 'rse_pending_service',
    PENDING_INTENT: 'rse_pending_intent'
};

// Global state
const AppState = {
    authToken: null,
    currentUser: null,
    currentUsername: null,
    outstandingBids: [],
    completedJobs: [],
    activeJobs: [],
    partyInvites: [],
    conversations: [],
    currentConversation: null,
    bulletinPosts: [],
    userLocation: null,
    providerProfile: null
};

// Initialize when DOM loads
document.addEventListener('DOMContentLoaded', function() {
    // Restore authentication state
    AppState.authToken = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
    AppState.currentUsername = localStorage.getItem(STORAGE_KEYS.USERNAME);
    
    // Make available globally for inline handlers
    window.authToken = AppState.authToken;
    window.currentUsername = AppState.currentUsername;
    
    if (AppState.authToken && AppState.currentUsername) {
        loadAccountData().then(() => {
            // Deep link: index.html?open=bid after auth
            const open = new URLSearchParams(location.search).get('open');
            if (open === 'bid') {
                showBuyerForm();
            } else {
                resumePendingBuyerIntent();
            }
        });
        updateUIForLoggedInUser();
    } else {
        // Guest deep link: stash intent and open auth
        const open = new URLSearchParams(location.search).get('open');
        if (open === 'bid') {
            sessionStorage.setItem(STORAGE_KEYS.PENDING_INTENT, 'bid');
            // Defer until listeners exist
            setTimeout(() => {
                showAuth({
                    intent: 'bid',
                    defaultTab: 'register',
                    defaultType: 'demand',
                    title: 'Create an account to post a request'
                });
            }, 0);
        }
    }
    
    // Set up form event listeners
    setupEventListeners();
    initializeGrabJobPage();
    
    // Load platform stats for homepage
    loadPlatformStats();

    // Light inbox badge poll for returning users
    if (AppState.authToken && !window._rseInboxPoll) {
        window._rseInboxPoll = setInterval(() => {
            if (AppState.authToken) refreshInboxBadge();
        }, 60000);
    }

    enhanceKeyboardServiceTiles();
    registerServiceWorker();
    initServiceAutocompletes();
    initHomeBidForm();
});

/** Make service tiles / tags keyboard-activatable */
function enhanceKeyboardServiceTiles() {
    document.querySelectorAll('.service-grid-item[onclick], .service-tag[onclick]').forEach((el) => {
        if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
        if (!el.getAttribute('role')) el.setAttribute('role', 'button');
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                el.click();
            }
        });
    });
}

function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    // Only on secure contexts / production-like hosts
    const host = location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
        // still allow local testing
    }
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch((err) => {
            console.log('SW registration skipped:', err && err.message);
        });
    });
}

// Load platform statistics
async function loadPlatformStats() {
    try {
        const response = await fetch(`${API_URL}/stats`);
        if (response.ok) {
            const stats = await response.json();
            const els = {
                demand: document.getElementById('statDemand'),
                supply: document.getElementById('statSupply'),
                active: document.getElementById('statActive'),
                completed: document.getElementById('statCompleted')
            };
            if (els.demand) els.demand.textContent = stats.demand_signups || 0;
            if (els.supply) els.supply.textContent = stats.supply_signups || 0;
            if (els.active) els.active.textContent = stats.active_requests || 0;
            if (els.completed) els.completed.textContent = stats.completed_jobs || 0;
        }
    } catch (error) {
        console.log('Could not load platform stats:', error);
    }
}

// Set up all event listeners
function setupEventListeners() {
    const forms = {
        login: document.getElementById('loginForm'),
        register: document.getElementById('registerForm'),
        bid: document.getElementById('bidForm'),
        chat: document.getElementById('chatForm'),
        reply: document.getElementById('replyForm'),
        bulletin: document.getElementById('bulletinForm'),
        nearby: document.getElementById('nearbyForm'),
        filter: document.getElementById('filterForm')
    };
    
    if (forms.login) forms.login.addEventListener('submit', handleLogin);
    if (forms.register) forms.register.addEventListener('submit', handleRegister);
    
    if (forms.bid) {
        forms.bid.addEventListener('submit', handleBidSubmission);
        const locationType = document.getElementById('bidLocationType');
        if (locationType) {
            locationType.addEventListener('change', (e) => {
                const addressField = document.getElementById('addressField');
                if (addressField) {
                    addressField.style.display = e.target.value === 'remote' ? 'none' : 'block';
                }
            });
        }
    }
    
    if (forms.chat) forms.chat.addEventListener('submit', handleChatMessage);
    if (forms.reply) forms.reply.addEventListener('submit', handleReply);
    if (forms.bulletin) forms.bulletin.addEventListener('submit', handleBulletinPost);
    if (forms.nearby) forms.nearby.addEventListener('submit', handleNearbySearch);
    if (forms.filter) forms.filter.addEventListener('submit', handleFilterApplication);

    setupAccountDropdown();

    // Close account sheet when mobile nav collapses
    const navCollapse = document.getElementById('navbarNav');
    if (navCollapse && !navCollapse.dataset.accountCloseBound) {
        navCollapse.dataset.accountCloseBound = '1';
        navCollapse.addEventListener('hide.bs.collapse', () => {
            document.querySelectorAll('.account-dropdown.open').forEach((d) => {
                d.classList.remove('open');
                const b = d.querySelector('.account-btn');
                if (b) b.setAttribute('aria-expanded', 'false');
            });
        });
    }
}

// Utility Functions
function showToast(message, type = 'info', durationMs = 3500) {
    let container = document.getElementById('toastContainerRse');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainerRse';
        container.className = 'toast-container-rse';
        container.setAttribute('aria-live', 'polite');
        document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast-rse ${type}`;
    el.setAttribute('role', 'status');
    el.textContent = message;
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 220);
    }, durationMs);
}

function setupAccountDropdown() {
    document.querySelectorAll('.account-dropdown').forEach((dropdown) => {
        const btn = dropdown.querySelector('.account-btn');
        if (!btn || btn.dataset.accountToggleBound === '1') return;
        btn.dataset.accountToggleBound = '1';
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute('aria-haspopup', 'true');
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const willOpen = !dropdown.classList.contains('open');
            document.querySelectorAll('.account-dropdown.open').forEach((d) => {
                if (d !== dropdown) {
                    d.classList.remove('open');
                    const b = d.querySelector('.account-btn');
                    if (b) b.setAttribute('aria-expanded', 'false');
                }
            });
            dropdown.classList.toggle('open', willOpen);
            btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        });
    });

    if (!window._rseAccountOutsideBound) {
        window._rseAccountOutsideBound = true;
        document.addEventListener('click', (e) => {
            if (e.target.closest('.account-dropdown')) return;
            document.querySelectorAll('.account-dropdown.open').forEach((d) => {
                d.classList.remove('open');
                const b = d.querySelector('.account-btn');
                if (b) b.setAttribute('aria-expanded', 'false');
            });
        });
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            document.querySelectorAll('.account-dropdown.open').forEach((d) => {
                d.classList.remove('open');
                const b = d.querySelector('.account-btn');
                if (b) b.setAttribute('aria-expanded', 'false');
            });
        });
    }
}

function showError(message, containerId = 'authError') {
    const errorDiv = document.getElementById(containerId);
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    } else {
        console.error(message);
        showToast(message, 'error');
    }
}

function setLoading(isLoading, buttonId) {
    const button = document.getElementById(buttonId);
    if (button) {
        if (isLoading) {
            button.classList.add('loading');
            button.dataset.originalText = button.textContent;
            button.textContent = 'Loading...';
            button.disabled = true;
        } else {
            button.classList.remove('loading');
            button.textContent = button.dataset.originalText || (buttonId.includes('login') ? 'Login' : 'Register');
            button.disabled = false;
        }
    }
}

function updateUIForLoggedInUser() {
    const elements = {
        login: document.getElementById('loginButton'),
        account: document.getElementById('accountDropdown'),
        chat: document.getElementById('chatButton'),
        bulletin: document.getElementById('bulletinButton')
    };
    
    if (elements.login) elements.login.style.display = 'none';
    if (elements.account) elements.account.style.display = 'inline-block';
    if (elements.chat) elements.chat.style.display = 'inline-block';
    if (elements.bulletin) elements.bulletin.style.display = 'inline-block';
}

function updateUIForLoggedOutUser() {
    const elements = {
        login: document.getElementById('loginButton'),
        account: document.getElementById('accountDropdown'),
        chat: document.getElementById('chatButton'),
        bulletin: document.getElementById('bulletinButton')
    };
    
    if (elements.login) elements.login.style.display = 'inline-block';
    if (elements.account) elements.account.style.display = 'none';
    if (elements.chat) elements.chat.style.display = 'none';
    if (elements.bulletin) elements.bulletin.style.display = 'none';

    const strip = document.getElementById('userHomeStrip');
    if (strip) strip.style.display = 'none';
    clearInboxBadge();
}

function requestUserLocation() {
    return new Promise((resolve) => {
        if (AppState.userLocation) {
            resolve(AppState.userLocation);
            return;
        }

        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    AppState.userLocation = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    };
                    resolve(AppState.userLocation);
                },
                (error) => {
                    console.warn('Geolocation error:', error);
                    resolve(null);
                },
                { timeout: 10000, enableHighAccuracy: false }
            );
        } else {
            resolve(null);
        }
    });
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    const now = Date.now();
    const diff = now - timestamp;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
}

// Authentication Functions
async function handleLogin(e) {
    e.preventDefault();
    
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    
    if (!username || !password) {
        showError('Please enter both username and password');
        return;
    }
    
    setLoading(true, 'loginSubmitBtn');
    try {
        await performLogin(username, password, { quiet: false });
    } catch (error) {
        showError(error.message || 'Login failed. Please check your credentials.');
        console.error('Login error:', error);
    } finally {
        setLoading(false, 'loginSubmitBtn');
    }
}

async function performLogin(username, password, { quiet } = {}) {
    const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ username, password })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || 'Login failed');
    }
    AppState.authToken = data.access_token;
    AppState.currentUsername = username;
    window.authToken = AppState.authToken;
    window.currentUsername = AppState.currentUsername;
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, AppState.authToken);
    localStorage.setItem(STORAGE_KEYS.USERNAME, AppState.currentUsername);
    const authModal = document.getElementById('authModal');
    if (authModal) {
        const modal = bootstrap.Modal.getInstance(authModal);
        if (modal) modal.hide();
    }
    updateUIForLoggedInUser();
    await loadAccountData();
    setupAccountDropdown();
    if (!quiet) showToast('Logged in successfully', 'success');
    await resumePendingBuyerIntent();
    return data;
}

async function handleRegister(e) {
    e.preventDefault();
    
    const username = document.getElementById('regUsername').value.trim();
    const password = document.getElementById('regPassword').value;
    const userTypeEl = document.querySelector('input[name="userType"]:checked');
    const userType = userTypeEl ? userTypeEl.value : null;
    
    if (!username || !password) {
        showError('Please enter both username and password');
        return;
    }
    
    if (password.length < 8) {
        showError('Password must be at least 8 characters long');
        return;
    }
    
    if (!userType) {
        showError('Please select whether you want to buy or provide services');
        return;
    }
    
    setLoading(true, 'registerSubmitBtn');
    
    try {
        const response = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username, password, user_type: userType })
        });
        
        if (response.ok) {
            try {
                await performLogin(username, password, { quiet: true });
                showToast('Account created — you are logged in', 'success');
            } catch (loginErr) {
                setLoading(false, 'registerSubmitBtn');
                showToast('Registered — please log in', 'info');
                const loginTab = document.querySelector('a[href="#login"]');
                if (loginTab) {
                    const tab = new bootstrap.Tab(loginTab);
                    tab.show();
                }
                const loginUser = document.getElementById('loginUsername');
                if (loginUser) loginUser.value = username;
            }
            setLoading(false, 'registerSubmitBtn');
        } else {
            setLoading(false, 'registerSubmitBtn');
            const errorData = await response.json().catch(() => ({}));
            showError(errorData.error || 'Registration failed. Please try a different username.');
        }
    } catch (error) {
        setLoading(false, 'registerSubmitBtn');
        showError('Network error. Please check your connection and try again.');
        console.error('Registration error:', error);
    }
}

function logout(opts = {}) {
    const quiet = opts && opts.quiet;
    AppState.authToken = null;
    AppState.currentUser = null;
    AppState.currentUsername = null;
    
    window.authToken = null;
    window.currentUser = null;
    window.currentUsername = null;
    
    localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USERNAME);
    
    updateUIForLoggedOutUser();
    AppState.outstandingBids = [];
    AppState.completedJobs = [];
    AppState.activeJobs = [];
    
    updateProviderDashboard();
    if (!quiet) showToast('Logged out', 'info');
}

// Account Management Functions
async function loadAccountData() {
    if (!AppState.authToken || !AppState.currentUsername) return;
    
    try {
        const accountResponse = await fetch(`${API_URL}/account`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (accountResponse.ok) {
            AppState.currentUser = await accountResponse.json();
            window.currentUser = AppState.currentUser; // Sync global
            updateAccountDisplay();
        } else if (accountResponse.status === 401) {
            showToast('Session expired — please log in again', 'info');
            logout({ quiet: true });
            return;
        }
        
        await Promise.all([loadOutstandingBids(), loadCompletedJobs()]);
        updateReturningUserHome();
        refreshInboxBadge();
        if (window.refreshProviderReadiness) window.refreshProviderReadiness();
        
    } catch (error) {
        console.error('Error loading account data:', error);
    }
}

/**
 * Role-aware home strip for returning + new logged-in users (index.html).
 */
function updateReturningUserHome() {
    const strip = document.getElementById('userHomeStrip');
    if (!strip) return;

    if (!AppState.authToken || !AppState.currentUser) {
        strip.style.display = 'none';
        return;
    }

    strip.style.display = 'block';
    const u = AppState.currentUser;
    const type = u.user_type || (u.identity && u.identity.user_type) || '';
    const isSupply = type === 'supply';
    const isDemand = type === 'demand';
    const name = u.username || AppState.currentUsername || 'operator';
    const active = AppState.activeJobs || [];
    const bids = AppState.outstandingBids || [];
    const completed = AppState.completedJobs || [];
    const invites = (AppState.partyInvites || []).filter((pi) => pi.invite_status === 'invited');

    const titleEl = document.getElementById('userHomeTitle');
    const subEl = document.getElementById('userHomeSub');
    const eyebrow = document.getElementById('userHomeEyebrow');
    const actions = document.getElementById('userHomeActions');
    const grid = document.getElementById('userHomeGrid');
    const checklist = document.getElementById('userHomeChecklist');

    if (eyebrow) {
        eyebrow.textContent = isSupply ? '// Provider console' : isDemand ? '// Buyer console' : '// Your console';
    }
    if (titleEl) titleEl.textContent = `Welcome back, ${name}`;

    const seatLabel = u.seat_status === 'valid'
        ? 'Seat active'
        : (u.wallet_address ? `Seat: ${u.seat_status || 'pending'}` : 'No wallet linked');

    if (subEl) {
        if (isSupply) {
            subEl.textContent = `${active.length} active job${active.length === 1 ? '' : 's'} · ${completed.length} completed · ${seatLabel}`;
        } else {
            subEl.textContent = `${bids.length} open request${bids.length === 1 ? '' : 's'} · ${active.length} active · ${completed.length} completed`;
        }
    }

    if (actions) {
        if (isSupply) {
            actions.innerHTML = `
                <a class="btn btn-hero-primary" href="grab_job.html">Find Work</a>
                <button type="button" class="btn btn-hero-secondary" onclick="showChat()">Inbox</button>
                <a class="btn btn-hero-secondary" href="profile.html">Profile</a>
            `;
        } else {
            actions.innerHTML = `
                <button type="button" class="btn btn-hero-primary" onclick="showBuyerForm()">Post request</button>
                <button type="button" class="btn btn-hero-secondary" onclick="showChat()">Inbox</button>
                <a class="btn btn-hero-secondary" href="campaigns.html">Campaigns</a>
            `;
        }
    }

    if (grid) {
        const tiles = [];
        if (isSupply || !isDemand) {
            tiles.push({ label: 'Active jobs', value: String(active.length), hint: active[0] ? (typeof active[0].service === 'object' ? 'In progress' : String(active[0].service).slice(0, 40)) : 'Grab a match' });
            tiles.push({ label: 'Seat', value: u.seat_status === 'valid' ? 'OK' : '—', hint: seatLabel });
        }
        if (isDemand || !isSupply) {
            tiles.push({ label: 'Open requests', value: String(bids.length), hint: bids[0] ? 'Waiting for providers' : 'Post your first' });
            tiles.push({ label: 'Active services', value: String(active.length), hint: invites.length ? `${invites.length} party invite(s)` : 'Matched work' });
        }
        tiles.push({ label: 'Completed', value: String(completed.length), hint: 'Reputation history' });
        grid.innerHTML = tiles.map((t) => `
            <div class="user-home-tile">
                <div class="user-home-tile-value">${escapeHtml(t.value)}</div>
                <div class="user-home-tile-label">${escapeHtml(t.label)}</div>
                <div class="user-home-tile-hint">${escapeHtml(t.hint)}</div>
            </div>
        `).join('');
    }

    // First-session checklist for users with little activity
    if (checklist) {
        const isNew = bids.length === 0 && active.length === 0 && completed.length === 0;
        if (isNew) {
            checklist.style.display = 'block';
            if (isSupply) {
                checklist.innerHTML = `
                    <h3 class="user-home-check-title">// Provider checklist</h3>
                    <ol class="user-home-check-list">
                        <li>Describe capabilities on <a href="grab_job.html">Find Work</a></li>
                        <li>Link wallet + seat on <a href="profile.html">Profile</a> (email mickey@theservicesexchange.com for a seat)</li>
                        <li>Tap <strong>Grab Job</strong> to get matched</li>
                        <li>Complete &amp; rate when the job is done</li>
                    </ol>
                `;
            } else {
                checklist.innerHTML = `
                    <h3 class="user-home-check-title">// Buyer checklist</h3>
                    <ol class="user-home-check-list">
                        <li><button type="button" class="btn btn-link p-0 align-baseline" onclick="showBuyerForm()">Post a service request</button></li>
                        <li>Wait for a provider match (watch Account → Active Services)</li>
                        <li>Coordinate in job chat, then complete &amp; rate</li>
                    </ol>
                `;
            }
        } else {
            checklist.style.display = 'none';
            checklist.innerHTML = '';
        }
    }
}

async function refreshInboxBadge() {
    const btn = document.getElementById('chatButton');
    if (!btn || !AppState.authToken) {
        clearInboxBadge();
        return;
    }
    try {
        const response = await fetch(`${API_URL}/chat/conversations`, {
            headers: { Authorization: `Bearer ${AppState.authToken}` }
        });
        if (!response.ok) return;
        const data = await response.json();
        const convos = data.conversations || [];
        AppState.conversations = convos;
        const unread = convos.filter((c) => c.unread).length;
        setInboxBadge(unread);
    } catch (e) {
        /* silent */
    }
}

function setInboxBadge(count) {
    const btn = document.getElementById('chatButton');
    if (!btn) return;
    let badge = document.getElementById('inboxBadge');
    if (count > 0) {
        if (!badge) {
            badge = document.createElement('span');
            badge.id = 'inboxBadge';
            badge.className = 'inbox-badge';
            btn.style.position = 'relative';
            btn.appendChild(badge);
        }
        badge.textContent = count > 9 ? '9+' : String(count);
        badge.style.display = 'inline-flex';
        btn.setAttribute('aria-label', `Inbox, ${count} unread`);
    } else if (badge) {
        badge.style.display = 'none';
        btn.setAttribute('aria-label', 'Inbox');
    }
}

function clearInboxBadge() {
    const badge = document.getElementById('inboxBadge');
    if (badge) badge.style.display = 'none';
}

/** After no-match on grab, show sample open market activity */
async function showNoMatchMarketHints() {
    const result = document.getElementById('grabJobResult');
    if (!result) return;
    try {
        const response = await fetch(`${API_URL}/exchange_data?limit=12`);
        if (!response.ok) return;
        const data = await response.json();
        const bids = data.active_bids || [];
        if (!bids.length) {
            result.innerHTML += `<p class="small-text mt-2 mb-0">Market is quiet right now — check <a href="campaigns.html">Campaigns</a> or try again later.</p>`;
            return;
        }
        const samples = bids.slice(0, 4).map((b) => {
            const svc = typeof b.service === 'object' ? (b.service.name || JSON.stringify(b.service)) : String(b.service || '');
            const price = b.price != null ? `${b.currency || 'USD'} ${b.price}` : '';
            return `<li><strong>${escapeHtml(svc.slice(0, 48))}</strong>${price ? ` · ${escapeHtml(price)}` : ''}</li>`;
        }).join('');
        result.innerHTML += `
            <div class="mt-3 pt-2" style="border-top:1px solid rgba(0,255,255,0.2);">
                <p class="small-text mb-1">Open requests on the exchange (tune capabilities to match):</p>
                <ul class="small-text mb-2" style="padding-left:1.2rem;">${samples}</ul>
                <p class="small-text mb-0">Tips: widen max distance, add sensor/payload keywords, or try remote location type.</p>
            </div>
        `;
    } catch (e) {
        /* ignore */
    }
}

function updateAccountDisplay() {
    if (!AppState.currentUser) return;
    
    const els = {
        username: document.getElementById('accountUsername'),
        displayName: document.getElementById('accountDisplayName'),
        starDisplay: document.getElementById('starDisplay'),
        ratingText: document.getElementById('ratingText')
    };
    
    const u = AppState.currentUser;
    const ident = u.identity || {};
    const typeLabel = u.user_type || ident.user_type || '';
    const publicId = ident.public_id || u.username;
    if (els.username) els.username.textContent = u.username + (typeLabel ? ` (${typeLabel})` : '');
    if (els.displayName) {
        els.displayName.textContent = u.username;
        let pill = document.getElementById('accountIdentityPill');
        if (!pill && els.displayName.parentElement) {
            pill = document.createElement('span');
            pill.id = 'accountIdentityPill';
            pill.className = 'identity-pill' + (String(publicId).startsWith('seat:') ? ' seat' : '');
            els.displayName.parentElement.appendChild(pill);
        }
        if (pill) {
            pill.textContent = publicId;
            pill.className = 'identity-pill' + (String(publicId).startsWith('seat:') ? ' seat' : '');
            pill.title = typeLabel ? `user_type=${typeLabel}` : 'identity';
        }
    }
    
    if (els.starDisplay && els.ratingText) {
        const stars = Math.round(AppState.currentUser.stars || 0);
        const starDisplayText = '★'.repeat(Math.min(stars, 5)) + '☆'.repeat(Math.max(5 - stars, 0));
        els.starDisplay.textContent = starDisplayText;
        els.ratingText.textContent = `${(AppState.currentUser.reputation_score || 0).toFixed(1)} (${AppState.currentUser.total_ratings || 0} ratings)`;
    }

    ensureAccountQuickLinks(typeLabel);
}

/** Quick nav inside account sheet for returning users */
function ensureAccountQuickLinks(typeLabel) {
    document.querySelectorAll('.account-window').forEach((win) => {
        let row = win.querySelector('.account-quick-links');
        if (!row) {
            row = document.createElement('div');
            row.className = 'account-section account-quick-links';
            const header = win.querySelector('.account-header');
            if (header && header.nextSibling) {
                win.insertBefore(row, header.nextSibling);
            } else {
                win.prepend(row);
            }
        }
        const isSupply = typeLabel === 'supply';
        row.innerHTML = `
            <h6>Quick links</h6>
            <div class="d-flex flex-wrap gap-2">
                <a class="btn btn-sm btn-outline-light" href="profile.html">Profile</a>
                <a class="btn btn-sm btn-outline-light" href="portfolio.html">Portfolio</a>
                ${isSupply
                    ? '<a class="btn btn-sm btn-outline-light" href="grab_job.html">Find Work</a>'
                    : '<button type="button" class="btn btn-sm btn-outline-light" onclick="showBuyerForm()">Post request</button>'}
                <a class="btn btn-sm btn-outline-light" href="campaigns.html">Campaigns</a>
            </div>
        `;
    });
}

async function loadOutstandingBids() {
    const bidsContainer = document.getElementById('outstandingBids');
    const loadingSpinner = document.getElementById('bidsLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/my_bids`, {
            headers: {'Authorization': `Bearer ${AppState.authToken}`}
        });
        
        if (response.ok) {
            const data = await response.json();
            AppState.outstandingBids = data.bids || [];
            updateBidsDisplay();
        } else if (bidsContainer) {
            bidsContainer.innerHTML = '<p class="text-danger">Error loading requests</p>';
        }
    } catch (error) {
        if (bidsContainer) {
            bidsContainer.innerHTML = '<p class="text-danger">Network error</p>';
        }
    } finally {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
    }
}

function updateBidsDisplay() {
    const container = document.getElementById('outstandingBids');
    if (!container) return;
    
    if (AppState.outstandingBids.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No outstanding requests. <button type="button" class="btn btn-link btn-sm p-0 align-baseline" onclick="showBuyerForm()">Post one</button></p>';
        return;
    }
    
    container.innerHTML = AppState.outstandingBids.map(bid => `
        <div class="bid-item">
            <h6>${typeof bid.service === 'object' ? escapeHtml(JSON.stringify(bid.service)) : escapeHtml(bid.service)}</h6>
            <p>Price: ${escapeHtml(bid.currency || 'USD')} ${bid.price} • Expires: ${new Date(bid.end_time * 1000).toLocaleString()}</p>
            ${bid.location_type !== 'remote' ? `<p class="text-muted">Location: ${escapeHtml(bid.address || 'Physical service')}</p>` : '<p class="text-muted">Remote service</p>'}
            <div class="bid-actions mt-2">
                <button type="button" class="btn btn-danger btn-sm" onclick="cancelBid('${bid.bid_id}')">Cancel</button>
            </div>
        </div>
    `).join('');
}

async function loadCompletedJobs() {
    const elements = {
        jobsContainer: document.getElementById('completedJobs'),
        jobsLoading: document.getElementById('jobsLoading'),
        activeContainer: document.getElementById('activeJobs'),
        activeLoading: document.getElementById('activeJobsLoading')
    };
    
    if (elements.jobsLoading) elements.jobsLoading.style.display = 'block';
    if (elements.activeLoading) elements.activeLoading.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/my_jobs`, {
            headers: {'Authorization': `Bearer ${AppState.authToken}`}
        });
        
        if (response.ok) {
            const data = await response.json();
            AppState.completedJobs = data.completed_jobs || [];
            AppState.activeJobs = data.active_jobs || [];
            AppState.partyInvites = data.party_invites || [];
            updateJobsDisplay();
            updateActiveJobsDisplay();
            updateProviderDashboard();
            updateReturningUserHome();
        }
    } catch (error) {
        console.error('Error loading jobs:', error);
    } finally {
        if (elements.jobsLoading) elements.jobsLoading.style.display = 'none';
        if (elements.activeLoading) elements.activeLoading.style.display = 'none';
    }
}

function partyBadgesHtml(party) {
    if (!party || !party.length) return '';
    const badges = party.map(p =>
        `<span class="badge bg-secondary me-1" title="${Math.round(p.share * 100)}% share">${escapeHtml(p.member_username)}: ${escapeHtml(p.status)}</span>`
    ).join('');
    return `<div class="mt-1">${badges}</div>`;
}

function updateActiveJobsDisplay() {
    const container = document.getElementById('activeJobs');
    if (!container) return;

    const invites = (AppState.partyInvites || []).filter(pi => pi.invite_status === 'invited' && pi.job_status === 'accepted');
    const coProviding = (AppState.partyInvites || []).filter(pi => pi.invite_status === 'accepted' && pi.job_status === 'accepted');

    if (AppState.activeJobs.length === 0 && invites.length === 0 && coProviding.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No active services yet. <a href="grab_job.html">Find work</a> or <button type="button" class="btn btn-link btn-sm p-0 align-baseline" onclick="showBuyerForm()">post a request</button>.</p>';
        return;
    }

    const activeHtml = AppState.activeJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service)}</h6>
            <p>Price: ${escapeHtml(job.currency || 'USD')} ${job.price} • Accepted: ${new Date(job.accepted_at * 1000).toLocaleDateString()}</p>
            <p class="text-muted">Role: ${escapeHtml(job.role)} • Partner: ${escapeHtml(job.counterparty)}</p>
            ${job.location_type !== 'remote' ? `<small class="text-muted">Location: ${escapeHtml(job.address || 'Physical service')}</small>` : '<small class="text-muted">Remote service</small>'}
            ${partyBadgesHtml(job.party)}
            <div class="mt-1 d-flex gap-2 flex-wrap">
                <button type="button" class="btn btn-sm btn-outline-light" onclick="openJobChannel('${job.job_id}')">💬 Job chat</button>
                <button type="button" class="btn btn-sm btn-primary" onclick="signJobPrompt('${job.job_id}')">Complete &amp; rate</button>
                ${job.role === 'provider' ? `<button type="button" class="btn btn-sm btn-outline-danger" onclick="rejectJobPrompt('${job.job_id}')">Reject</button>` : ''}
                ${job.role === 'provider' ? `<button type="button" class="btn btn-sm btn-outline-light" onclick="inviteToJobParty('${job.job_id}', 'supply')">+ Co-provider</button>` : ''}
                ${job.role === 'buyer' ? `<button type="button" class="btn btn-sm btn-outline-light" onclick="inviteToJobParty('${job.job_id}', 'demand')">+ Co-buyer</button>` : ''}
                ${(job.role === 'provider' || job.role === 'buyer') ? `<button type="button" class="btn btn-sm btn-outline-danger" onclick="fileJobDispute('${job.job_id}')">Dispute</button>` : ''}
            </div>
        </div>
    `).join('');

    const inviteHtml = invites.map(pi => `
        <div class="job-item">
            <h6>${typeof pi.service === 'object' ? escapeHtml(JSON.stringify(pi.service)) : escapeHtml(pi.service)}</h6>
            <p class="text-muted">${escapeHtml(pi.side || 'supply')} invite • share: ${pi.share != null ? Math.round(pi.share * 100) + '%' : 'n/a'} (attribution)</p>
            <div class="d-flex gap-2">
                <button class="btn btn-sm btn-outline-light" onclick="respondToPartyInvite('${pi.job_id}', 'accept')">Accept</button>
                <button class="btn btn-sm btn-outline-danger" onclick="respondToPartyInvite('${pi.job_id}', 'decline')">Decline</button>
            </div>
        </div>
    `).join('');

    const coProvidingHtml = coProviding.map(pi => `
        <div class="job-item">
            <h6>${typeof pi.service === 'object' ? escapeHtml(JSON.stringify(pi.service)) : escapeHtml(pi.service)}</h6>
            <p class="text-muted">Co-providing with ${escapeHtml(pi.primary_provider)} • Your share: ${Math.round(pi.share * 100)}% (rep credit)</p>
        </div>
    `).join('');

    container.innerHTML = activeHtml + inviteHtml + coProvidingHtml;
}

function updateJobsDisplay() {
    const container = document.getElementById('completedJobs');
    if (!container) return;

    const completedAsParty = (AppState.partyInvites || []).filter(pi => pi.invite_status === 'accepted' && pi.job_status === 'completed');

    if (AppState.completedJobs.length === 0 && completedAsParty.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No completed services</p>';
        return;
    }

    const completedHtml = AppState.completedJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service)}</h6>
            <p>Price: ${escapeHtml(job.currency || 'USD')} ${job.price} • Completed: ${new Date(job.completed_at * 1000).toLocaleDateString()}</p>
            <div class="d-flex justify-content-between">
                <small>Role: ${escapeHtml(job.role)}</small>
                <small>Rating: ${job.their_rating ? '★'.repeat(job.their_rating) : 'Not rated'}</small>
            </div>
            ${partyBadgesHtml(job.party)}
            ${(job.role === 'provider' || job.role === 'buyer') ? `<button class="btn btn-sm btn-link text-danger p-0 mt-1" onclick="fileJobDispute('${job.job_id}')">File dispute</button>` : ''}
        </div>
    `).join('');

    const partyCompletedHtml = completedAsParty.map(pi => `
        <div class="job-item">
            <h6>${typeof pi.service === 'object' ? escapeHtml(JSON.stringify(pi.service)) : escapeHtml(pi.service)}</h6>
            <p class="text-muted">Co-provided with ${escapeHtml(pi.primary_provider)} • Your share: ${Math.round(pi.share * 100)}% (rep credit)</p>
        </div>
    `).join('');

    container.innerHTML = completedHtml + partyCompletedHtml;
}


async function respondToPartyInvite(jobId, action) {
    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}/party/respond`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action })
        });
        if (response.ok) {
            loadCompletedJobs();
        } else {
            const data = await response.json().catch(() => ({}));
            showToast(`Failed to respond: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while responding to invite', 'error');
    }
}

function fileJobDispute(jobId) {
    if (!AppState.authToken) {
        showAuth({ defaultTab: 'login' });
        return;
    }
    ensureJobActionModals();
    // Reuse reject modal chrome with dispute copy
    const title = document.getElementById('jobRejectTitle');
    const submit = document.getElementById('jobRejectSubmit');
    const reasonEl = document.getElementById('jobRejectReason');
    document.getElementById('jobRejectJobId').value = jobId;
    if (title) title.textContent = 'File dispute';
    if (submit) {
        submit.textContent = 'Submit dispute';
        submit.dataset.mode = 'dispute';
    }
    if (reasonEl) {
        reasonEl.placeholder = 'Describe the issue with this job';
        reasonEl.value = '';
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('jobRejectModal')).show();
}

async function _fileJobDisputeApi(jobId, reason) {
    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}/dispute`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ reason })
        });
        if (response.ok) {
            showToast('Dispute filed. An admin will review it.', 'success');
        } else {
            const data = await response.json().catch(() => ({}));
            showToast(`Failed to file dispute: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while filing dispute', 'error');
    }
}

async function cancelBid(bidId) {
    if (!confirm('Are you sure you want to cancel this request?')) return;
    
    try {
        const response = await fetch(`${API_URL}/cancel_bid`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ bid_id: bidId })
        });
        
        if (response.ok) {
            showToast('Request cancelled', 'success');
            AppState.outstandingBids = AppState.outstandingBids.filter(bid => bid.bid_id !== bidId);
            updateBidsDisplay();
        } else {
            const error = await response.json();
            showToast(`Failed to cancel request: ${error.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while cancelling request', 'error');
    }
}

// ---------------------------------------------------------------------------
// Service autocomplete (catalog + live market + recent)
// ---------------------------------------------------------------------------
const SERVICE_CATALOG = [
    { label: 'Lawn Mowing Bot', category: 'Outdoor', aliases: ['grass', 'yard', 'mow', 'lawn care', 'edging'], keywords: ['residential', 'acre', 'weekly'], hint: 'Residential & commercial lots', priceHint: 80, location: 'physical' },
    { label: 'Security Patrol Bot', category: 'Security', aliases: ['guard', 'night watch', 'patrol', 'security robot'], keywords: ['perimeter', 'facility'], hint: 'Site patrol & monitoring', priceHint: 200, location: 'physical' },
    { label: 'Delivery Drone', category: 'Logistics', aliases: ['drone delivery', 'package', 'last mile', 'courier'], keywords: ['radius', 'payload'], hint: 'Short-range aerial delivery', priceHint: 35, location: 'physical' },
    { label: 'Warehouse Pick and Pack', category: 'Logistics', aliases: ['fulfillment', 'pick pack', 'picking', 'packing'], keywords: ['sku', 'inventory'], hint: 'Indoor fulfillment assist', priceHint: 150, location: 'physical' },
    { label: 'Drone Photography', category: 'Media', aliases: ['aerial photo', 'survey', 'mapping', 'photogrammetry'], keywords: ['inspection', 'real estate'], hint: 'Aerial survey & imagery', priceHint: 120, location: 'physical' },
    { label: 'Industrial Inspection Bot', category: 'Inspection', aliases: ['ndt', 'facility inspection', 'pipeline', 'infrastructure'], keywords: ['thermal', 'visual'], hint: 'Infrastructure inspection', priceHint: 300, location: 'physical' },
    { label: 'Agricultural Drone', category: 'Outdoor', aliases: ['crop', 'spray', 'agri', 'field', 'farm'], keywords: ['multispectral', 'scouting'], hint: 'Crop scouting & spray support', priceHint: 250, location: 'physical' },
    { label: 'Automated Food Prep', category: 'Hospitality', aliases: ['kitchen', 'cooking', 'chef bot', 'food prep'], keywords: ['restaurant', 'meal'], hint: 'Kitchen automation assist', priceHint: 180, location: 'physical' },
    { label: 'Robotic Welding', category: 'Industrial', aliases: ['weld', 'fabrication', 'mig', 'tig'], keywords: ['shop', 'metal'], hint: 'Shop floor welding cell', priceHint: 400, location: 'physical' },
    { label: 'Geriatric Care Robot', category: 'Care', aliases: ['elder care', 'companion', 'senior', 'care robot'], keywords: ['mobility', 'check-in'], hint: 'Companion & check-in support', priceHint: 220, location: 'physical' },
    { label: 'Robotic Vacuum & Floor Clean', category: 'Facilities', aliases: ['clean', 'janitor', 'floor scrub', 'vacuum'], keywords: ['office', 'warehouse'], hint: 'Autonomous floor care', priceHint: 90, location: 'physical' },
    { label: 'Snow Plow Robot', category: 'Outdoor', aliases: ['snow removal', 'plow', 'deice', 'winter'], keywords: ['driveway', 'lot'], hint: 'Seasonal snow clearing', priceHint: 140, location: 'physical' },
    { label: 'Pool Cleaning Robot', category: 'Outdoor', aliases: ['pool', 'spa', 'water'], keywords: ['residential'], hint: 'In-pool autonomous clean', priceHint: 70, location: 'physical' },
    { label: 'Inventory Audit Robot', category: 'Logistics', aliases: ['stock count', 'cycle count', 'rfid', 'warehouse audit'], keywords: ['sku'], hint: 'Automated stock counts', priceHint: 175, location: 'physical' },
    { label: 'Window Cleaning Drone', category: 'Facilities', aliases: ['glass', 'facade', 'high rise'], keywords: ['building'], hint: 'Exterior glass assist', priceHint: 260, location: 'physical' },
    { label: 'Parking Lot Patrol', category: 'Security', aliases: ['parking', 'lot security', 'anpr', 'lpr'], keywords: ['overnight'], hint: 'Lot monitoring patrol', priceHint: 160, location: 'physical' },
    { label: 'Solar Panel Cleaning Bot', category: 'Energy', aliases: ['solar', 'pv', 'panel wash'], keywords: ['array'], hint: 'PV array cleaning', priceHint: 190, location: 'physical' },
    { label: 'Construction Site Haul Bot', category: 'Construction', aliases: ['material haul', 'jobsite', 'wheelbarrow robot'], keywords: ['debris'], hint: 'Jobsite material moves', priceHint: 210, location: 'physical' },
    { label: 'Remote Teleop Assistance', category: 'Remote', aliases: ['teleop', 'remote operator', 'remote assist'], keywords: ['supervision'], hint: 'Human-in-loop remote ops', priceHint: 95, location: 'remote' },
    { label: 'Data Labeling Robot Fleet', category: 'Remote', aliases: ['labeling', 'annotation', 'ml data', 'dataset'], keywords: ['computer vision'], hint: 'Annotation workflow support', priceHint: 60, location: 'remote' },
    { label: 'Server Room Thermal Scan', category: 'Inspection', aliases: ['datacenter', 'thermal', 'hotspot'], keywords: ['rack'], hint: 'Thermal anomaly scan', priceHint: 280, location: 'physical' },
    { label: 'Hospital Supply Runner', category: 'Care', aliases: ['med supply', 'hospital logistics', 'pharmacy run'], keywords: ['indoor'], hint: 'Indoor supply transport', priceHint: 130, location: 'physical' },
    { label: 'Event Security Presence', category: 'Security', aliases: ['venue', 'concert', 'crowd'], keywords: ['temporary'], hint: 'Temporary venue presence', priceHint: 240, location: 'physical' },
    { label: 'Tree Canopy Survey Drone', category: 'Outdoor', aliases: ['arborist', 'tree survey', 'canopy'], keywords: ['lidar'], hint: 'Canopy & hazard survey', priceHint: 170, location: 'physical' },
    { label: 'Autonomous Mowing Fleet', category: 'Outdoor', aliases: ['fleet mow', 'campus lawn', 'golf'], keywords: ['large area'], hint: 'Multi-unit large grounds', priceHint: 500, location: 'physical' }
];

const RECENT_SERVICES_KEY = 'rse_recent_services';

function getRecentServices() {
    try {
        const raw = JSON.parse(localStorage.getItem(RECENT_SERVICES_KEY) || '[]');
        return Array.isArray(raw) ? raw.filter((s) => typeof s === 'string' && s.trim()).slice(0, 8) : [];
    } catch (e) {
        return [];
    }
}

function pushRecentService(label) {
    if (!label || !String(label).trim()) return;
    const clean = String(label).trim().slice(0, 120);
    const next = [clean, ...getRecentServices().filter((s) => s.toLowerCase() !== clean.toLowerCase())].slice(0, 8);
    localStorage.setItem(RECENT_SERVICES_KEY, JSON.stringify(next));
}

function normalizeAcQuery(q) {
    return String(q || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

function scoreServiceMatch(item, query) {
    if (!query) return item._boost || 1;
    const q = normalizeAcQuery(query);
    const label = normalizeAcQuery(item.label);
    const hay = normalizeAcQuery([item.label, item.category, ...(item.aliases || []), ...(item.keywords || []), item.hint || ''].join(' '));
    if (!q) return 0;

    let score = 0;
    if (label === q) score += 100;
    else if (label.startsWith(q)) score += 70;
    else if (label.includes(q)) score += 45;

    const words = q.split(' ').filter(Boolean);
    let wordHits = 0;
    for (const w of words) {
        if (hay.includes(w)) {
            wordHits += 1;
            score += 12;
        } else {
            // light fuzzy: prefix of any token
            const tokens = hay.split(' ');
            if (tokens.some((t) => t.startsWith(w) || (w.length > 3 && t.includes(w.slice(0, -1))))) {
                wordHits += 0.5;
                score += 6;
            }
        }
    }
    if (words.length && wordHits / words.length >= 0.75) score += 15;
    if (item.source === 'live') score += 8;
    if (item.source === 'recent') score += 5;
    if (item._boost) score += item._boost;
    return score;
}

function highlightMatch(text, query) {
    const safe = escapeHtml(text);
    const q = normalizeAcQuery(query);
    if (!q || q.length < 2) return safe;
    try {
        const parts = q.split(' ').filter((w) => w.length > 1);
        let out = safe;
        for (const w of parts) {
            const re = new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
            out = out.replace(re, '<span class="ac-match">$1</span>');
        }
        return out;
    } catch (e) {
        return safe;
    }
}

let _liveMarketServices = [];
let _liveMarketFetchedAt = 0;

async function refreshLiveMarketServices() {
    if (Date.now() - _liveMarketFetchedAt < 60000 && _liveMarketServices.length) return _liveMarketServices;
    try {
        const response = await fetch(`${API_URL}/exchange_data?limit=40`);
        if (!response.ok) return _liveMarketServices;
        const data = await response.json();
        const bids = data.active_bids || [];
        const seen = new Set();
        const items = [];
        for (const bid of bids) {
            const serviceName = typeof bid.service === 'object'
                ? (bid.service.name || bid.service.description || JSON.stringify(bid.service))
                : String(bid.service || '');
            const label = serviceName.trim().slice(0, 80);
            if (label.length < 3) continue;
            const key = label.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            items.push({
                label,
                category: 'Live market',
                aliases: [],
                keywords: [],
                hint: bid.price != null ? `Open request · ${bid.currency || 'USD'} ${bid.price}` : 'Active on exchange',
                priceHint: bid.price,
                location: bid.location_type || null,
                source: 'live'
            });
            if (items.length >= 12) break;
        }
        _liveMarketServices = items;
        _liveMarketFetchedAt = Date.now();
    } catch (e) {
        /* ignore */
    }
    return _liveMarketServices;
}

function buildAutocompleteCandidates(query) {
    const q = normalizeAcQuery(query);
    const recent = getRecentServices().map((label) => ({
        label,
        category: 'Recent',
        aliases: [],
        keywords: [],
        hint: 'You used this recently',
        source: 'recent'
    }));
    const catalog = SERVICE_CATALOG.map((c) => ({ ...c, source: 'catalog' }));
    const live = _liveMarketServices.map((c) => ({ ...c, source: 'live' }));

    let pool;
    if (!q) {
        // Empty: recent → popular catalog → live
        const popular = catalog.slice(0, 8);
        pool = [...recent.slice(0, 4), ...popular, ...live.slice(0, 4)];
    } else {
        pool = [...catalog, ...live, ...recent];
    }

    const scored = pool
        .map((item) => ({ item, score: scoreServiceMatch(item, q) }))
        .filter((row) => (q ? row.score >= 12 : true))
        .sort((a, b) => b.score - a.score);

    // de-dupe by label
    const seen = new Set();
    const out = [];
    for (const row of scored) {
        const key = row.item.label.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(row.item);
        if (out.length >= 14) break;
    }
    return out;
}

function groupAcItems(items) {
    const order = ['Recent', 'Live market', 'Outdoor', 'Security', 'Logistics', 'Media', 'Inspection', 'Industrial', 'Facilities', 'Care', 'Energy', 'Construction', 'Hospitality', 'Remote'];
    const map = new Map();
    for (const item of items) {
        const cat = item.category || 'Other';
        if (!map.has(cat)) map.set(cat, []);
        map.get(cat).push(item);
    }
    const keys = [...map.keys()].sort((a, b) => {
        const ia = order.indexOf(a);
        const ib = order.indexOf(b);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    return keys.map((k) => ({ category: k, items: map.get(k) }));
}

/**
 * Attach rich autocomplete to an input/textarea + listbox element.
 */
function attachServiceAutocomplete(inputEl, listEl, opts = {}) {
    if (!inputEl || !listEl || inputEl.dataset.acBound === '1') return;
    inputEl.dataset.acBound = '1';

    let activeIndex = -1;
    let currentItems = [];
    let debounceTimer = null;

    const setExpanded = (open) => {
        inputEl.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) listEl.hidden = false;
        else listEl.hidden = true;
    };

    const close = () => {
        activeIndex = -1;
        setExpanded(false);
    };

    const applyItem = (item) => {
        if (!item) return;
        inputEl.value = item.label;
        pushRecentService(item.label);
        if (typeof opts.onSelect === 'function') opts.onSelect(item);
        close();
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        inputEl.focus();
    };

    const render = (items, query) => {
        currentItems = items;
        activeIndex = items.length ? 0 : -1;
        if (!items.length) {
            listEl.innerHTML = `<div class="service-ac-empty">No catalog matches — keep typing a free-form task description.</div>
                <div class="service-ac-footer">Tip: include location, size, and constraints (e.g. “0.5 acre”, “after 6pm”).</div>`;
            setExpanded(true);
            return;
        }
        const groups = groupAcItems(items);
        let flatIndex = 0;
        let html = '';
        for (const g of groups) {
            html += `<div class="service-ac-group">${escapeHtml(g.category)}</div>`;
            for (const item of g.items) {
                const idx = flatIndex++;
                const badge = item.source === 'live'
                    ? '<span class="ac-badge live">Live</span>'
                    : item.source === 'recent'
                        ? '<span class="ac-badge recent">Recent</span>'
                        : '';
                const price = item.priceHint != null
                    ? ` · from ~$${Number(item.priceHint).toLocaleString()}`
                    : '';
                html += `<button type="button" class="service-ac-option" role="option" id="ac-opt-${inputEl.id}-${idx}" data-ac-index="${idx}" aria-selected="${idx === activeIndex ? 'true' : 'false'}">
                    <span class="ac-label">${highlightMatch(item.label, query)}${badge}</span>
                    <span class="ac-meta">${escapeHtml(item.hint || item.category || '')}${escapeHtml(price)}</span>
                </button>`;
            }
        }
        html += `<div class="service-ac-footer">↑↓ navigate · Enter select · Esc close · free text always allowed</div>`;
        listEl.innerHTML = html;
        setExpanded(true);
        listEl.querySelectorAll('.service-ac-option').forEach((btn) => {
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const i = parseInt(btn.dataset.acIndex, 10);
                applyItem(currentItems[i]);
            });
        });
    };

    const updateActive = () => {
        listEl.querySelectorAll('.service-ac-option').forEach((btn) => {
            const i = parseInt(btn.dataset.acIndex, 10);
            btn.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
            if (i === activeIndex) {
                btn.scrollIntoView({ block: 'nearest' });
                inputEl.setAttribute('aria-activedescendant', btn.id);
            }
        });
    };

    const refresh = async () => {
        await refreshLiveMarketServices();
        const q = inputEl.value;
        render(buildAutocompleteCandidates(q), q);
    };

    inputEl.addEventListener('focus', () => {
        refreshLiveMarketServices().then(() => {
            render(buildAutocompleteCandidates(inputEl.value), inputEl.value);
        });
    });

    inputEl.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => refresh(), 80);
    });

    inputEl.addEventListener('keydown', (e) => {
        if (listEl.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
            refresh();
            e.preventDefault();
            return;
        }
        if (listEl.hidden) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!currentItems.length) return;
            activeIndex = (activeIndex + 1) % currentItems.length;
            updateActive();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (!currentItems.length) return;
            activeIndex = (activeIndex - 1 + currentItems.length) % currentItems.length;
            updateActive();
        } else if (e.key === 'Enter' && activeIndex >= 0 && currentItems[activeIndex]) {
            // Only capture Enter for selection when list open and an item active
            if (!listEl.hidden) {
                e.preventDefault();
                applyItem(currentItems[activeIndex]);
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            close();
        } else if (e.key === 'Tab') {
            close();
        }
    });

    inputEl.addEventListener('blur', () => {
        setTimeout(close, 150);
    });
}

function initServiceAutocompletes() {
    const homeInput = document.getElementById('homeBidService');
    const homeList = document.getElementById('homeServiceAcList');
    if (homeInput && homeList) {
        attachServiceAutocomplete(homeInput, homeList, {
            onSelect: (item) => {
                if (item.priceHint != null) {
                    const priceEl = document.getElementById('homeBidPrice');
                    if (priceEl && !priceEl.value) priceEl.value = item.priceHint;
                }
                if (item.location) {
                    const loc = document.getElementById('homeBidLocationType');
                    if (loc) {
                        loc.value = item.location;
                        loc.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            }
        });
    }

    const bidInput = document.getElementById('bidService');
    const bidList = document.getElementById('bidServiceAcList');
    if (bidInput && bidList) {
        attachServiceAutocomplete(bidInput, bidList, {
            onSelect: (item) => {
                if (item.priceHint != null) {
                    const priceEl = document.getElementById('bidPrice');
                    if (priceEl && !priceEl.value) priceEl.value = item.priceHint;
                }
                if (item.location) {
                    const loc = document.getElementById('bidLocationType');
                    if (loc) {
                        loc.value = item.location;
                        loc.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            }
        });
    }

    refreshLiveMarketServices();
}

function initHomeBidForm() {
    const form = document.getElementById('homeBidForm');
    if (!form || form.dataset.bound === '1') return;
    form.dataset.bound = '1';

    const loc = document.getElementById('homeBidLocationType');
    const addrField = document.getElementById('homeAddressField');
    if (loc && addrField) {
        const sync = () => {
            addrField.style.display = loc.value === 'remote' ? 'none' : 'block';
        };
        loc.addEventListener('change', sync);
        sync();
    }

    form.addEventListener('submit', handleBidSubmission);
    requestUserLocation();
}

function readBidFieldsFromForm(form) {
    if (form && form.id === 'homeBidForm') {
        return {
            service: (document.getElementById('homeBidService') || {}).value || '',
            price: parseFloat((document.getElementById('homeBidPrice') || {}).value),
            currency: (document.getElementById('homePaymentMethod') || {}).value || 'USD',
            duration: parseInt((document.getElementById('homeBidDuration') || {}).value, 10),
            durationUnit: (document.getElementById('homeBidDurationUnit') || {}).value || 'hours',
            location_type: (document.getElementById('homeBidLocationType') || {}).value || 'physical',
            address: ((document.getElementById('homeBidAddress') || {}).value || '').trim(),
            formId: 'homeBidForm'
        };
    }
    return {
        service: (document.getElementById('bidService') || {}).value || '',
        price: parseFloat((document.getElementById('bidPrice') || {}).value),
        currency: (document.getElementById('paymentMethod') || {}).value || 'USD',
        duration: parseInt((document.getElementById('bidDuration') || {}).value, 10),
        durationUnit: (document.getElementById('bidDurationUnit') || {}).value || 'hours',
        location_type: (document.getElementById('bidLocationType') || {}).value || 'physical',
        address: ((document.getElementById('bidAddress') || {}).value || '').trim(),
        formId: 'bidForm'
    };
}

function stashHomeBidDraft(fields) {
    try {
        sessionStorage.setItem('rse_bid_draft', JSON.stringify(fields));
    } catch (e) { /* ignore */ }
}

function restoreHomeBidDraft() {
    try {
        const raw = sessionStorage.getItem('rse_bid_draft');
        if (!raw) return;
        sessionStorage.removeItem('rse_bid_draft');
        const f = JSON.parse(raw);
        const set = (id, v) => {
            const el = document.getElementById(id);
            if (el && v != null && v !== '') el.value = v;
        };
        set('homeBidService', f.service);
        set('homeBidPrice', f.price);
        set('homePaymentMethod', f.currency);
        set('homeBidDuration', f.duration);
        set('homeBidDurationUnit', f.durationUnit);
        set('homeBidLocationType', f.location_type);
        set('homeBidAddress', f.address);
        const loc = document.getElementById('homeBidLocationType');
        if (loc) loc.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e) { /* ignore */ }
}

// Service Request Functions
async function handleBidSubmission(e) {
    e.preventDefault();

    const form = e.target;
    const fields = readBidFieldsFromForm(form);

    if (!fields.service || !String(fields.service).trim()) {
        showToast('Describe the service you need', 'error');
        return;
    }
    if (!(fields.price > 0)) {
        showToast('Enter a price greater than zero', 'error');
        return;
    }

    if (!AppState.authToken) {
        stashHomeBidDraft(fields);
        sessionStorage.setItem(STORAGE_KEYS.PENDING_INTENT, 'bid');
        if (fields.service) sessionStorage.setItem(STORAGE_KEYS.PENDING_SERVICE, fields.service);
        showAuth({
            intent: 'bid',
            defaultTab: 'register',
            defaultType: 'demand',
            title: 'Create an account to post this request'
        });
        return;
    }

    const durationInSeconds = fields.durationUnit === 'hours'
        ? fields.duration * 3600
        : fields.duration * 86400;

    const data = {
        service: String(fields.service).trim(),
        price: fields.price,
        currency: fields.currency,
        end_time: Math.floor(Date.now() / 1000) + durationInSeconds,
        location_type: fields.location_type
    };

    if (data.location_type !== 'remote') {
        if (fields.address) {
            data.address = fields.address;
        } else if (AppState.userLocation) {
            data.address = `${AppState.userLocation.latitude}, ${AppState.userLocation.longitude}`;
        } else {
            showToast('Please provide an address or allow location access for physical services.', 'error');
            return;
        }
    }

    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.dataset.originalText = submitBtn.textContent;
        submitBtn.textContent = 'Submitting…';
    }

    try {
        const response = await fetch(`${API_URL}/submit_bid`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AppState.authToken}`
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            const result = await response.json();
            showToast(`Request submitted (${result.bid_id})`, 'success');
            pushRecentService(data.service);

            const bidModal = document.getElementById('bidModal');
            if (bidModal && fields.formId === 'bidForm') {
                const inst = bootstrap.Modal.getInstance(bidModal);
                if (inst) inst.hide();
            }

            form.reset();
            if (fields.formId === 'homeBidForm') {
                const loc = document.getElementById('homeBidLocationType');
                if (loc) loc.dispatchEvent(new Event('change', { bubbles: true }));
            }

            if (AppState.authToken) {
                loadOutstandingBids();
                updateReturningUserHome();
            }
        } else {
            const errorData = await response.json().catch(() => ({}));
            showToast(`Failed to submit request: ${errorData.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while submitting request', 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = submitBtn.dataset.originalText || 'Submit request';
        }
    }
}

// Chat Functions
async function loadConversations() {
    const inboxContainer = document.getElementById('chatInbox');
    const loadingSpinner = document.getElementById('conversationsLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/chat/conversations`, {
            headers: {'Authorization': `Bearer ${AppState.authToken}`}
        });
        
        if (response.ok) {
            const data = await response.json();
            AppState.conversations = data.conversations || [];
            updateConversationsDisplay();
            const unread = AppState.conversations.filter((c) => c.unread).length;
            setInboxBadge(unread);
        } else if (inboxContainer) {
            inboxContainer.innerHTML = '<p class="text-danger p-3">Error loading conversations</p>';
        }
    } catch (error) {
        if (inboxContainer) {
            inboxContainer.innerHTML = '<p class="text-danger p-3">Network error</p>';
        }
    } finally {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
    }
}

function updateConversationsDisplay() {
    const container = document.getElementById('chatInbox');
    if (!container) return;
    
    if (AppState.conversations.length === 0) {
        container.innerHTML = '<p class="text-muted text-center p-3">No conversations yet</p>';
        return;
    }
    
    container.innerHTML = AppState.conversations.map((conv, index) => `
        <div class="conversation-item ${AppState.currentConversation === index ? 'active' : ''}" onclick="selectConversation(${index})">
            <div class="conversation-meta">
                <span class="conversation-user">${escapeHtml(conv.user)}</span>
                <span class="conversation-time">${formatTime(conv.timestamp * 1000)}</span>
            </div>
            <div class="conversation-preview">${escapeHtml(conv.lastMessage)}</div>
            ${conv.unread ? '<div class="badge bg-primary mt-1">New</div>' : ''}
        </div>
    `).join('');
}

function selectConversation(index) {
    AppState.currentConversation = index;
    updateConversationsDisplay();
    showConversationView(AppState.conversations[index]);
}

async function showConversationView(conversation) {
    const views = {
        conversation: document.getElementById('conversationView'),
        newForm: document.getElementById('newMessageForm'),
        placeholder: document.getElementById('chatPlaceholder'),
        userHeader: document.getElementById('currentConversationUser'),
        replyForm: document.getElementById('replyForm'),
        history: document.getElementById('messageHistory')
    };
    
    if (views.conversation) views.conversation.style.display = 'block';
    if (views.newForm) views.newForm.style.display = 'none';
    if (views.placeholder) views.placeholder.style.display = 'none';
    if (views.userHeader) views.userHeader.textContent = conversation.user;
    if (views.replyForm) views.replyForm.style.display = 'block';
    
    if (views.history) {
        views.history.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div> Loading messages...</div>';
        
        try {
            const response = await fetch(`${API_URL}/chat/messages`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${AppState.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    conversation_id: conversation.conversation_id || conversation.user 
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                const messages = data.messages || [];
                
                views.history.innerHTML = messages.map(msg => `
                    <div class="message-item ${msg.sender === AppState.currentUsername ? 'sent' : 'received'}">
                        <div class="message-sender">${escapeHtml(msg.sender)}</div>
                        <div class="message-text">${escapeHtml(msg.message)}</div>
                        <div class="message-time">${formatTime(msg.timestamp * 1000)}</div>
                    </div>
                `).join('');
                
                if (messages.length === 0) {
                    views.history.innerHTML = '<div class="text-center text-muted p-3">No messages yet</div>';
                }
            } else {
                views.history.innerHTML = '<div class="text-center text-danger p-3">Error loading messages</div>';
            }
        } catch (error) {
            views.history.innerHTML = '<div class="text-center text-danger p-3">Network error loading messages</div>';
        }
        
        views.history.scrollTop = views.history.scrollHeight;
    }
}

async function handleChatMessage(e) {
    e.preventDefault();
    
    const data = {
        recipient: document.getElementById('chatRecipient').value,
        message: document.getElementById('chatMessage').value
    };
    
    const jobId = document.getElementById('chatJobId').value.trim();
    if (jobId) {
        data.job_id = jobId;
    }
    
    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AppState.authToken}`
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            showToast('Message sent', 'success');
            document.getElementById('chatForm').reset();
            hideNewMessageForm();
            await loadConversations();
        } else {
            const error = await response.json();
            showToast(`Failed to send message: ${error.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while sending message', 'error');
    }
}

async function handleReply(e) {
    e.preventDefault();
    
    const message = document.getElementById('replyMessage').value.trim();
    if (!message || AppState.currentConversation === null) return;
    
    const conversation = AppState.conversations[AppState.currentConversation];
    
    try {
        const response = await fetch(`${API_URL}/chat/reply`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                recipient: conversation.user,
                message: message,
                conversation_id: conversation.conversation_id || conversation.user
            })
        });
        
        if (response.ok) {
            // Add message to history immediately
            const messageHistory = document.getElementById('messageHistory');
            if (messageHistory) {
                messageHistory.innerHTML += `
                    <div class="message-item sent">
                        <div class="message-sender">You</div>
                        <div class="message-text">${escapeHtml(message)}</div>
                        <div class="message-time">Just now</div>
                    </div>
                `;
                messageHistory.scrollTop = messageHistory.scrollHeight;
            }
            
            document.getElementById('replyMessage').value = '';
            
            // Update conversation preview
            conversation.lastMessage = message;
            conversation.timestamp = Math.floor(Date.now() / 1000);
            updateConversationsDisplay();
        } else {
            const error = await response.json();
            showToast(`Failed to send message: ${error.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while sending message', 'error');
    }
}

function showNewMessageForm() {
    document.getElementById('conversationView').style.display = 'none';
    document.getElementById('newMessageForm').style.display = 'block';
    document.getElementById('chatPlaceholder').style.display = 'none';
}

function hideNewMessageForm() {
    document.getElementById('newMessageForm').style.display = 'none';
    if (AppState.currentConversation !== null) {
        document.getElementById('conversationView').style.display = 'block';
    } else {
        document.getElementById('chatPlaceholder').style.display = 'block';
    }
}

// Bulletin Functions
async function loadBulletinFeed() {
    const feedContainer = document.getElementById('bulletinFeed');
    const loadingSpinner = document.getElementById('bulletinLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/bulletin/feed`, {
            headers: {'Authorization': `Bearer ${AppState.authToken}`}
        });
        
        if (response.ok) {
            const data = await response.json();
            AppState.bulletinPosts = data.posts || [];
            updateBulletinDisplay();
        } else if (feedContainer) {
            feedContainer.innerHTML = '<p class="text-danger p-3">Error loading bulletin posts</p>';
        }
    } catch (error) {
        if (feedContainer) {
            feedContainer.innerHTML = '<p class="text-danger p-3">Network error</p>';
        }
    } finally {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
    }
}

function updateBulletinDisplay() {
    const container = document.getElementById('bulletinFeed');
    if (!container) return;
    
    if (AppState.bulletinPosts.length === 0) {
        container.innerHTML = '<p class="text-muted text-center p-3">No posts yet</p>';
        return;
    }
    
    container.innerHTML = AppState.bulletinPosts.map(post => `
        <div class="bulletin-item">
            <div class="bulletin-header">
                <h6 class="bulletin-title">${escapeHtml(post.title)}</h6>
                <span class="bulletin-category">${escapeHtml(post.category)}</span>
            </div>
            <div class="bulletin-meta">By ${escapeHtml(post.author)} • ${formatTime(post.timestamp * 1000)}</div>
            <div class="bulletin-content">${escapeHtml(post.content)}</div>
        </div>
    `).join('');
}

async function handleBulletinPost(e) {
    e.preventDefault();
    
    const data = {
        title: document.getElementById('bulletinTitle').value,
        content: document.getElementById('bulletinContent').value,
        category: document.getElementById('bulletinCategory').value
    };
    
    try {
        const response = await fetch(`${API_URL}/bulletin`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AppState.authToken}`
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showToast('Posted to bulletin', 'success');
            hideNewPostForm();
            await loadBulletinFeed();
        } else {
            const error = await response.json();
            showToast(`Failed to post: ${error.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast('Network error while posting to bulletin', 'error');
    }
}

function showNewPostForm() {
    const form = document.getElementById('newPostForm');
    if (form) form.style.display = 'block';
}

function hideNewPostForm() {
    const form = document.getElementById('newPostForm');
    const inputForm = document.getElementById('bulletinForm');
    
    if (form) form.style.display = 'none';
    if (inputForm) inputForm.reset();
}

// Modal Functions
/**
 * Show auth modal with optional context.
 * @param {object|string} [opts]
 * @param {string} [opts.intent] - 'bid' | 'grab' | 'chat' etc — resumed after login
 * @param {string} [opts.defaultTab] - 'login' | 'register'
 * @param {string} [opts.defaultType] - 'demand' | 'supply'
 * @param {string} [opts.title] - modal title override
 */
function showAuth(opts = {}) {
    if (typeof opts === 'string') opts = { title: opts };
    const {
        intent = null,
        defaultTab = null,
        defaultType = null,
        title = null
    } = opts || {};

    if (intent) {
        sessionStorage.setItem(STORAGE_KEYS.PENDING_INTENT, intent);
    }

    const authError = document.getElementById('authError');
    if (authError) authError.style.display = 'none';

    const authModal = document.getElementById('authModal');
    if (!authModal) return;

    const titleEl = authModal.querySelector('.modal-title');
    if (titleEl && title) titleEl.textContent = title;

    // Prefer register when starting a first-value action
    const preferRegister = defaultTab === 'register' || (!!intent && defaultTab !== 'login');
    const loginTab = authModal.querySelector('a[href="#login"]');
    const registerTab = authModal.querySelector('a[href="#register"]');
    if (preferRegister && registerTab) {
        const tab = new bootstrap.Tab(registerTab);
        tab.show();
    } else if (defaultTab === 'login' && loginTab) {
        const tab = new bootstrap.Tab(loginTab);
        tab.show();
    }

    if (defaultType === 'demand' || defaultType === 'supply') {
        const radio = document.getElementById(defaultType === 'demand' ? 'typeDemand' : 'typeSupply');
        if (radio) radio.checked = true;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(authModal);
    modal.show();
}

function focusHomeBidForm(prefillService) {
    const homeService = document.getElementById('homeBidService');
    const panel = document.querySelector('.home-bid-panel');
    if (!homeService) return false;
    if (prefillService) homeService.value = prefillService;
    const target = panel || homeService;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => {
        homeService.focus();
        homeService.dispatchEvent(new Event('input', { bubbles: true }));
    }, 200);
    return true;
}

async function showBuyerForm(prefillService) {
    // Prefer on-page bid form when present (homepage)
    if (focusHomeBidForm(prefillService)) {
        requestUserLocation();
        return;
    }

    if (!AppState.authToken) {
        if (prefillService) {
            sessionStorage.setItem(STORAGE_KEYS.PENDING_SERVICE, prefillService);
        } else {
            sessionStorage.setItem(STORAGE_KEYS.PENDING_INTENT, 'bid');
        }
        showAuth({
            intent: 'bid',
            defaultTab: 'register',
            defaultType: 'demand',
            title: prefillService ? 'Create an account to post this request' : 'Create an account to post a request'
        });
        return;
    }

    requestUserLocation();

    const bidModal = document.getElementById('bidModal');
    if (bidModal) {
        const modal = bootstrap.Modal.getOrCreateInstance(bidModal);
        modal.show();
        loadPopularServices();
        if (prefillService) {
            const bidService = document.getElementById('bidService');
            if (bidService) bidService.value = prefillService;
        }
        return;
    }

    if (prefillService) {
        sessionStorage.setItem(STORAGE_KEYS.PENDING_SERVICE, prefillService);
    } else {
        sessionStorage.setItem(STORAGE_KEYS.PENDING_INTENT, 'bid');
    }
    if (!/index\.html(?:$|\?)/.test(location.pathname) && !location.pathname.endsWith('/')) {
        window.location.href = 'index.html?open=bid';
    }
}

async function resumePendingBuyerIntent() {
    if (!AppState.authToken) return;

    restoreHomeBidDraft();

    const pendingService = sessionStorage.getItem(STORAGE_KEYS.PENDING_SERVICE);
    const pendingIntent = sessionStorage.getItem(STORAGE_KEYS.PENDING_INTENT);
    sessionStorage.removeItem(STORAGE_KEYS.PENDING_SERVICE);
    sessionStorage.removeItem(STORAGE_KEYS.PENDING_INTENT);

    // If draft was restored and home form exists, auto-submit when complete
    const homeForm = document.getElementById('homeBidForm');
    if (homeForm && document.getElementById('homeBidService')?.value && document.getElementById('homeBidPrice')?.value) {
        focusHomeBidForm();
        // brief delay so auth UI settles
        setTimeout(() => {
            homeForm.requestSubmit();
        }, 250);
        return;
    }

    if (pendingService) {
        await showBuyerForm(pendingService);
        return;
    }
    if (pendingIntent === 'bid') {
        await showBuyerForm();
        return;
    }
    if (pendingIntent === 'grab') {
        const form = document.getElementById('grabJobForm');
        if (form) {
            form.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const ta = document.getElementById('capabilitiesText');
            if (ta) ta.focus();
        } else if (!location.pathname.includes('grab_job')) {
            window.location.href = 'grab_job.html';
        }
    }
}

async function loadPopularServices() {
    const container = document.getElementById('popularServicesContainer');
    if (!container) return;
    
    try {
        const response = await fetch(`${API_URL}/exchange_data?limit=20`);
        if (response.ok) {
            const data = await response.json();
            const bids = data.active_bids || [];
            
            // Extract unique service names from recent activity
            const serviceNames = new Set();
            for (const bid of bids) {
                const serviceName = typeof bid.service === 'object' 
                    ? (bid.service.name || JSON.stringify(bid.service))
                    : String(bid.service);
                // Take first 30 chars for display
                const shortName = serviceName.substring(0, 30);
                if (shortName.length > 2) {
                    serviceNames.add(shortName);
                }
                if (serviceNames.size >= 6) break;
            }
            
            if (serviceNames.size > 0) {
                container.innerHTML = Array.from(serviceNames).map(name => 
                    `<span class="service-tag" onclick="document.getElementById('bidService').value='${escapeHtml(name)}'">${escapeHtml(name)}</span>`
                ).join('');
            }
        }
    } catch (error) {
        console.log('Could not load popular services:', error);
    }
}

async function showChat() {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    
    const chatModal = document.getElementById('chatModal');
    if (chatModal) {
        const modal = new bootstrap.Modal(chatModal);
        modal.show();
        await loadConversations();
    }
}

async function showBulletin() {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    
    const bulletinModal = document.getElementById('bulletinModal');
    if (bulletinModal) {
        const modal = new bootstrap.Modal(bulletinModal);
        modal.show();
        await loadBulletinFeed();
    }
}

function selectService(serviceName) {
    if (focusHomeBidForm(serviceName)) return;
    showBuyerForm(serviceName);
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function contactProvider(bidId) {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    
    showChat();
    setTimeout(() => {
        showNewMessageForm();
        const jobIdField = document.getElementById('chatJobId');
        if (jobIdField) {
            jobIdField.value = bidId;
        }
    }, 300);
}

// Provider Grab Job Page Functions
function initializeGrabJobPage() {
    const elements = {
        editor: document.getElementById('capabilitiesText'),
        file: document.getElementById('capabilitiesFile'),
        saveBtn: document.getElementById('saveCapabilitiesBtn'),
        clearBtn: document.getElementById('clearCapabilitiesBtn'),
        form: document.getElementById('grabJobForm'),
        refreshBtn: document.getElementById('refreshJobsBtn')
    };

    if (!elements.editor && !elements.form) return;

    const savedProfile = localStorage.getItem(STORAGE_KEYS.PROVIDER_PROFILE);
    if (savedProfile && elements.editor && !elements.editor.value.trim()) {
        elements.editor.value = savedProfile;
        AppState.providerProfile = savedProfile;
    } else if (elements.editor) {
        AppState.providerProfile = elements.editor.value.trim();
    }

    if (elements.editor) {
        elements.editor.addEventListener('input', () => {
            AppState.providerProfile = elements.editor.value.trim();
        });
        
        elements.editor.addEventListener('blur', () => {
            const value = elements.editor.value.trim();
            if (value) {
                localStorage.setItem(STORAGE_KEYS.PROVIDER_PROFILE, value);
            }
        });
    }

    if (elements.file) {
        elements.file.addEventListener('change', handleCapabilitiesFile);
    }

    if (elements.saveBtn) {
        elements.saveBtn.addEventListener('click', (e) => {
            e.preventDefault();
            saveCapabilitiesProfile();
        });
    }

    if (elements.clearBtn) {
        elements.clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (elements.editor) elements.editor.value = '';
            AppState.providerProfile = null;
            localStorage.removeItem(STORAGE_KEYS.PROVIDER_PROFILE);
            setCapabilitiesStatus('Capabilities cleared.', false);
        });
    }

    if (elements.form) {
        elements.form.addEventListener('submit', handleGrabJobSubmission);
    }

    if (elements.refreshBtn) {
        elements.refreshBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!AppState.authToken) {
                showAuth();
                return;
            }
            await loadCompletedJobs();
        });
    }

    updateProviderDashboard();
}

function handleCapabilitiesFile(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
        const textarea = document.getElementById('capabilitiesText');
        if (!textarea) return;

        const raw = typeof reader.result === 'string' ? reader.result : '';
        let formatted = raw.trim();
        try {
            const parsed = JSON.parse(raw);
            formatted = JSON.stringify(parsed, null, 2);
        } catch (err) {
            formatted = raw.trim();
        }

        textarea.value = formatted;
        AppState.providerProfile = formatted;
        localStorage.setItem(STORAGE_KEYS.PROVIDER_PROFILE, formatted);
        setCapabilitiesStatus(`Loaded profile from ${file.name}.`, false);
    };

    reader.onerror = () => {
        setCapabilitiesStatus('Failed to read capabilities file.', true);
    };

    reader.readAsText(file);
}

function saveCapabilitiesProfile() {
    const textarea = document.getElementById('capabilitiesText');
    if (!textarea) return;

    const value = textarea.value.trim();
    if (!value) {
        localStorage.removeItem(STORAGE_KEYS.PROVIDER_PROFILE);
        AppState.providerProfile = null;
        setCapabilitiesStatus('Capabilities profile removed.', false);
        return;
    }

    localStorage.setItem(STORAGE_KEYS.PROVIDER_PROFILE, value);
    AppState.providerProfile = value;
    setCapabilitiesStatus('Capabilities profile saved locally.', false);
}

function prepareCapabilitiesPayload(raw) {
    if (!raw) return '';

    const trimmed = raw.trim();
    try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === 'string') return parsed;
        return JSON.stringify(parsed);
    } catch (err) {
        return JSON.stringify({ capabilities: trimmed });
    }
}

/** Status line under capabilities editor (or toast fallback). */
function setCapabilitiesStatus(message, isError = false) {
    let el = document.getElementById('capabilitiesStatus');
    if (!el) {
        const ta = document.getElementById('capabilitiesText');
        if (ta && ta.parentElement) {
            el = document.createElement('div');
            el.id = 'capabilitiesStatus';
            el.className = 'small-text mt-2';
            ta.parentElement.appendChild(el);
        }
    }
    if (el) {
        el.textContent = message;
        el.style.color = isError ? 'var(--danger)' : 'var(--accent)';
        return;
    }
    showToast(message, isError ? 'error' : 'info');
}

/**
 * Display grab-job result in #grabJobResult (or toast).
 * message may be plain text or HTML (when from renderGrabJobSuccess).
 */
function setGrabJobResult(message, isError = false) {
    const result = document.getElementById('grabJobResult');
    if (!result) {
        showToast(typeof message === 'string' ? message.replace(/<[^>]+>/g, ' ').trim() : String(message), isError ? 'error' : 'info');
        return;
    }

    result.style.display = 'block';
    const plain = typeof message === 'string' ? message : String(message);
    const looksHtml = /<[a-z][\s\S]*>/i.test(plain);

    if (isError) {
        result.className = 'grab-result error';
        result.innerHTML = looksHtml ? plain : `<strong>Error</strong><br>${escapeHtml(plain)}`;
    } else if (/no jobs matched|no match|no matching/i.test(plain) && !looksHtml) {
        result.className = 'grab-result info';
        result.innerHTML = `<strong>No Match</strong><br>${escapeHtml(plain)}`;
    } else if (/Matched Job|job-matched|Job Matched/i.test(plain) || looksHtml) {
        result.className = 'grab-result success';
        if (looksHtml) {
            result.innerHTML = plain;
        } else {
            result.innerHTML = `<div class="job-matched"><h4>Job Matched Successfully!</h4>${escapeHtml(plain)}</div>`;
        }
    } else {
        result.className = 'grab-result info';
        result.innerHTML = looksHtml ? plain : escapeHtml(plain);
    }
}

/** Build success HTML for a grab_job response (includes "Matched Job" marker). */
function renderGrabJobSuccess(data, capabilitiesUsed) {
    const service = typeof data.service === 'object'
        ? (data.service.name || JSON.stringify(data.service))
        : String(data.service || 'Service');
    const price = data.price != null ? data.price : '—';
    const currency = data.currency || 'USD';
    const buyer = data.buyer_username || 'buyer';
    const jobId = data.job_id || '';
    const location = data.location_type === 'remote'
        ? 'Remote'
        : (data.address || data.location_type || 'Physical');

    return `
        <div class="job-matched">
            <h4>Matched Job</h4>
            <p><strong>Service:</strong> ${escapeHtml(service)}</p>
            <p><strong>Pay:</strong> ${escapeHtml(String(currency))} ${escapeHtml(String(price))}</p>
            <p><strong>Buyer:</strong> ${escapeHtml(buyer)}</p>
            <p><strong>Location:</strong> ${escapeHtml(location)}</p>
            ${jobId ? `<p class="small-text mb-2"><strong>Job ID:</strong> ${escapeHtml(jobId)}</p>` : ''}
            <div class="d-flex gap-2 flex-wrap mt-2">
                ${jobId ? `<button type="button" class="btn btn-sm btn-primary" onclick="openJobChannel('${escapeHtml(jobId)}')">Open job chat</button>` : ''}
                <button type="button" class="btn btn-sm btn-outline-light" onclick="showChat()">Inbox</button>
            </div>
            <p class="small-text mt-2 mb-0">Coordinate with the buyer in job chat, then complete and rate when done.</p>
        </div>
    `;
}

/** Render provider active jobs into #providerActiveJobs on grab_job page. */
function updateProviderDashboard() {
    const container = document.getElementById('providerActiveJobs');
    const card = document.getElementById('activeJobsCard');
    if (!container) return;

    const providerJobs = (AppState.activeJobs || []).filter(
        (j) => j.role === 'provider' || j.provider_username === AppState.currentUsername
    );

    if (card) {
        card.style.display = AppState.authToken ? 'block' : 'none';
    }

    if (!AppState.authToken) {
        container.innerHTML = '<p class="text-muted mb-0">Log in to see active jobs</p>';
        return;
    }

    if (providerJobs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No active jobs yet — grab one above when you are ready.</p>';
        return;
    }

    container.innerHTML = providerJobs.map((job) => {
        const service = typeof job.service === 'object'
            ? escapeHtml(JSON.stringify(job.service))
            : escapeHtml(job.service);
        const accepted = job.accepted_at
            ? new Date(job.accepted_at * 1000).toLocaleDateString()
            : '';
        return `
            <div class="job-item mb-3">
                <h6>${service}</h6>
                <p class="mb-1">Pay: ${escapeHtml(job.currency || 'USD')} ${escapeHtml(String(job.price))}
                    ${accepted ? ` · Accepted ${accepted}` : ''}</p>
                <p class="text-muted small-text mb-2">Buyer: ${escapeHtml(job.counterparty || job.buyer_username || '—')}</p>
                <div class="d-flex gap-2 flex-wrap">
                    <button type="button" class="btn btn-sm btn-outline-light" onclick="openJobChannel('${job.job_id}')">Job chat</button>
                    <button type="button" class="btn btn-sm btn-primary" onclick="signJobPrompt('${job.job_id}')">Complete &amp; rate</button>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="rejectJobPrompt('${job.job_id}')">Reject</button>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Link Ethereum wallet via POST /set_wallet (profile + readiness flows).
 * @param {string} [address]
 * @param {{statusEl?: HTMLElement, inputEl?: HTMLElement}} [opts]
 */
async function linkWallet(address, opts = {}) {
    if (!AppState.authToken) {
        showAuth({ defaultTab: 'login', title: 'Log in to link wallet' });
        return null;
    }
    const raw = (address || '').trim();
    if (!raw) {
        showToast('Enter a wallet address', 'error');
        return null;
    }
    try {
        const response = await fetch(`${API_URL}/set_wallet`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ wallet_address: raw })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            showToast(data.error || 'Could not link wallet', 'error');
            if (opts.statusEl) {
                opts.statusEl.style.display = 'block';
                opts.statusEl.style.color = 'var(--danger)';
                opts.statusEl.textContent = data.error || 'Link failed';
            }
            return null;
        }
        showToast(`Wallet linked · seat: ${data.seat_status || 'checked'}`, 'success');
        if (opts.statusEl) {
            opts.statusEl.style.display = 'block';
            opts.statusEl.style.color = 'var(--accent)';
            opts.statusEl.textContent = `Linked ${data.wallet_address || raw} · seat ${data.seat_status || 'unknown'}`;
        }
        const text = document.getElementById('walletAddressText');
        if (text) text.textContent = data.wallet_address || raw;
        const seatEl = document.getElementById('seatStatusText');
        if (seatEl) seatEl.textContent = data.seat_status || 'unknown';
        if (opts.inputEl) opts.inputEl.value = data.wallet_address || raw;
        await loadAccountData();
        if (window.refreshProviderReadiness) window.refreshProviderReadiness();
        return data;
    } catch (e) {
        showToast('Network error linking wallet', 'error');
        return null;
    }
}

function linkWalletFromProfile() {
    const input = document.getElementById('walletAddressInput');
    const status = document.getElementById('walletLinkStatus');
    return linkWallet(input ? input.value : '', { inputEl: input, statusEl: status });
}

/** Mobile-friendly complete/rate and reject modals (no window.prompt). */
function ensureJobActionModals() {
    if (document.getElementById('jobRateModal')) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = `
<div class="modal fade" id="jobRateModal" tabindex="-1" aria-labelledby="jobRateTitle">
  <div class="modal-dialog modal-dialog-centered modal-fullscreen-sm-down">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="jobRateTitle">Complete &amp; rate</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="jobRateJobId">
        <p class="text-muted mb-3">Rate the other party, then mark your side complete.</p>
        <label class="form-label" for="jobRateStars">Rating</label>
        <div class="star-picker" id="jobRatePicker" role="group" aria-label="Star rating">
          <button type="button" class="star-pick" data-stars="1" aria-label="1 star">★</button>
          <button type="button" class="star-pick" data-stars="2" aria-label="2 stars">★</button>
          <button type="button" class="star-pick" data-stars="3" aria-label="3 stars">★</button>
          <button type="button" class="star-pick" data-stars="4" aria-label="4 stars">★</button>
          <button type="button" class="star-pick" data-stars="5" aria-label="5 stars">★</button>
        </div>
        <input type="hidden" id="jobRateStars" value="5">
        <p class="small-text mt-2 mb-0" id="jobRateHint">Selected: 5 stars</p>
      </div>
      <div class="modal-footer flex-column flex-sm-row gap-2">
        <button type="button" class="btn btn-secondary w-100 w-sm-auto" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-primary w-100 w-sm-auto" id="jobRateSubmit">Submit rating</button>
      </div>
    </div>
  </div>
</div>
<div class="modal fade" id="jobRejectModal" tabindex="-1" aria-labelledby="jobRejectTitle">
  <div class="modal-dialog modal-dialog-centered modal-fullscreen-sm-down">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="jobRejectTitle">Reject job</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="jobRejectJobId">
        <label class="form-label" for="jobRejectReason">Reason (optional)</label>
        <textarea class="form-control" id="jobRejectReason" rows="3" placeholder="Why are you rejecting this job?"></textarea>
      </div>
      <div class="modal-footer flex-column flex-sm-row gap-2">
        <button type="button" class="btn btn-secondary w-100 w-sm-auto" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-outline-danger w-100 w-sm-auto" id="jobRejectSubmit">Reject job</button>
      </div>
    </div>
  </div>
</div>`;
    document.body.appendChild(wrap);

    const picker = document.getElementById('jobRatePicker');
    const starsInput = document.getElementById('jobRateStars');
    const hint = document.getElementById('jobRateHint');
    const paint = (n) => {
        starsInput.value = String(n);
        hint.textContent = `Selected: ${n} star${n === 1 ? '' : 's'}`;
        picker.querySelectorAll('.star-pick').forEach((btn) => {
            const v = parseInt(btn.dataset.stars, 10);
            btn.classList.toggle('active', v <= n);
            btn.setAttribute('aria-pressed', v === n ? 'true' : 'false');
        });
    };
    paint(5);
    picker.addEventListener('click', (e) => {
        const btn = e.target.closest('.star-pick');
        if (!btn) return;
        paint(parseInt(btn.dataset.stars, 10));
    });

    document.getElementById('jobRateSubmit').addEventListener('click', async () => {
        const jobId = document.getElementById('jobRateJobId').value;
        const stars = parseInt(document.getElementById('jobRateStars').value, 10);
        const submitBtn = document.getElementById('jobRateSubmit');
        submitBtn.disabled = true;
        try {
            const response = await fetch(`${API_URL}/sign_job`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${AppState.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ job_id: jobId, star_rating: stars })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok) {
                showToast('Job completed and rated', 'success');
                bootstrap.Modal.getInstance(document.getElementById('jobRateModal'))?.hide();
                await loadCompletedJobs();
            } else {
                showToast(data.error || 'Could not complete job', 'error');
            }
        } catch (err) {
            showToast('Network error while completing job', 'error');
        } finally {
            submitBtn.disabled = false;
        }
    });

    document.getElementById('jobRejectSubmit').addEventListener('click', async () => {
        const jobId = document.getElementById('jobRejectJobId').value;
        const reason = (document.getElementById('jobRejectReason').value || '').trim();
        const submitBtn = document.getElementById('jobRejectSubmit');
        const mode = submitBtn.dataset.mode || 'reject';
        submitBtn.disabled = true;
        try {
            if (mode === 'dispute') {
                if (!reason) {
                    showToast('Please describe the issue', 'error');
                    return;
                }
                await _fileJobDisputeApi(jobId, reason);
                bootstrap.Modal.getInstance(document.getElementById('jobRejectModal'))?.hide();
                return;
            }
            const response = await fetch(`${API_URL}/reject_job`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${AppState.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ job_id: jobId, reason })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok) {
                showToast('Job rejected', 'info');
                bootstrap.Modal.getInstance(document.getElementById('jobRejectModal'))?.hide();
                await loadCompletedJobs();
            } else {
                showToast(data.error || 'Could not reject job', 'error');
            }
        } catch (err) {
            showToast('Network error while rejecting job', 'error');
        } finally {
            submitBtn.disabled = false;
        }
    });
}

function signJobPrompt(jobId) {
    if (!AppState.authToken) {
        showAuth({ defaultTab: 'login' });
        return;
    }
    ensureJobActionModals();
    document.getElementById('jobRateJobId').value = jobId;
    const picker = document.getElementById('jobRatePicker');
    if (picker) {
        picker.querySelectorAll('.star-pick').forEach((btn) => {
            const v = parseInt(btn.dataset.stars, 10);
            btn.classList.toggle('active', v <= 5);
        });
        document.getElementById('jobRateStars').value = '5';
        document.getElementById('jobRateHint').textContent = 'Selected: 5 stars';
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('jobRateModal')).show();
}

function rejectJobPrompt(jobId) {
    if (!AppState.authToken) {
        showAuth({ defaultTab: 'login' });
        return;
    }
    ensureJobActionModals();
    document.getElementById('jobRejectJobId').value = jobId;
    document.getElementById('jobRejectReason').value = '';
    const title = document.getElementById('jobRejectTitle');
    const submit = document.getElementById('jobRejectSubmit');
    const reasonEl = document.getElementById('jobRejectReason');
    if (title) title.textContent = 'Reject job';
    if (submit) {
        submit.textContent = 'Reject job';
        submit.dataset.mode = 'reject';
    }
    if (reasonEl) reasonEl.placeholder = 'Why are you rejecting this job?';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('jobRejectModal')).show();
}

async function handleGrabJobSubmission(e) {
    e.preventDefault();
    
    if (!AppState.authToken) {
        showAuth({
            intent: 'grab',
            defaultTab: 'register',
            defaultType: 'supply',
            title: 'Create a provider account to find work'
        });
        return;
    }

    const elements = {
        textarea: document.getElementById('capabilitiesText'),
        submitBtn: document.getElementById('grabJobSubmit'),
        locationType: document.getElementById('grabLocationType'),
        address: document.getElementById('grabAddress'),
        lat: document.getElementById('grabLatitude'),
        lon: document.getElementById('grabLongitude'),
        maxDistance: document.getElementById('grabDistance')
    };

    const capabilitiesText = elements.textarea ? elements.textarea.value.trim() : AppState.providerProfile;
    if (!capabilitiesText) {
        setGrabJobResult('Add your capabilities before grabbing a job.', true);
        return;
    }

    // Auto-save
    if (capabilitiesText) {
        localStorage.setItem(STORAGE_KEYS.PROVIDER_PROFILE, capabilitiesText);
        AppState.providerProfile = capabilitiesText;
    }

    const payload = {
        capabilities: prepareCapabilitiesPayload(capabilitiesText)
    };

    if (elements.locationType) payload.location_type = elements.locationType.value || 'remote';

    const address = elements.address ? elements.address.value.trim() : '';
    const lat = elements.lat ? parseFloat(elements.lat.value) : NaN;
    const lon = elements.lon ? parseFloat(elements.lon.value) : NaN;
    
    if (payload.location_type !== 'remote') {
        if (!isNaN(lat) && !isNaN(lon)) {
            payload.lat = lat;
            payload.lon = lon;
        } else if (address) {
            payload.address = address;
        } else {
            setGrabJobResult('Provide an address or coordinates for physical or hybrid jobs.', true);
            return;
        }
    } else if (address) {
        payload.address = address;
    }

    if (elements.maxDistance && elements.maxDistance.value) {
        payload.max_distance = parseFloat(elements.maxDistance.value);
    }

    if (elements.submitBtn) {
        elements.submitBtn.disabled = true;
        const btnText = document.getElementById('grabButtonText');
        if (btnText) btnText.textContent = 'Grabbing...';
        else elements.submitBtn.textContent = 'Grabbing...';
    }

    setGrabJobResult('Looking for the best job match...', false);

    try {
        const response = await fetch(`${API_URL}/grab_job`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.status === 204) {
            setGrabJobResult(
                'No jobs matched your capabilities. Try widening max distance, refining capabilities, or check back when more buyers post requests.',
                false
            );
            showNoMatchMarketHints();
            return;
        }

        const data = await response.json().catch(() => ({}));
        if (response.ok) {
            setGrabJobResult(renderGrabJobSuccess(data, payload.capabilities), false);
            await loadCompletedJobs();
            showToast('Job matched — open job chat to coordinate', 'success');
        } else {
            let errMsg = data.error || data.message || 'Unable to grab a job right now.';
            if (/wallet|seat|NFT/i.test(errMsg)) {
                errMsg += ' Link your wallet on Profile after you have a seat (email mickey@theservicesexchange.com).';
            }
            if (/supply-type|Only supply/i.test(errMsg)) {
                errMsg = 'This account is not a provider account. Register a Provide Services account or use Find Work with a supply login.';
            }
            setGrabJobResult(errMsg, true);
        }
    } catch (error) {
        setGrabJobResult('Network error while grabbing a job.', true);
    } finally {
        if (elements.submitBtn) {
            elements.submitBtn.disabled = false;
            const btnText = document.getElementById('grabButtonText');
            if (btnText) btnText.textContent = 'Grab Job';
            else elements.submitBtn.textContent = 'Grab Job';
        }
    }
}

// Copy Base URL Function
function copyBaseUrl() {
    const baseUrl = document.getElementById('baseUrl');
    const copyIcon = document.getElementById('copyIcon');
    
    if (!baseUrl) return;
    
    const url = baseUrl.textContent.trim();
    
    navigator.clipboard.writeText(url).then(() => {
        if (copyIcon) {
            copyIcon.textContent = '✓';
            setTimeout(() => {
                copyIcon.textContent = '📋';
            }, 2000);
        }
    }).catch(() => {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = url;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (copyIcon) {
            copyIcon.textContent = '✓';
            setTimeout(() => {
                copyIcon.textContent = '📋';
            }, 2000);
        }
    });
}

// API Status Check Function
async function checkApiStatus() {
    const indicator = document.getElementById('apiStatusIndicator');
    if (!indicator) return;
    
    indicator.className = 'api-status-indicator checking';
    indicator.title = 'Checking API status...';
    
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch(`${API_URL}/ping`, {
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
            indicator.className = 'api-status-indicator online';
            indicator.title = 'API is online';
        } else {
            indicator.className = 'api-status-indicator offline';
            indicator.title = `API returned status ${response.status}`;
        }
    } catch (error) {
        indicator.className = 'api-status-indicator offline';
        indicator.title = 'API is offline or unreachable';
    }
}

// Ping Server Function (for API docs)
async function pingServer() {
    const btn = document.getElementById('pingBtn');
    const spinner = document.getElementById('pingSpinner');
    const text = document.getElementById('pingText');
    const result = document.getElementById('pingResult');
    
    if (!btn || !result) return;
    
    // Reset button state
    btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (text) text.textContent = 'Pinging...';
    result.style.display = 'none';
    
    try {
        const response = await fetch(`${API_URL}/ping`);
        const data = await response.json();
        
        // Show success
        result.className = 'ping-result ping-success';
        result.innerHTML = `
            <strong>✅ Success (${response.status})</strong><br>
            Response: ${JSON.stringify(data, null, 2)}
        `;
        result.style.display = 'block';
        
    } catch (error) {
        // Show error
        result.className = 'ping-result ping-error';
        result.innerHTML = `
            <strong>❌ Error</strong><br>
            ${error.message}<br>
            <small>Note: This may be due to CORS policy or server unavailability.</small>
        `;
        result.style.display = 'block';
    }
    
    // Reset button
    btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (text) text.textContent = 'Ping Server';
}

// Make functions available globally
window.showAuth = showAuth;
window.showBuyerForm = showBuyerForm;
window.showChat = showChat;
window.showBulletin = showBulletin;
window.selectService = selectService;
window.showToast = showToast;
window.logout = logout;
window.cancelBid = cancelBid;
window.inviteToJobParty = inviteToJobParty;
window.respondToPartyInvite = respondToPartyInvite;
window.fileJobDispute = fileJobDispute;
window.openJobChannel = openJobChannel;
window.postJobChannelMessage = postJobChannelMessage;
window.setGrabJobResult = setGrabJobResult;
window.renderGrabJobSuccess = renderGrabJobSuccess;
window.updateProviderDashboard = updateProviderDashboard;
window.setCapabilitiesStatus = setCapabilitiesStatus;
window.signJobPrompt = signJobPrompt;
window.rejectJobPrompt = rejectJobPrompt;
window.updateReturningUserHome = updateReturningUserHome;
window.refreshInboxBadge = refreshInboxBadge;
window.linkWallet = linkWallet;
window.linkWalletFromProfile = linkWalletFromProfile;


AppState.jobChannel = { jobId: null, pollTimer: null, lastTs: 0, lastId: null, readOnly: false };

function ensureCoopModals() {
    if (document.getElementById('jobChannelModal')) return;
    const html = `
<div class="modal fade" id="jobChannelModal" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-scrollable modal-fullscreen-sm-down">
    <div class="modal-content job-channel-modal-content">
      <div class="modal-header">
        <div>
          <h5 class="modal-title">Job channel</h5>
          <small class="text-muted" id="jobChannelMeta"></small>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body d-flex flex-column">
        <div class="job-channel-feed flex-grow-1" id="jobChannelFeed"></div>
        <form id="jobChannelForm" class="mt-3 job-channel-composer">
          <div class="input-group job-channel-input-group">
            <input type="text" class="form-control" id="jobChannelInput" placeholder="Message the job team…" maxlength="4000" autocomplete="off" enterkeyhint="send">
            <button class="btn btn-primary" type="submit" id="jobChannelSendBtn">Send</button>
          </div>
          <small class="text-muted" id="jobChannelHint">Members only · poll every 8s</small>
        </form>
      </div>
    </div>
  </div>
</div>
<div class="modal fade" id="partyInviteModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered modal-fullscreen-sm-down">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="partyInviteTitle">Invite to job party</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="partyInviteJobId">
        <input type="hidden" id="partyInviteSide" value="supply">
        <div class="mb-3">
          <label class="form-label" for="partyInviteUsername">Username</label>
          <input class="form-control" id="partyInviteUsername" required placeholder="co-worker username" autocomplete="username">
        </div>
        <div class="mb-3">
          <label class="form-label" for="partyInviteShare">Attribution share (0–1)</label>
          <input type="number" class="form-control" id="partyInviteShare" min="0.01" max="0.95" step="0.01" value="0.4" inputmode="decimal">
          <small class="text-muted">UX hint only — demand co-buyers do not earn matching reputation</small>
        </div>
        <button class="btn btn-primary w-100" id="partyInviteSubmit">Send invite</button>
      </div>
    </div>
  </div>
</div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    document.getElementById('jobChannelForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('jobChannelInput');
        const body = (input.value || '').trim();
        if (!body || !AppState.jobChannel.jobId) return;
        const sent = await postJobChannelMessage(AppState.jobChannel.jobId, body);
        if (sent) {
            input.value = '';
            await refreshJobChannelMessages(true);
        }
    });
    document.getElementById('partyInviteSubmit').addEventListener('click', async () => {
        const jobId = document.getElementById('partyInviteJobId').value;
        const side = document.getElementById('partyInviteSide').value || 'supply';
        const memberUsername = document.getElementById('partyInviteUsername').value.trim();
        const share = parseFloat(document.getElementById('partyInviteShare').value);
        if (!memberUsername || !share || share <= 0 || share >= 1) {
            showToast('Username and share (0–1 exclusive) required', 'error');
            return;
        }
        try {
            const response = await fetch(`${API_URL}/jobs/${jobId}/party/invite`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${AppState.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ member_username: memberUsername, share, side })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok) {
                showToast(`Invited ${memberUsername}`, 'success');
                bootstrap.Modal.getInstance(document.getElementById('partyInviteModal'))?.hide();
                loadCompletedJobs();
            } else {
                showToast(data.error || 'Invite failed', 'error');
            }
        } catch (err) {
            showToast('Network error inviting party member', 'error');
        }
    });
    document.getElementById('jobChannelModal').addEventListener('hidden.bs.modal', () => {
        if (AppState.jobChannel.pollTimer) {
            clearInterval(AppState.jobChannel.pollTimer);
            AppState.jobChannel.pollTimer = null;
        }
    });
}

function renderJobChannelMessages(messages, append) {
    const feed = document.getElementById('jobChannelFeed');
    if (!feed) return;
    if (!append) feed.innerHTML = '';
    (messages || []).forEach(m => {
        const div = document.createElement('div');
        const mine = m.sender === AppState.currentUsername;
        div.className = 'job-channel-msg' + (m.message_type === 'system' ? ' system' : mine ? ' mine' : '');
        const when = m.sent_at ? new Date(m.sent_at * 1000).toLocaleString() : '';
        const who = m.sender === 'system' ? 'system' : escapeHtml(m.sender || '');
        const t = m.message_type && m.message_type !== 'user' ? ` · ${escapeHtml(m.message_type)}` : '';
        div.innerHTML = `<div class="jc-meta">${who}${t} · ${when}</div><div class="jc-body">${escapeHtml(m.body || '')}</div>`;
        feed.appendChild(div);
    });
    feed.scrollTop = feed.scrollHeight;
}

async function refreshJobChannelMessages(full) {
    const jobId = AppState.jobChannel.jobId;
    if (!jobId || !AppState.authToken) return;
    let url = `${API_URL}/jobs/${jobId}/messages?limit=50`;
    if (!full && AppState.jobChannel.lastTs) {
        url += `&since_ts=${AppState.jobChannel.lastTs}`;
        if (AppState.jobChannel.lastId) url += `&after_id=${encodeURIComponent(AppState.jobChannel.lastId)}`;
    }
    try {
        const res = await fetch(url, { headers: { 'Authorization': `Bearer ${AppState.authToken}` } });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return;
        const msgs = data.messages || [];
        if (full) renderJobChannelMessages(msgs, false);
        else if (msgs.length) renderJobChannelMessages(msgs, true);
        if (msgs.length) {
            const last = msgs[msgs.length - 1];
            AppState.jobChannel.lastTs = last.sent_at;
            AppState.jobChannel.lastId = last.message_id;
            fetch(`${API_URL}/jobs/${jobId}/messages/read`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${AppState.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ last_read_ts: last.sent_at })
            }).catch(() => {});
        }
    } catch (e) { /* poll soft-fail */ }
}

async function openJobChannel(jobId) {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    ensureCoopModals();
    AppState.jobChannel.jobId = jobId;
    AppState.jobChannel.lastTs = 0;
    AppState.jobChannel.lastId = null;
    try {
        const metaRes = await fetch(`${API_URL}/jobs/${jobId}/channel`, {
            headers: { 'Authorization': `Bearer ${AppState.authToken}` }
        });
        const meta = await metaRes.json().catch(() => ({}));
        if (!metaRes.ok) {
            showToast(meta.error || 'Cannot open job channel', 'error');
            return;
        }
        const metaEl = document.getElementById('jobChannelMeta');
        const members = (meta.members || []).join(', ');
        metaEl.textContent = `${meta.state || 'active'} · members: ${members} · ${jobId.slice(0, 8)}…`;
        AppState.jobChannel.readOnly = meta.state === 'read_only';
        const input = document.getElementById('jobChannelInput');
        const sendBtn = document.getElementById('jobChannelSendBtn');
        input.disabled = AppState.jobChannel.readOnly;
        sendBtn.disabled = AppState.jobChannel.readOnly;
        document.getElementById('jobChannelHint').textContent = AppState.jobChannel.readOnly
            ? 'Channel is read-only (job completed or rejected)'
            : 'Members only · polls every 8s';

        await refreshJobChannelMessages(true);
        const modal = new bootstrap.Modal(document.getElementById('jobChannelModal'));
        modal.show();
        if (AppState.jobChannel.pollTimer) clearInterval(AppState.jobChannel.pollTimer);
        AppState.jobChannel.pollTimer = setInterval(() => refreshJobChannelMessages(false), 8000);
    } catch (e) {
        showToast('Network error opening job channel', 'error');
    }
}

async function postJobChannelMessage(jobId, body, messageType = 'user', payload = null) {
    try {
        const res = await fetch(`${API_URL}/jobs/${jobId}/messages`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AppState.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                body,
                message_type: messageType,
                payload: payload || undefined
            })
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            return data;
        }
        showToast(data.error || 'Failed to send', 'error');
        return null;
    } catch (e) {
        showToast('Network error posting to channel', 'error');
        return null;
    }
}

async function inviteToJobParty(jobId, side) {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    ensureCoopModals();
    const partySide = (side === 'demand') ? 'demand' : 'supply';
    document.getElementById('partyInviteJobId').value = jobId;
    document.getElementById('partyInviteSide').value = partySide;
    document.getElementById('partyInviteTitle').textContent =
        partySide === 'demand' ? 'Invite co-buyer' : 'Invite co-provider';
    document.getElementById('partyInviteUsername').value = '';
    document.getElementById('partyInviteShare').value = '0.4';
    new bootstrap.Modal(document.getElementById('partyInviteModal')).show();
}


window.selectConversation = selectConversation;
window.showNewMessageForm = showNewMessageForm;
window.hideNewMessageForm = hideNewMessageForm;
window.showNewPostForm = showNewPostForm;
window.hideNewPostForm = hideNewPostForm;
window.contactProvider = contactProvider;
window.pingServer = pingServer;
window.loadPopularServices = loadPopularServices;
window.loadCompletedJobs = loadCompletedJobs;
window.updateUIForLoggedInUser = updateUIForLoggedInUser;
window.updateUIForLoggedOutUser = updateUIForLoggedOutUser;
window.copyBaseUrl = copyBaseUrl;
window.checkApiStatus = checkApiStatus;

// Check API status on page load (for API docs page)
if (document.getElementById('apiStatusIndicator')) {
    checkApiStatus();
}