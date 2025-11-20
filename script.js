/**
 * Service Exchange Frontend Script
 * -------------------------------
 * Handles all frontend interactions, API calls, and UI updates.
 */

const API_URL = 'https://rse-api.com:5003';

// Global state
window.authToken = null;
window.currentUser = null;
window.currentUsername = null;
let outstandingBids = [];
let completedJobs = [];
let activeJobs = [];
let conversations = [];
let currentConversation = null;
let bulletinPosts = [];
let userLocation = null;
let providerProfile = null;

// Initialize when DOM loads
document.addEventListener('DOMContentLoaded', function() {
    // Restore authentication state
    window.authToken = localStorage.getItem('auth_token');
    window.currentUsername = localStorage.getItem('current_username');
    
    if (window.authToken && window.currentUsername) {
        loadAccountData();
        updateUIForLoggedInUser();
    }
    
    // Set up form event listeners
    setupEventListeners();
    initializeGrabJobPage();
});

// Set up all event listeners
function setupEventListeners() {
    // Authentication forms
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const bidForm = document.getElementById('bidForm');
    const chatForm = document.getElementById('chatForm');
    const replyForm = document.getElementById('replyForm');
    const bulletinForm = document.getElementById('bulletinForm');
    const nearbyForm = document.getElementById('nearbyForm');
    const filterForm = document.getElementById('filterForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }
    
    if (registerForm) {
        registerForm.addEventListener('submit', handleRegister);
    }
    
    if (bidForm) {
        bidForm.addEventListener('submit', handleBidSubmission);
        
        // Location type handling
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
    
    if (chatForm) {
        chatForm.addEventListener('submit', handleChatMessage);
    }
    
    if (replyForm) {
        replyForm.addEventListener('submit', handleReply);
    }
    
    if (bulletinForm) {
        bulletinForm.addEventListener('submit', handleBulletinPost);
    }
    
    if (nearbyForm) {
        nearbyForm.addEventListener('submit', handleNearbySearch);
    }
    
    if (filterForm) {
        filterForm.addEventListener('submit', handleFilterApplication);
    }
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
    }
}

function setLoading(isLoading, buttonId) {
    const button = document.getElementById(buttonId);
    if (button) {
        if (isLoading) {
            button.classList.add('loading');
            button.disabled = true;
            button.textContent = 'Loading...';
        } else {
            button.classList.remove('loading');
            button.disabled = false;
            button.textContent = buttonId.includes('login') ? 'Login' : 'Register';
        }
    }
}

function updateUIForLoggedInUser() {
    const loginButton = document.getElementById('loginButton');
    const accountDropdown = document.getElementById('accountDropdown');
    const chatButton = document.getElementById('chatButton');
    const bulletinButton = document.getElementById('bulletinButton');
    
    if (loginButton) loginButton.style.display = 'none';
    if (accountDropdown) accountDropdown.style.display = 'inline-block';
    if (chatButton) chatButton.style.display = 'inline-block';
    if (bulletinButton) bulletinButton.style.display = 'inline-block';
}

function updateUIForLoggedOutUser() {
    const loginButton = document.getElementById('loginButton');
    const accountDropdown = document.getElementById('accountDropdown');
    const chatButton = document.getElementById('chatButton');
    const bulletinButton = document.getElementById('bulletinButton');
    
    if (loginButton) loginButton.style.display = 'inline-block';
    if (accountDropdown) accountDropdown.style.display = 'none';
    if (chatButton) chatButton.style.display = 'none';
    if (bulletinButton) bulletinButton.style.display = 'none';
}

function requestUserLocation() {
    return new Promise((resolve, reject) => {
        if (userLocation) {
            resolve(userLocation);
            return;
        }

        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    userLocation = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    };
                    resolve(userLocation);
                },
                (error) => {
                    console.warn('Geolocation error:', error);
                    resolve(null);
                },
                {
                    timeout: 10000,
                    enableHighAccuracy: false
                }
            );
        } else {
            resolve(null);
        }
    });
}

