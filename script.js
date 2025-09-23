// The Services Exchange - Unified JavaScript
const API_URL = 'https://rse-api.com:5003';

// Global state
let authToken = null;
let currentUser = null;
let currentUsername = null;
let outstandingBids = [];
let completedJobs = [];
let activeJobs = [];
let conversations = [];
let currentConversation = null;
let bulletinPosts = [];
let userLocation = null;

// Initialize when DOM loads
document.addEventListener('DOMContentLoaded', function() {
    // Restore authentication state
    authToken = localStorage.getItem('auth_token');
    currentUsername = localStorage.getItem('current_username');
    
    if (authToken && currentUsername) {
        loadAccountData();
        updateUIForLoggedInUser();
    }
    
    // Set up form event listeners
    setupEventListeners();
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
            authToken = data.access_token;
            currentUsername = username;
            
            localStorage.setItem('auth_token', authToken);
            localStorage.setItem('current_username', currentUsername);
            
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
    authToken = null;
    currentUser = null;
    currentUsername = null;
    localStorage.removeItem('auth_token');
    localStorage.removeItem('current_username');
    updateUIForLoggedOutUser();
    alert('Logged out successfully');
}

// Account Management Functions
async function loadAccountData() {
    if (!authToken || !currentUsername) {
        console.error('No auth token or username available');
        return;
    }
    
    try {
        const accountResponse = await fetch(`${API_URL}/account`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username: currentUsername })
        });
        
        if (accountResponse.ok) {
            currentUser = await accountResponse.json();
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
    if (!currentUser) return;
    
    const accountUsername = document.getElementById('accountUsername');
    const accountDisplayName = document.getElementById('accountDisplayName');
    const starDisplay = document.getElementById('starDisplay');
    const ratingText = document.getElementById('ratingText');
    
    if (accountUsername) accountUsername.textContent = currentUser.username;
    if (accountDisplayName) accountDisplayName.textContent = currentUser.username;
    
    if (starDisplay && ratingText) {
        const stars = Math.round(currentUser.stars || 0);
        const starDisplayText = '★'.repeat(Math.min(stars, 5)) + '☆'.repeat(Math.max(5 - stars, 0));
        starDisplay.textContent = starDisplayText;
        ratingText.textContent = `${currentUser.stars || 0} (${currentUser.total_ratings || 0} ratings)`;
    }
}

async function loadOutstandingBids() {
    const bidsContainer = document.getElementById('outstandingBids');
    const loadingSpinner = document.getElementById('bidsLoading');
    
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/my_bids`, {
            headers: {'Authorization': `Bearer ${authToken}`}
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
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        if (jobsLoadingSpinner) jobsLoadingSpinner.style.display = 'none';
        if (activeJobsLoadingSpinner) activeJobsLoadingSpinner.style.display = 'none';
        
        if (response.ok) {
            const data = await response.json();
            completedJobs = data.completed_jobs || [];
            activeJobs = data.active_jobs || [];
            updateJobsDisplay();
            updateActiveJobsDisplay();
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
                'Authorization': `Bearer ${authToken}`,
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
            if (authToken) {
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
            headers: {'Authorization': `Bearer ${authToken}`}
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
                    'Authorization': `Bearer ${authToken}`,
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
                    <div class="message-item ${msg.sender === currentUsername ? 'sent' : 'received'}">
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
                'Authorization': `Bearer ${authToken}`,
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
            headers: {'Authorization': `Bearer ${authToken}`}
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
    if (!authToken) {
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
    if (!authToken) {
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
    if (!authToken) {
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