// Nearby Services - Map and Exchange Data functionality
let map = null;
let markers = [];

// Mapbox access token - You'll need to replace this with your actual token
mapboxgl.accessToken = 'pk.eyJ1IjoibWlja2V5c2hhdWdobmVzc3kiLCJhIjoiY2x6NGxyNG93MnptaDJxb2dhOGloenZqeiJ9.ANY7UIu7VTPFwqTD8cEAKQ';

// Initialize the page - wait for mapbox to be loaded
function initializePage() {
    if (typeof mapboxgl === 'undefined') {
        // If mapboxgl isn't loaded yet, try again in 100ms
        setTimeout(initializePage, 100);
        return;
    }
    initializeMap();
    loadExchangeData();
}

// Initialize when DOM and scripts are ready
window.addEventListener('load', initializePage);

function initializeMap() {
    // Initialize map centered on Denver, CO
    map = new mapboxgl.Map({
        container: 'map',
        style: 'mapbox://styles/mapbox/streets-v11',
        center: [-104.9903, 39.7392], // Denver coordinates
        zoom: 10
    });
    
    map.addControl(new mapboxgl.NavigationControl());
    
    // Add click handler for getting coordinates
    map.on('click', (e) => {
        const { lng, lat } = e.lngLat;
        searchNearbyByCoordinates(lat, lng);
    });
}

async function loadExchangeData() {
    const statsLoading = document.getElementById('statsLoading');
    const activityLoading = document.getElementById('activityLoading');
    
    if (statsLoading) statsLoading.style.display = 'block';
    if (activityLoading) activityLoading.style.display = 'block';
    
    try {
        const response = await fetch(`${API_URL}/exchange_data?limit=50&include_completed=true`);
        
        if (response.ok) {
            const data = await response.json();
            updateExchangeStats(data);
            updateRecentActivity(data);
        } else {
            console.error('Failed to load exchange data');
        }
        
    } catch (error) {
        console.error('Error loading exchange data:', error);
    } finally {
        if (statsLoading) {
            statsLoading.style.display = 'none';
            const exchangeStats = document.getElementById('exchangeStats');
            if (exchangeStats) exchangeStats.style.display = 'block';
        }
        if (activityLoading) {
            activityLoading.style.display = 'none';
            const recentActivity = document.getElementById('recentActivity');
            if (recentActivity) recentActivity.style.display = 'block';
        }
    }
}

function updateExchangeStats(data) {
    const stats = data.market_stats || {};
    
    const activeBidsCount = document.getElementById('activeBidsCount');
    const completedTodayCount = document.getElementById('completedTodayCount');
    const avgPrice = document.getElementById('avgPrice');
    
    if (activeBidsCount) activeBidsCount.textContent = stats.total_active_bids || 0;
    if (completedTodayCount) completedTodayCount.textContent = stats.total_completed_today || 0;
    if (avgPrice) avgPrice.textContent = stats.avg_price_cleaning ? `$${stats.avg_price_cleaning.toFixed(0)}` : 'N/A';
}

function updateRecentActivity(data) {
    const container = document.getElementById('recentActivity');
    if (!container) return;
    
    const activeBids = data.active_bids || [];
    const completedJobs = data.completed_jobs || [];
    
    // Combine and sort by date
    const allActivity = [
        ...activeBids.map(bid => ({...bid, type: 'bid', date: bid.posted_at})),
        ...completedJobs.map(job => ({...job, type: 'completed', date: job.completed_at}))
    ].sort((a, b) => b.date - a.date).slice(0, 10);
    
    if (allActivity.length === 0) {
        container.innerHTML = '<p class="text-muted">No recent activity</p>';
        return;
    }
    
    container.innerHTML = allActivity.map(item => {
        const isCompleted = item.type === 'completed';
        const service = typeof item.service === 'string' ? item.service : 
                      (item.service?.type || 'Service');
        
        return `
            <div class="job-item ${isCompleted ? 'job-completed' : ''}">
                <div class="job-title">${service}</div>
                <div class="job-meta">
                    $${item.price} • ${isCompleted ? 'Completed' : 'Active Bid'} • 
                    ${new Date(item.date * 1000).toLocaleDateString()}
                </div>
                ${item.location ? `<div class="job-meta">${item.location}</div>` : ''}
                ${isCompleted && item.avg_rating ? `<div class="reputation-stars">${'★'.repeat(Math.round(item.avg_rating))}</div>` : ''}
            </div>
        `;
    }).join('');
}

function clearMapMarkers() {
    markers.forEach(marker => marker.remove());
    markers = [];
}

function addServiceMarker(service, lat, lng) {
    const popup = new mapboxgl.Popup({ offset: 25 }).setHTML(`
        <div style="padding: 10px;">
            <h6>${service.service}</h6>
            <p><strong>$${service.price}</strong> • ${service.distance.toFixed(1)} miles</p>
            ${service.buyer_reputation ? `<div class="reputation-stars">${'★'.repeat(Math.round(service.buyer_reputation))}</div>` : ''}
        </div>
    `);
    
    const marker = new mapboxgl.Marker({color: '#6366f1'})
        .setLngLat([lng, lat])
        .setPopup(popup)
        .addTo(map);
    
    markers.push(marker);
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
            
            // Geocode address to center map
            await geocodeAndCenterMap(address);
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

async function searchNearbyByCoordinates(lat, lng) {
    const loading = document.getElementById('nearbyLoading');
    const results = document.getElementById('nearbyResults');
    
    if (loading) loading.style.display = 'block';
    if (results) results.innerHTML = '';
    
    try {
        const radiusInput = document.getElementById('searchRadius');
        const radius = radiusInput ? parseInt(radiusInput.value) || 10 : 10;
        
        const response = await fetch(`${API_URL}/nearby`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                lat: lat,
                lon: lng,
                radius: radius
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            displayNearbyResults(data.services || []);
            map.flyTo({center: [lng, lat], zoom: 12});
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
    
    clearMapMarkers();
    
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
    
    // Add markers to map (if we had coordinates)
    // For now, we'll just center on the search location
}

async function geocodeAndCenterMap(address) {
    // In a real implementation, you'd use Mapbox Geocoding API
    // For demo purposes, we'll center on Denver
    map.flyTo({center: [-104.9903, 39.7392], zoom: 12});
}

// Make functions available globally for nearby page
window.updateExchangeStats = updateExchangeStats;
window.updateRecentActivity = updateRecentActivity;
window.geocodeAndCenterMap = geocodeAndCenterMap;