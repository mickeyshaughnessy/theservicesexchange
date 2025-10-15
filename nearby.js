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
    try {
        // Initialize map centered on Denver, CO
        map = new mapboxgl.Map({
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v11',
            center: [-104.9903, 39.7392], // Denver coordinates
            zoom: 10
        });
        
        map.addControl(new mapboxgl.NavigationControl());
        
        // Load markers after map is loaded
        map.on('load', () => {
            loadExchangeDataOnMap();
        });
        
        console.log('Map initialized successfully');
    } catch (error) {
        console.error('Error initializing map:', error);
    }
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

async function loadExchangeDataOnMap() {
    try {
        // Get filter values
        const categoryFilter = document.getElementById('categoryFilter');
        const locationFilter = document.getElementById('locationFilter');
        const limitFilter = document.getElementById('limitFilter');
        const includeCompleted = document.getElementById('includeCompleted');
        
        const params = new URLSearchParams();
        if (categoryFilter && categoryFilter.value) params.append('category', categoryFilter.value);
        if (locationFilter && locationFilter.value) params.append('location', locationFilter.value);
        if (limitFilter && limitFilter.value) params.append('limit', limitFilter.value);
        if (includeCompleted) params.append('include_completed', includeCompleted.checked);
        
        const response = await fetch(`${API_URL}/exchange_data?${params.toString()}`);
        
        if (response.ok) {
            const data = await response.json();
            displayServicesOnMap(data);
        } else {
            console.error('Failed to load exchange data for map');
        }
        
    } catch (error) {
        console.error('Error loading exchange data for map:', error);
    }
}

async function displayServicesOnMap(data) {
    clearMapMarkers();
    
    const activeBids = data.active_bids || [];
    const completedJobs = data.completed_jobs || [];
    
    // Combine all jobs with location data
    const allJobs = [...activeBids, ...completedJobs];
    
    for (const job of allJobs) {
        let lat = job.lat;
        let lon = job.lon;
        
        // If no coordinates but we have an address, try to geocode
        if ((!lat || !lon) && job.address) {
            try {
                const coords = await geocodeAddress(job.address);
                if (coords) {
                    lat = coords.lat;
                    lon = coords.lon;
                }
            } catch (error) {
                console.warn(`Failed to geocode address: ${job.address}`, error);
            }
        }
        
        // If we have coordinates (original or geocoded), add marker
        if (lat && lon) {
            const service = typeof job.service === 'string' ? job.service : 
                          (job.service?.type || 'Service');
            const isCompleted = job.completed_at !== undefined;
            
            const popup = new mapboxgl.Popup({ offset: 25 }).setHTML(`
                <div style="padding: 10px;">
                    <h6>${service}</h6>
                    <p><strong>$${job.price}</strong> ${isCompleted ? '• Completed' : '• Active'}</p>
                    ${job.address || job.location ? `<p class="text-muted small">${job.address || job.location}</p>` : ''}
                    ${job.buyer_reputation ? `<div style="color: gold;">${'★'.repeat(Math.round(job.buyer_reputation))}</div>` : ''}
                </div>
            `);
            
            const markerColor = isCompleted ? '#10b981' : '#6366f1';
            
            const marker = new mapboxgl.Marker({color: markerColor})
                .setLngLat([lon, lat])
                .setPopup(popup)
                .addTo(map);
            
            markers.push(marker);
        }
    }
    
    console.log(`Displayed ${markers.length} services on map`);
}

function updateExchangeStats(data) {
    const stats = data.market_stats || {};
    
    const activeBidsCount = document.getElementById('activeBidsCount');
    const completedTodayCount = document.getElementById('completedTodayCount');
    const activeBidsDetails = document.getElementById('activeBidsDetails');
    
    if (activeBidsCount) activeBidsCount.textContent = stats.total_active_bids || 0;
    if (completedTodayCount) completedTodayCount.textContent = stats.total_completed_today || 0;
    
    // Populate active bids details text box
    if (activeBidsDetails) {
        const activeBids = data.active_bids || [];
        if (activeBids.length === 0) {
            activeBidsDetails.value = 'No active bids available.';
        } else {
            const bidDetails = activeBids.map((bid, index) => {
                const service = typeof bid.service === 'string' ? bid.service : 
                              (bid.service?.type || 'Service');
                const location = bid.address || bid.location || 'No address specified';
                const postedDate = bid.posted_at ? new Date(bid.posted_at * 1000).toLocaleString() : 'N/A';
                
                return `Bid #${index + 1}:\nService: ${service}\nPrice: $${bid.price}\nLocation: ${location}\nPosted: ${postedDate}\n${bid.buyer_reputation ? `Rating: ${bid.buyer_reputation.toFixed(1)} stars` : 'No rating'}\n`;
            }).join('\n---\n\n');
            
            activeBidsDetails.value = bidDetails;
        }
    }
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

async function geocodeAddress(address) {
    try {
        const response = await fetch(
            `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(address)}.json?access_token=${mapboxgl.accessToken}&limit=1`
        );
        
        if (response.ok) {
            const data = await response.json();
            if (data.features && data.features.length > 0) {
                const [lon, lat] = data.features[0].center;
                return { lat, lon };
            }
        }
        return null;
    } catch (error) {
        console.error('Geocoding error:', error);
        return null;
    }
}

async function geocodeAndCenterMap(address) {
    const coords = await geocodeAddress(address);
    if (coords) {
        map.flyTo({center: [coords.lon, coords.lat], zoom: 12});
    } else {
        // Fallback to Denver if geocoding fails
        map.flyTo({center: [-104.9903, 39.7392], zoom: 12});
    }
}

// Set up filter form event handler
document.addEventListener('DOMContentLoaded', () => {
    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        filterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (map) {
                loadExchangeDataOnMap();
            }
        });
    }
    
    // Also trigger filter when checkbox changes
    const includeCompleted = document.getElementById('includeCompleted');
    if (includeCompleted) {
        includeCompleted.addEventListener('change', () => {
            if (map) {
                loadExchangeDataOnMap();
            }
        });
    }
});

// Make functions available globally for nearby page
window.updateExchangeStats = updateExchangeStats;
window.updateRecentActivity = updateRecentActivity;
window.geocodeAndCenterMap = geocodeAndCenterMap;