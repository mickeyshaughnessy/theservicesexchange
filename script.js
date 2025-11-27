/**
 * Service Exchange Frontend Script
 * -------------------------------
 * Handles all frontend interactions, API calls, and UI updates.
 */

const API_URL = 'https://rse-api.com:5003';
const STORAGE_KEYS = {
    AUTH_TOKEN: 'auth_token',
    USERNAME: 'current_username',
    PROVIDER_PROFILE: 'provider_capabilities_profile'
};

// Global state
const AppState = {
    authToken: null,
    currentUser: null,
    currentUsername: null,
    outstandingBids: [],
    completedJobs: [],
    activeJobs: [],
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
        loadAccountData();
        updateUIForLoggedInUser();
    }
    
    // Set up form event listeners
    setupEventListeners();
    initializeGrabJobPage();
});

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
}

// Utility Functions
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
        alert(message);
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
        const response = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        setLoading(false, 'loginSubmitBtn');
        
        if (response.ok) {
            AppState.authToken = data.access_token;
            AppState.currentUsername = username;
            
            // Sync global window vars for compatibility
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
            
            // Only show alert if manual login (not auto-login)
            if (e) alert('Login successful!');
        } else {
            showError(data.error || 'Login failed. Please check your credentials.');
        }
    } catch (error) {
        setLoading(false, 'loginSubmitBtn');
        showError('Network error. Please check your connection and try again.');
        console.error('Login error:', error);
    }
}

async function handleRegister(e) {
    e.preventDefault();
    
    const username = document.getElementById('regUsername').value.trim();
    const password = document.getElementById('regPassword').value;
    
    if (!username || !password) {
        showError('Please enter both username and password');
        return;
    }
    
    if (password.length < 8) {
        showError('Password must be at least 8 characters long');
        return;
    }
    
    setLoading(true, 'registerSubmitBtn');
    
    try {
        const response = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username, password })
        });
        
        setLoading(false, 'registerSubmitBtn');
        
        if (response.ok) {
            alert('Registration successful! Please login.');
            // Switch to login tab
            const loginTab = document.querySelector('a[href="#login"]');
            if (loginTab) {
                // Bootstrap 5 tab activation
                const tab = new bootstrap.Tab(loginTab);
                tab.show();
            }
            document.getElementById('loginUsername').value = username;
        } else {
            const errorData = await response.json().catch(() => ({}));
            showError(errorData.error || 'Registration failed. Please try a different username.');
        }
    } catch (error) {
        setLoading(false, 'registerSubmitBtn');
        showError('Network error. Please check your connection and try again.');
        console.error('Registration error:', error);
    }
}

function logout() {
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
    alert('Logged out successfully');
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
            logout();
            return;
        }
        
        await Promise.all([loadOutstandingBids(), loadCompletedJobs()]);
        
    } catch (error) {
        console.error('Error loading account data:', error);
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
    
    if (els.username) els.username.textContent = AppState.currentUser.username;
    if (els.displayName) els.displayName.textContent = AppState.currentUser.username;
    
    if (els.starDisplay && els.ratingText) {
        const stars = Math.round(AppState.currentUser.stars || 0);
        const starDisplayText = '★'.repeat(Math.min(stars, 5)) + '☆'.repeat(Math.max(5 - stars, 0));
        els.starDisplay.textContent = starDisplayText;
        els.ratingText.textContent = `${(AppState.currentUser.reputation_score || 0).toFixed(1)} (${AppState.currentUser.total_ratings || 0} ratings)`;
    }
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
        container.innerHTML = '<p class="text-muted mb-0">No outstanding requests</p>';
        return;
    }
    
    container.innerHTML = AppState.outstandingBids.map(bid => `
        <div class="bid-item">
            <h6>${typeof bid.service === 'object' ? escapeHtml(JSON.stringify(bid.service)) : escapeHtml(bid.service)}</h6>
            <p>Price: ${escapeHtml(bid.currency || 'USD')} ${bid.price} • Expires: ${new Date(bid.end_time * 1000).toLocaleString()}</p>
            ${bid.location_type !== 'remote' ? `<p class="text-muted">Location: ${escapeHtml(bid.address || 'Physical service')}</p>` : '<p class="text-muted">Remote service</p>'}
            <div class="bid-actions mt-2">
                <button class="btn btn-danger btn-xs" onclick="cancelBid('${bid.bid_id}')">Cancel</button>
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
            updateJobsDisplay();
            updateActiveJobsDisplay();
            updateProviderDashboard();
        }
    } catch (error) {
        console.error('Error loading jobs:', error);
    } finally {
        if (elements.jobsLoading) elements.jobsLoading.style.display = 'none';
        if (elements.activeLoading) elements.activeLoading.style.display = 'none';
    }
}

function updateActiveJobsDisplay() {
    const container = document.getElementById('activeJobs');
    if (!container) return;
    
    if (AppState.activeJobs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No active services</p>';
        return;
    }
    
    container.innerHTML = AppState.activeJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service)}</h6>
            <p>Price: ${escapeHtml(job.currency || 'USD')} ${job.price} • Accepted: ${new Date(job.accepted_at * 1000).toLocaleDateString()}</p>
            <p class="text-muted">Role: ${escapeHtml(job.role)} • Partner: ${escapeHtml(job.counterparty)}</p>
            ${job.location_type !== 'remote' ? `<small class="text-muted">Location: ${escapeHtml(job.address || 'Physical service')}</small>` : '<small class="text-muted">Remote service</small>'}
        </div>
    `).join('');
}