function formatTime(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
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
        
        setLoading(false, 'loginSubmitBtn');
        
        if (response.ok) {
            const data = await response.json();
            window.authToken = data.access_token;
            window.currentUsername = username;
            
            localStorage.setItem('auth_token', window.authToken);
            localStorage.setItem('current_username', window.currentUsername);
            
            const authModal = document.getElementById('authModal');
            if (authModal) {
                bootstrap.Modal.getInstance(authModal).hide();
            }
            
            updateUIForLoggedInUser();
            await loadAccountData();
            
            alert('Login successful!');
        } else {
            const errorData = await response.json().catch(() => ({}));
            showError(errorData.error || 'Login failed. Please check your credentials.');
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
            document.querySelector('[href="#login"]').click();
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
    window.authToken = null;
    window.currentUser = null;
    window.currentUsername = null;
    localStorage.removeItem('auth_token');
    localStorage.removeItem('current_username');
    updateUIForLoggedOutUser();
    outstandingBids = [];
    completedJobs = [];
    activeJobs = [];
    updateProviderDashboard();
    alert('Logged out successfully');
}

// Account Management Functions
async function loadAccountData() {
    if (!window.authToken || !window.currentUsername) {
        console.error('No auth token or username available');
        return;
    }
    
    try {
        const accountResponse = await fetch(`${API_URL}/account`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${window.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username: window.currentUsername })
        });
        
        if (accountResponse.ok) {
            window.currentUser = await accountResponse.json();
            updateAccountDisplay();
        } else {
            console.error('Failed to load account data:', accountResponse.status);
            if (accountResponse.status === 401) {
                logout();
                return;
            }
        }
        
        await loadOutstandingBids();
        await loadCompletedJobs();
        
    } catch (error) {
        console.error('Error loading account data:', error);
        showError('Failed to load account data. Please try refreshing the page.');
    }
}

function updateAccountDisplay() {
    if (!window.currentUser) return;
    
    const accountUsername = document.getElementById('accountUsername');
    const accountDisplayName = document.getElementById('accountDisplayName');
    const starDisplay = document.getElementById('starDisplay');
    const ratingText = document.getElementById('ratingText');
    
    if (accountUsername) accountUsername.textContent = window.currentUser.username;
    if (accountDisplayName) accountDisplayName.textContent = window.currentUser.username;
    
    if (starDisplay && ratingText) {
        const stars = Math.round(window.currentUser.stars || 0);
        const starDisplayText = '★'.repeat(Math.min(stars, 5)) + '☆'.repeat(Math.max(5 - stars, 0));
        starDisplay.textContent = starDisplayText;
        ratingText.textContent = `${window.currentUser.stars || 0} (${window.currentUser.total_ratings || 0} ratings)`;
    }
}

async function loadOutstandingBids() {
    const bidsContainer = document.getElementById('outstandingBids');
    const loadingSpinner = document.getElementById('bidsLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/my_bids`, {
            headers: {'Authorization': `Bearer ${window.authToken}`}
        });
        
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        
        if (response.ok) {
            const data = await response.json();
            outstandingBids = data.bids || [];
            updateBidsDisplay();
        } else if (bidsContainer) {
            bidsContainer.innerHTML = '<p class="text-danger">Error loading requests</p>';
        }
        
    } catch (error) {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        if (bidsContainer) {
            bidsContainer.innerHTML = '<p class="text-danger">Network error loading requests</p>';
        }
    }
}

function updateBidsDisplay() {
    const container = document.getElementById('outstandingBids');
    if (!container) return;
    
    if (outstandingBids.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No outstanding requests</p>';
        return;
    }
    
    container.innerHTML = outstandingBids.map(bid => `
        <div class="bid-item">
            <h6>${typeof bid.service === 'object' ? JSON.stringify(bid.service) : bid.service}</h6>
            <p>Price: ${bid.currency || 'USD'} ${bid.price} • Expires: ${new Date(bid.end_time * 1000).toLocaleString()}</p>
            ${bid.location_type !== 'remote' ? `<p class="text-muted">Location: ${bid.address || 'Physical service'}</p>` : '<p class="text-muted">Remote service</p>'}
            <div class="bid-actions">
                <button class="btn btn-danger btn-xs" onclick="cancelBid('${bid.bid_id}')">Cancel</button>
            </div>
        </div>
    `).join('');
}