function updateJobsDisplay() {
    const container = document.getElementById('completedJobs');
    if (!container) return;
    
    if (AppState.completedJobs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No completed services</p>';
        return;
    }
    
    container.innerHTML = AppState.completedJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service)}</h6>
            <p>Price: ${escapeHtml(job.currency || 'USD')} ${job.price} • Completed: ${new Date(job.completed_at * 1000).toLocaleDateString()}</p>
            <div class="d-flex justify-content-between">
                <small>Role: ${escapeHtml(job.role)}</small>
                <small>Rating: ${job.their_rating ? '★'.repeat(job.their_rating) : 'Not rated'}</small>
            </div>
        </div>
    `).join('');
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
            alert('Request cancelled successfully');
            AppState.outstandingBids = AppState.outstandingBids.filter(bid => bid.bid_id !== bidId);
            updateBidsDisplay();
        } else {
            const error = await response.json();
            alert(`Failed to cancel request: ${error.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error while cancelling request');
    }
}

// Service Request Functions
async function handleBidSubmission(e) {
    e.preventDefault();
    
    const duration = parseInt(document.getElementById('bidDuration').value);
    const durationUnit = document.getElementById('bidDurationUnit').value;
    const durationInSeconds = durationUnit === 'hours' ? duration * 3600 : duration * 86400;
    
    const data = {
        service: document.getElementById('bidService').value,
        price: parseFloat(document.getElementById('bidPrice').value),
        currency: document.getElementById('paymentMethod').value,
        end_time: Math.floor(Date.now() / 1000) + durationInSeconds,
        location_type: document.getElementById('bidLocationType').value
    };
    
    // Use provided address or fallback to user location
    if (data.location_type !== 'remote') {
        const addressInput = document.getElementById('bidAddress').value.trim();
        if (addressInput) {
            data.address = addressInput;
        } else if (AppState.userLocation) {
            data.address = `${AppState.userLocation.latitude}, ${AppState.userLocation.longitude}`;
        } else {
            alert('Please provide an address or allow location access for physical services.');
            return;
        }
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
            alert(`Service request submitted! ID: ${result.bid_id}`);
            
            const bidModal = document.getElementById('bidModal');
            if (bidModal) {
                bootstrap.Modal.getInstance(bidModal).hide();
            }
            
            document.getElementById('bidForm').reset();
            
            if (AppState.authToken) {
                loadOutstandingBids();
            }
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`Failed to submit request: ${errorData.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error while submitting request');
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
            alert('Message sent successfully!');
            document.getElementById('chatForm').reset();
            hideNewMessageForm();
            await loadConversations();
        } else {
            const error = await response.json();
            alert(`Failed to send message: ${error.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error while sending message');
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
            alert(`Failed to send message: ${error.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error while sending message');
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
            alert('Posted to bulletin successfully!');
            hideNewPostForm();
            await loadBulletinFeed();
        } else {
            const error = await response.json();
            alert(`Failed to post: ${error.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error while posting to bulletin');
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
function showAuth() {
    const authError = document.getElementById('authError');
    if (authError) authError.style.display = 'none';
    
    const authModal = document.getElementById('authModal');
    if (authModal) {
        const modal = new bootstrap.Modal(authModal);
        modal.show();
    }
}

async function showBuyerForm() {
    if (!AppState.authToken) {
        showAuth();
        return;
    }
    
    await requestUserLocation();
    
    const bidModal = document.getElementById('bidModal');
    if (bidModal) {
        const modal = new bootstrap.Modal(bidModal);
        modal.show();
        loadPopularServices();
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
    showBuyerForm();
    // Small delay to ensure modal is ready and form exists
    setTimeout(() => {
        const bidService = document.getElementById('bidService');
        if (bidService) {
            bidService.value = serviceName;
        }
    }, 200);
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

async function handleGrabJobSubmission(e) {
    e.preventDefault();
    
    if (!AppState.authToken) {
        showAuth();
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
        elements.submitBtn.textContent = 'Grabbing...';
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
            setGrabJobResult('No jobs matched your capabilities. Try again soon.', true);
            return;
        }

        const data = await response.json().catch(() => ({}));
        if (response.ok) {
            setGrabJobResult(renderGrabJobSuccess(data, payload.capabilities), false);
            await loadCompletedJobs();
        } else {
            setGrabJobResult(data.error || 'Unable to grab a job right now.', true);
        }
    } catch (error) {
        setGrabJobResult('Network error while grabbing a job.', true);
    } finally {
        if (elements.submitBtn) {
            elements.submitBtn.disabled = false;
            elements.submitBtn.textContent = 'Grab Job';
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
window.logout = logout;
window.cancelBid = cancelBid;
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