async function loadCompletedJobs() {
    const jobsContainer = document.getElementById('completedJobs');
    const jobsLoadingSpinner = document.getElementById('jobsLoading');
    const activeJobsContainer = document.getElementById('activeJobs');
    const activeJobsLoadingSpinner = document.getElementById('activeJobsLoading');
    
    if (jobsLoadingSpinner) jobsLoadingSpinner.style.display = 'block';
    if (activeJobsLoadingSpinner) activeJobsLoadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/my_jobs`, {
            headers: {'Authorization': `Bearer ${window.authToken}`}
        });
        
        if (jobsLoadingSpinner) jobsLoadingSpinner.style.display = 'none';
        if (activeJobsLoadingSpinner) activeJobsLoadingSpinner.style.display = 'none';
        
        if (response.ok) {
            const data = await response.json();
            completedJobs = data.completed_jobs || [];
            activeJobs = data.active_jobs || [];
            updateJobsDisplay();
            updateActiveJobsDisplay();
            updateProviderDashboard();
        } else {
            if (jobsContainer) jobsContainer.innerHTML = '<p class="text-danger">Error loading services</p>';
            if (activeJobsContainer) activeJobsContainer.innerHTML = '<p class="text-danger">Error loading active services</p>';
        }
        
    } catch (error) {
        if (jobsLoadingSpinner) jobsLoadingSpinner.style.display = 'none';
        if (activeJobsLoadingSpinner) activeJobsLoadingSpinner.style.display = 'none';
        if (jobsContainer) jobsContainer.innerHTML = '<p class="text-danger">Network error loading services</p>';
        if (activeJobsContainer) activeJobsContainer.innerHTML = '<p class="text-danger">Network error loading active services</p>';
    }
}

function updateActiveJobsDisplay() {
    const container = document.getElementById('activeJobs');
    if (!container) return;
    
    if (activeJobs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No active services</p>';
        return;
    }
    
    container.innerHTML = activeJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? JSON.stringify(job.service) : job.service}</h6>
            <p>Price: ${job.currency || 'USD'} ${job.price} • Accepted: ${new Date(job.accepted_at * 1000).toLocaleDateString()} • Role: ${job.role}</p>
            <p class="text-muted">Partner: ${job.counterparty}</p>
            ${job.location_type !== 'remote' ? `<small class="text-muted">Location: ${job.address || 'Physical service'}</small>` : '<small class="text-muted">Remote service</small>'}
        </div>
    `).join('');
}

function updateJobsDisplay() {
    const container = document.getElementById('completedJobs');
    if (!container) return;
    
    if (completedJobs.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">No completed services</p>';
        return;
    }
    
    container.innerHTML = completedJobs.map(job => `
        <div class="job-item">
            <h6>${typeof job.service === 'object' ? JSON.stringify(job.service) : job.service}</h6>
            <p>Price: ${job.currency || 'USD'} ${job.price} • Completed: ${new Date(job.completed_at * 1000).toLocaleDateString()} • Role: ${job.role}</p>
            <div class="d-flex justify-content-between">
                <small>You rated: ${job.my_rating ? '★'.repeat(job.my_rating) + '☆'.repeat(5 - job.my_rating) : 'Not rated'}</small>
                <small>They rated: ${job.their_rating ? '★'.repeat(job.their_rating) + '☆'.repeat(5 - job.their_rating) : 'Not rated'}</small>
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
                'Authorization': `Bearer ${window.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ bid_id: bidId })
        });
        
        if (response.ok) {
            alert('Request cancelled successfully');
            outstandingBids = outstandingBids.filter(bid => bid.bid_id !== bidId);
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
        } else if (userLocation) {
            data.address = `${userLocation.latitude}, ${userLocation.longitude}`;
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
                'Authorization': `Bearer ${authToken}`
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
            document.getElementById('bidDuration').value = '24';
            document.getElementById('bidDurationUnit').value = 'hours';
            document.getElementById('paymentMethod').value = 'USD';
            if (window.authToken) {
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
            headers: {'Authorization': `Bearer ${window.authToken}`}
        });
        
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        
        if (response.ok) {
            const data = await response.json();
            conversations = data.conversations || [];
            updateConversationsDisplay();
        } else if (inboxContainer) {
            inboxContainer.innerHTML = '<p class="text-danger">Error loading conversations</p>';
        }
        
    } catch (error) {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        if (inboxContainer) {
            inboxContainer.innerHTML = '<p class="text-danger">Network error loading conversations</p>';
        }
    }
}

function updateConversationsDisplay() {
    const container = document.getElementById('chatInbox');
    if (!container) return;
    
    if (conversations.length === 0) {
        container.innerHTML = '<p class="text-muted text-center p-3">No conversations yet</p>';
        return;
    }
    
    container.innerHTML = conversations.map((conv, index) => `
        <div class="conversation-item ${currentConversation === index ? 'active' : ''}" onclick="selectConversation(${index})">
            <div class="conversation-meta">
                <span class="conversation-user">${conv.user}</span>
                <span class="conversation-time">${formatTime(conv.timestamp * 1000)}</span>
            </div>
            <div class="conversation-preview">${conv.lastMessage}</div>
            ${conv.unread ? '<div class="badge bg-primary">New</div>' : ''}
        </div>
    `).join('');
}

function selectConversation(index) {
    currentConversation = index;
    updateConversationsDisplay();
    showConversationView(conversations[index]);
}

async function showConversationView(conversation) {
    const conversationView = document.getElementById('conversationView');
    const newMessageForm = document.getElementById('newMessageForm');
    const chatPlaceholder = document.getElementById('chatPlaceholder');
    const currentConversationUser = document.getElementById('currentConversationUser');
    const replyForm = document.getElementById('replyForm');
    const messageHistory = document.getElementById('messageHistory');
    
    if (conversationView) conversationView.style.display = 'block';
    if (newMessageForm) newMessageForm.style.display = 'none';
    if (chatPlaceholder) chatPlaceholder.style.display = 'none';
    if (currentConversationUser) currentConversationUser.textContent = conversation.user;
    if (replyForm) replyForm.style.display = 'block';
    
    // Load message history from API
    if (messageHistory) {
        messageHistory.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div> Loading messages...</div>';
        
        try {
            const response = await fetch(`${API_URL}/chat/messages`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${window.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    conversation_id: conversation.conversation_id || conversation.user 
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                const messages = data.messages || [];
                
                messageHistory.innerHTML = messages.map(msg => `
                    <div class="message-item ${msg.sender === window.currentUsername ? 'sent' : 'received'}">
                        <div class="message-sender">${msg.sender}</div>
                        <div class="message-text">${msg.message}</div>
                        <div class="message-time">${formatTime(msg.timestamp * 1000)}</div>
                    </div>
                `).join('');
                
                if (messages.length === 0) {
                    messageHistory.innerHTML = '<div class="text-center text-muted p-3">No messages yet</div>';
                }
            } else {
                messageHistory.innerHTML = '<div class="text-center text-danger p-3">Error loading messages</div>';
            }
        } catch (error) {
            messageHistory.innerHTML = '<div class="text-center text-danger p-3">Network error loading messages</div>';
        }
        
        messageHistory.scrollTop = messageHistory.scrollHeight;
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
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`Message sent successfully! Message ID: ${result.message_id}`);
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
    if (!message || currentConversation === null) return;
    
    const conversation = conversations[currentConversation];
    
    try {
        const response = await fetch(`${API_URL}/chat/reply`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${window.authToken}`,
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
                        <div class="message-text">${message}</div>
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
    const conversationView = document.getElementById('conversationView');
    const newMessageForm = document.getElementById('newMessageForm');
    const chatPlaceholder = document.getElementById('chatPlaceholder');
    
    if (conversationView) conversationView.style.display = 'none';
    if (newMessageForm) newMessageForm.style.display = 'block';
    if (chatPlaceholder) chatPlaceholder.style.display = 'none';
}

function hideNewMessageForm() {
    const newMessageForm = document.getElementById('newMessageForm');
    const conversationView = document.getElementById('conversationView');
    const chatPlaceholder = document.getElementById('chatPlaceholder');
    
    if (newMessageForm) newMessageForm.style.display = 'none';
    if (currentConversation !== null && conversationView) {
        conversationView.style.display = 'block';
    } else if (chatPlaceholder) {
        chatPlaceholder.style.display = 'block';
    }
}

// Bulletin Functions
async function loadBulletinFeed() {
    const feedContainer = document.getElementById('bulletinFeed');
    const loadingSpinner = document.getElementById('bulletinLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/bulletin/feed`, {
            headers: {'Authorization': `Bearer ${window.authToken}`}
        });
        
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        
        if (response.ok) {
            const data = await response.json();
            bulletinPosts = data.posts || [];
            updateBulletinDisplay();
        } else if (feedContainer) {
            feedContainer.innerHTML = '<p class="text-danger">Error loading bulletin posts</p>';
        }
        
    } catch (error) {
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        if (feedContainer) {
            feedContainer.innerHTML = '<p class="text-danger">Network error loading bulletin posts</p>';
        }
    }
}

function updateBulletinDisplay() {
    const container = document.getElementById('bulletinFeed');
    if (!container) return;
    
    if (bulletinPosts.length === 0) {
        container.innerHTML = '<p class="text-muted text-center p-3">No posts yet</p>';
        return;
    }
    
    container.innerHTML = bulletinPosts.map(post => `
        <div class="bulletin-item">
            <div class="bulletin-header">
                <h6 class="bulletin-title">${post.title}</h6>
                <span class="bulletin-category">${post.category}</span>
            </div>
            <div class="bulletin-meta">By ${post.author} • ${formatTime(post.timestamp * 1000)}</div>
            <div class="bulletin-content">${post.content}</div>
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
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`Posted to bulletin successfully! Post ID: ${result.post_id}`);
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
    const newPostForm = document.getElementById('newPostForm');
    if (newPostForm) {
        newPostForm.style.display = 'block';
    }
}

function hideNewPostForm() {
    const newPostForm = document.getElementById('newPostForm');
    const bulletinForm = document.getElementById('bulletinForm');
    
    if (newPostForm) newPostForm.style.display = 'none';
    if (bulletinForm) bulletinForm.reset();
}

// Modal Functions
function showAuth() {
    const authError = document.getElementById('authError');
    if (authError) authError.style.display = 'none';
    
    const authModal = document.getElementById('authModal');
    if (authModal) {
        new bootstrap.Modal(authModal).show();
    }
}

async function showBuyerForm() {
    if (!window.authToken) {
        showAuth();
        return;
    }
    
    await requestUserLocation();
    
    const bidModal = document.getElementById('bidModal');
    if (bidModal) {
        new bootstrap.Modal(bidModal).show();
    }
}

async function showChat() {
    if (!window.authToken) {
        showAuth();
        return;
    }
    
    const chatModal = document.getElementById('chatModal');
    if (chatModal) {
        new bootstrap.Modal(chatModal).show();
        await loadConversations();
    }
}

async function showBulletin() {
    if (!window.authToken) {
        showAuth();
        return;
    }
    
    const bulletinModal = document.getElementById('bulletinModal');
    if (bulletinModal) {
        new bootstrap.Modal(bulletinModal).show();
        await loadBulletinFeed();
    }
}

function selectService(serviceName) {
    showBuyerForm();
    setTimeout(() => {
        const bidService = document.getElementById('bidService');
        if (bidService) {
            bidService.value = serviceName;
        }
    }, 100);
}

function escapeHtml(value) {
    if (value === null || value === undefined) {
        return '';
    }
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Provider Grab Job Page Functions
function initializeGrabJobPage() {
    const capabilitiesEditor = document.getElementById('capabilitiesText');
    const capabilitiesFile = document.getElementById('capabilitiesFile');
    const saveBtn = document.getElementById('saveCapabilitiesBtn');
    const clearBtn = document.getElementById('clearCapabilitiesBtn');
    const grabJobForm = document.getElementById('grabJobForm');
    const refreshBtn = document.getElementById('refreshJobsBtn');

    if (!capabilitiesEditor && !grabJobForm) {
        return;
    }

    const savedProfile = localStorage.getItem('provider_capabilities_profile');
    if (savedProfile && capabilitiesEditor && !capabilitiesEditor.value.trim()) {
        capabilitiesEditor.value = savedProfile;
        providerProfile = savedProfile;
    } else if (capabilitiesEditor) {
        providerProfile = capabilitiesEditor.value.trim();
    }

    if (capabilitiesEditor) {
        capabilitiesEditor.addEventListener('input', () => {
            providerProfile = capabilitiesEditor.value.trim();
        });
        
        capabilitiesEditor.addEventListener('blur', () => {
            const value = capabilitiesEditor.value.trim();
            if (value) {
                localStorage.setItem('provider_capabilities_profile', value);
            }
        });
    }

    if (capabilitiesFile) {
        capabilitiesFile.addEventListener('change', handleCapabilitiesFile);
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', (e) => {
            e.preventDefault();
            saveCapabilitiesProfile();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (capabilitiesEditor) {
                capabilitiesEditor.value = '';
            }
            providerProfile = null;
            localStorage.removeItem('provider_capabilities_profile');
            setCapabilitiesStatus('Capabilities cleared.', false);
        });
    }

    if (grabJobForm) {
        console.log('Grab Job form found, attaching submit handler');
        grabJobForm.addEventListener('submit', function(e) {
            console.log('Grab Job form submitted');
            handleGrabJobSubmission(e);
        });
    } else {
        console.log('Grab Job form not found on this page');
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!window.authToken) {
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
    if (!file) {
        return;
    }

    const reader = new FileReader();
    reader.onload = () => {
        const textarea = document.getElementById('capabilitiesText');
        if (!textarea) {
            return;
        }

        const raw = typeof reader.result === 'string' ? reader.result : '';
        let formatted = raw.trim();
        try {
            const parsed = JSON.parse(raw);
            formatted = JSON.stringify(parsed, null, 2);
        } catch (err) {
            formatted = raw.trim();
        }

        textarea.value = formatted;
        providerProfile = formatted;
        localStorage.setItem('provider_capabilities_profile', formatted);
        setCapabilitiesStatus(`Loaded profile from ${file.name}.`, false);
    };

    reader.onerror = () => {
        setCapabilitiesStatus('Failed to read capabilities file.', true);
    };

    reader.readAsText(file);
}

function saveCapabilitiesProfile() {
    const textarea = document.getElementById('capabilitiesText');
    if (!textarea) {
        return;
    }

    const value = textarea.value.trim();
    if (!value) {
        localStorage.removeItem('provider_capabilities_profile');
        providerProfile = null;
        setCapabilitiesStatus('Capabilities profile removed.', false);
        return;
    }

    localStorage.setItem('provider_capabilities_profile', value);
    providerProfile = value;
    setCapabilitiesStatus('Capabilities profile saved locally.', false);
}

function prepareCapabilitiesPayload(raw) {
    if (!raw) {
        return '';
    }

    const trimmed = raw.trim();
    try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === 'string') {
            return parsed;
        }
        return JSON.stringify(parsed);
    } catch (err) {
        const wrapped = { capabilities: trimmed };
        return JSON.stringify(wrapped);
    }
}

async function handleGrabJobSubmission(e) {
    console.log('handleGrabJobSubmission called', e);
    e.preventDefault();
    e.stopPropagation();

    if (!window.authToken) {
        console.log('No auth token, showing auth modal');
        showAuth();
        return;
    }

    const textarea = document.getElementById('capabilitiesText');
    const submitBtn = document.getElementById('grabJobSubmit');
    const locationTypeEl = document.getElementById('grabLocationType');
    const addressEl = document.getElementById('grabAddress');
    const latEl = document.getElementById('grabLatitude');
    const lonEl = document.getElementById('grabLongitude');
    const maxDistanceEl = document.getElementById('grabDistance');

    const capabilitiesText = textarea ? textarea.value.trim() : providerProfile;
    if (!capabilitiesText) {
        setGrabJobResult('Add your capabilities before grabbing a job.', true);
        return;
    }

    if (capabilitiesText) {
        localStorage.setItem('provider_capabilities_profile', capabilitiesText);
    }

    const payload = {
        capabilities: prepareCapabilitiesPayload(capabilitiesText)
    };

    const locationType = locationTypeEl ? locationTypeEl.value : 'remote';
    if (locationType) {
        payload.location_type = locationType;
    }

    const address = addressEl ? addressEl.value.trim() : '';
    const latValue = latEl ? latEl.value.trim() : '';
    const lonValue = lonEl ? lonEl.value.trim() : '';
    const distanceValue = maxDistanceEl ? maxDistanceEl.value.trim() : '';

    if (locationType !== 'remote') {
        if (latValue && lonValue) {
            const lat = parseFloat(latValue);
            const lon = parseFloat(lonValue);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
                setGrabJobResult('Latitude and longitude must be numeric.', true);
                return;
            }
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

    if (distanceValue) {
        const maxDistance = parseFloat(distanceValue);
        if (Number.isFinite(maxDistance) && maxDistance > 0) {
            payload.max_distance = maxDistance;
        }
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Grabbing...';
    }

    setGrabJobResult('Looking for the best job match...', false);

    try {
        const response = await fetch(`${API_URL}/grab_job`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${window.authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.status === 204) {
            setGrabJobResult('No jobs matched your capabilities. Try again soon.<br><br><strong>Submitted capabilities:</strong><br><pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 5px; overflow-x: auto;">' + escapeHtml(payload.capabilities) + '</pre>', true);
            return;
        }

        const data = await response.json().catch(() => ({}));
        if (response.ok) {
            setGrabJobResult(renderGrabJobSuccess(data, payload.capabilities), false);
            await loadCompletedJobs();
        } else {
            setGrabJobResult((data.error || 'Unable to grab a job right now.') + '<br><br><strong>Submitted capabilities:</strong><br><pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 5px; overflow-x: auto;">' + escapeHtml(payload.capabilities) + '</pre>', true);
        }
    } catch (error) {
        setGrabJobResult('Network error while grabbing a job.<br><br><strong>Submitted capabilities:</strong><br><pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 5px; overflow-x: auto;">' + escapeHtml(payload.capabilities) + '</pre>', true);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Grab Job';
        }
    }
}

function renderGrabJobSuccess(job, submittedCapabilities) {
    const price = job && job.currency ? `${escapeHtml(job.currency)} ${escapeHtml(job.price)}` : `$${escapeHtml(job.price)}`;
    const location = job && job.location_type === 'remote' ? 'Remote' : escapeHtml(job.address || 'Physical service');
    const acceptedTime = job && job.accepted_at ? new Date(job.accepted_at * 1000).toLocaleString() : 'Just now';
    const service = typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service);
    const buyer = escapeHtml(job.buyer_username || '');
    
    let capabilitiesSection = '';
    if (submittedCapabilities) {
        capabilitiesSection = `<br><br><strong>Submitted capabilities:</strong><br><pre style="background: rgba(255,255,255,0.2); padding: 10px; border-radius: 5px; margin-top: 5px; overflow-x: auto;">${escapeHtml(submittedCapabilities)}</pre>`;
    }
    
    return `
        <strong>Matched Job:</strong> ${service}<br>
        <span class="job-meta">Price: ${price}</span><br>
        <span class="job-meta">Buyer: ${buyer}</span><br>
        <span class="job-meta">Location: ${location}</span><br>
        <span class="job-meta">Accepted at: ${acceptedTime}</span>${capabilitiesSection}
    `;
}

function setGrabJobResult(message, isError = false) {
    const result = document.getElementById('grabJobResult');
    if (!result) {
        return;
    }

    result.style.display = 'block';
    result.className = isError ? 'grab-result error' : 'grab-result';
    result.innerHTML = message;
}

function setCapabilitiesStatus(message, isError = false) {
    const status = document.getElementById('capabilitiesStatus');
    if (!status) {
        return;
    }

    if (!message) {
        status.style.display = 'none';
        return;
    }

    status.style.display = 'block';
    status.className = isError ? 'grab-result error' : 'grab-result';
    status.textContent = message;
}

function updateProviderDashboard() {
    const activeContainer = document.getElementById('providerActiveJobs');
    const completedContainer = document.getElementById('providerCompletedJobs');
    const activeCount = document.getElementById('providerActiveCount');
    const completedCount = document.getElementById('providerCompletedCount');
    const reputationEl = document.getElementById('providerReputation');
    const completedTotalEl = document.getElementById('providerCompletedTotal');

    if (!activeContainer && !completedContainer && !activeCount) {
        return;
    }

    if (!window.authToken) {
        if (activeContainer) {
            activeContainer.innerHTML = '<p class="text-muted mb-0">Login to view your active jobs.</p>';
        }
        if (completedContainer) {
            completedContainer.innerHTML = '<p class="text-muted mb-0">Login to view completed jobs.</p>';
        }
        if (activeCount) activeCount.textContent = '0';
        if (completedCount) completedCount.textContent = '0';
        if (reputationEl) reputationEl.textContent = '--';
        if (completedTotalEl) completedTotalEl.textContent = '--';
        return;
    }

    if (activeContainer) {
        activeContainer.innerHTML = renderJobCards(activeJobs, 'active');
    }

    if (completedContainer) {
        completedContainer.innerHTML = renderJobCards(completedJobs, 'completed');
    }

    if (activeCount) {
        activeCount.textContent = activeJobs.length.toString();
    }

    if (completedCount) {
        completedCount.textContent = completedJobs.length.toString();
    }

    if (reputationEl) {
        reputationEl.textContent = window.currentUser && window.currentUser.reputation_score !== undefined ? window.currentUser.reputation_score.toFixed(2) : '--';
    }

    if (completedTotalEl) {
        completedTotalEl.textContent = window.currentUser && window.currentUser.completed_jobs !== undefined ? window.currentUser.completed_jobs : '--';
    }
}

function renderJobCards(jobs, type) {
    if (!jobs || jobs.length === 0) {
        return `<p class="text-muted mb-0">No ${type === 'completed' ? 'completed' : 'active'} jobs yet.</p>`;
    }

    return jobs.map(job => {
        const title = typeof job.service === 'object' ? escapeHtml(JSON.stringify(job.service)) : escapeHtml(job.service);
        const price = job.currency ? `${escapeHtml(job.currency)} ${escapeHtml(job.price)}` : `$${escapeHtml(job.price)}`;
        const accepted = job.accepted_at ? new Date(job.accepted_at * 1000).toLocaleString() : '';
        const completed = job.completed_at ? new Date(job.completed_at * 1000).toLocaleString() : '';
        const partner = job.counterparty ? `Partner: ${escapeHtml(job.counterparty)}` : '';
        const role = job.role ? escapeHtml(job.role.toUpperCase()) : '';
        const location = job.location_type === 'remote' ? 'Remote' : escapeHtml(job.address || 'Physical service');
        const status = job.status ? escapeHtml(job.status.toUpperCase()) : (type === 'completed' ? 'COMPLETED' : 'ACTIVE');

        return `
            <div class="job-card">
                <h4>${title}</h4>
                <div class="job-meta">Price: ${price}</div>
                <div class="job-meta">Role: ${role}</div>
                <div class="job-meta">${partner}</div>
                <div class="job-meta">Location: ${location}</div>
                ${accepted ? `<div class="job-meta">Accepted: ${accepted}</div>` : ''}
                ${completed ? `<div class="job-meta">Completed: ${completed}</div>` : ''}
                <div class="job-status">${status}</div>
            </div>
        `;
    }).join('');
}

// Nearby Services Functions
async function handleNearbySearch(e) {
    e.preventDefault();
    
    const address = document.getElementById('searchAddress').value;
    const radius = parseInt(document.getElementById('searchRadius').value);
    await searchNearbyByAddress(address, radius);
}

async function searchNearbyByAddress(address, radius) {
    const loading = document.getElementById('nearbyLoading');
    const results = document.getElementById('nearbyResults');
    
    if (loading) loading.style.display = 'block';
    if (results) results.innerHTML = '';
    
    try {
        const response = await fetch(`${API_URL}/nearby`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                address: address,
                radius: radius || 10
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            displayNearbyResults(data.services || []);
            
            // Center map if available
            if (typeof geocodeAndCenterMap === 'function') {
                await geocodeAndCenterMap(address);
            }
        } else if (results) {
            results.innerHTML = '<p class="text-danger">Failed to search for nearby services</p>';
        }
        
    } catch (error) {
        if (results) {
            results.innerHTML = '<p class="text-danger">Network error while searching</p>';
        }
    } finally {
        if (loading) loading.style.display = 'none';
    }
}

function displayNearbyResults(services) {
    const results = document.getElementById('nearbyResults');
    if (!results) return;
    
    if (services.length === 0) {
        results.innerHTML = '<p class="text-muted">No services found in this area.</p>';
        return;
    }
    
    results.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h5>Found ${services.length} service${services.length === 1 ? '' : 's'}</h5>
        </div>
        ${services.map(service => `
            <div class="service-card">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6>${service.service}</h6>
                        <p class="service-distance">📍 ${service.distance.toFixed(1)} miles away</p>
                        ${service.address ? `<p class="text-muted small">${service.address}</p>` : ''}
                        ${service.buyer_reputation ? `
                            <div class="reputation-stars">
                                ${'★'.repeat(Math.round(service.buyer_reputation))}${'☆'.repeat(5 - Math.round(service.buyer_reputation))}
                                <span class="text-muted ms-1">(${service.buyer_reputation.toFixed(1)})</span>
                            </div>
                        ` : ''}
                    </div>
                    <div class="text-end">
                        <div class="service-price">$${service.price}</div>
                        <button class="btn btn-sm btn-outline-primary mt-2" onclick="contactProvider('${service.bid_id}')">
                            Contact
                        </button>
                    </div>
                </div>
            </div>
        `).join('')}
    `;
}

function contactProvider(bidId) {
    alert(`Contact functionality would be implemented here for bid: ${bidId}`);
}

// Filter Functions
async function handleFilterApplication(e) {
    e.preventDefault();
    
    const category = document.getElementById('categoryFilter').value;
    const location = document.getElementById('locationFilter').value;
    const limit = parseInt(document.getElementById('limitFilter').value);
    const includeCompleted = document.getElementById('includeCompleted').checked;
    
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (location) params.append('location', location);
    if (limit) params.append('limit', limit.toString());
    if (includeCompleted) params.append('include_completed', 'true');
    
    try {
        const response = await fetch(`${API_URL}/exchange_data?${params}`);
        
        if (response.ok) {
            const data = await response.json();
            if (typeof updateExchangeStats === 'function') {
                updateExchangeStats(data);
            }
            if (typeof updateRecentActivity === 'function') {
                updateRecentActivity(data);
            }
        }
    } catch (error) {
        console.error('Error applying filters:', error);
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
window.loadCompletedJobs = loadCompletedJobs;
window.updateUIForLoggedInUser = updateUIForLoggedInUser;
window.updateUIForLoggedOutUser = updateUIForLoggedOutUser;