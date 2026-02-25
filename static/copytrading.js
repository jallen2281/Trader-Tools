/**
 * Copy Trading Research - JavaScript functionality
 */

let allTraders = [];
let followedTraders = new Set();
let politicianTrades = [];
let activeTab = 'traders'; // 'traders' or 'politicians'

// Sample trader data - In production, this would come from an API
const sampleTraders = [
    {
        id: 1,
        name: "Sarah Chen",
        badge: "pro",
        performance: 127.5,
        winRate: 68,
        followers: 2847,
        riskLevel: "medium",
        riskScore: 55,
        avgReturn: 3.2,
        maxDrawdown: -12.4,
        sharpeRatio: 1.8,
        totalTrades: 342,
        strategies: ["Growth", "Momentum"],
        description: "Focus on tech growth stocks with strong fundamentals",
        yearlyReturns: [45, 52, 30.5]
    },
    {
        id: 2,
        name: "Michael Rodriguez",
        badge: "verified",
        performance: 89.3,
        winRate: 72,
        followers: 5123,
        riskLevel: "low",
        riskScore: 28,
        avgReturn: 2.1,
        maxDrawdown: -8.2,
        sharpeRatio: 2.3,
        totalTrades: 156,
        strategies: ["Dividend", "Value"],
        description: "Conservative dividend growth strategy",
        yearlyReturns: [28, 31, 30.3]
    },
    {
        id: 3,
        name: "Alexandra Kim",
        badge: "rising",
        performance: 215.8,
        winRate: 64,
        followers: 1456,
        riskLevel: "high",
        riskScore: 78,
        avgReturn: 5.8,
        maxDrawdown: -22.1,
        sharpeRatio: 1.4,
        totalTrades: 589,
        strategies: ["Options", "Swing"],
        description: "Aggressive options strategies with technical analysis",
        yearlyReturns: [85, 72.5, 58.3]
    },
    {
        id: 4,
        name: "David Thompson",
        badge: "verified",
        performance: 156.2,
        winRate: 70,
        followers: 3892,
        riskLevel: "medium",
        riskScore: 48,
        avgReturn: 4.1,
        maxDrawdown: -15.3,
        sharpeRatio: 1.9,
        totalTrades: 428,
        strategies: ["Momentum", "Growth"],
        description: "Momentum-based trading with trend following",
        yearlyReturns: [52, 56, 48.2]
    },
    {
        id: 5,
        name: "Emily Foster",
        badge: "pro",
        performance: 98.7,
        winRate: 75,
        followers: 4521,
        riskLevel: "low",
        riskScore: 32,
        avgReturn: 2.8,
        maxDrawdown: -9.5,
        sharpeRatio: 2.1,
        totalTrades: 267,
        strategies: ["Value", "Dividend"],
        description: "Deep value investing with margin of safety",
        yearlyReturns: [32, 35, 31.7]
    },
    {
        id: 6,
        name: "James Lee",
        badge: "rising",
        performance: 187.3,
        winRate: 66,
        followers: 987,
        riskLevel: "high",
        riskScore: 72,
        avgReturn: 5.2,
        maxDrawdown: -19.8,
        sharpeRatio: 1.5,
        totalTrades: 512,
        strategies: ["Swing", "Momentum"],
        description: "Short-term swing trades on high-volume stocks",
        yearlyReturns: [62, 67, 58.3]
    }
];

/**
 * Initialize the page
 */
function init() {
    loadFollowedTraders();
    allTraders = [...sampleTraders];
    renderTraders(allTraders);
    loadPoliticianTrades();
    
    // Set up tab switching
    setupTabSwitching();
}

/**
 * Set up tab switching between traders and politicians
 */
function setupTabSwitching() {
    const tradersTab = document.getElementById('tradersTab');
    const politiciansTab = document.getElementById('politiciansTab');
    
    if (tradersTab && politiciansTab) {
        tradersTab.addEventListener('click', () => switchTab('traders'));
        politiciansTab.addEventListener('click', () => switchTab('politicians'));
    }
}

/**
 * Switch between traders and politicians view
 */
function switchTab(tab) {
    activeTab = tab;
    
    // Update tab buttons
    const tradersTab = document.getElementById('tradersTab');
    const politiciansTab = document.getElementById('politiciansTab');
    
    if (tab === 'traders') {
        tradersTab.classList.add('active');
        politiciansTab.classList.remove('active');
        document.getElementById('traderGrid').style.display = 'grid';
        document.getElementById('politicianGrid').style.display = 'none';
        document.getElementById('filtersBar').style.display = 'flex';
        document.getElementById('politicianFilters').style.display = 'none';
    } else {
        tradersTab.classList.remove('active');
        politiciansTab.classList.add('active');
        document.getElementById('traderGrid').style.display = 'none';
        document.getElementById('politicianGrid').style.display = 'grid';
        document.getElementById('filtersBar').style.display = 'none';
        document.getElementById('politicianFilters').style.display = 'flex';
    }
}

/**
 * Load politician trades from API
 */
async function loadPoliticianTrades() {
    try {
        const response = await fetch('/api/politician-trades?days=30');
        if (response.ok) {
            const data = await response.json();
            politicianTrades = data.trades;
            renderPoliticianTrades(politicianTrades);
        }
    } catch (e) {
        console.error('Error loading politician trades:', e);
        showToast('Failed to load politician trades', 'error');
    }
}

/**
 * Load followed traders from localStorage
 */
function loadFollowedTraders() {
    try {
        const saved = localStorage.getItem('followedTraders');
        if (saved) {
            followedTraders = new Set(JSON.parse(saved));
        }
    } catch (e) {
        console.error('Error loading followed traders:', e);
    }
}

/**
 * Save followed traders to localStorage
 */
function saveFollowedTraders() {
    try {
        localStorage.setItem('followedTraders', JSON.stringify([...followedTraders]));
    } catch (e) {
        console.error('Error saving followed traders:', e);
    }
}

/**
 * Render trader cards
 */
function renderTraders(traders) {
    const grid = document.getElementById('traderGrid');
    
    if (traders.length === 0) {
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">
                <div style="font-size: 3em; margin-bottom: 15px;">🔍</div>
                <div>No traders match your filters</div>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = traders.map(trader => createTraderCard(trader)).join('');
}

/**
 * Create a trader card HTML
 */
function createTraderCard(trader) {
    const isFollowing = followedTraders.has(trader.id);
    const perfClass = trader.performance >= 0 ? 'positive' : 'negative';
    const riskClass = trader.riskLevel === 'low' ? 'risk-low' : trader.riskLevel === 'medium' ? 'risk-medium' : 'risk-high';
    const badgeClass = `badge-${trader.badge}`;
    
    return `
        <div class="trader-card">
            <div class="trader-header">
                <div class="trader-name">${trader.name}</div>
                <div class="trader-badge ${badgeClass}">${trader.badge}</div>
            </div>
            
            <div class="trader-stats">
                <div class="stat-item">
                    <div class="stat-label">Total Return</div>
                    <div class="stat-value ${perfClass}">+${trader.performance}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value">${trader.winRate}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Avg Return</div>
                    <div class="stat-value positive">+${trader.avgReturn}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Sharpe Ratio</div>
                    <div class="stat-value">${trader.sharpeRatio}</div>
                </div>
            </div>
            
            <div class="risk-meter">
                <div class="stat-label">Risk Level: ${trader.riskLevel.toUpperCase()}</div>
                <div class="risk-bar">
                    <div class="risk-fill ${riskClass}" style="width: ${trader.riskScore}%"></div>
                </div>
            </div>
            
            <div style="color: var(--text-secondary); font-size: 0.9em; margin: 12px 0; line-height: 1.5;">
                ${trader.description}
            </div>
            
            <div class="strategy-tags">
                ${trader.strategies.map(s => `<div class="strategy-tag">${s}</div>`).join('')}
            </div>
            
            <div class="followers-count">
                <span>👥</span>
                <span>${trader.followers.toLocaleString()} followers</span>
                <span style="margin-left: auto;">📊 ${trader.totalTrades} trades</span>
            </div>
            
            <div class="trader-actions">
                <button class="btn-follow ${isFollowing ? 'following' : ''}" onclick="toggleFollow(${trader.id})">
                    ${isFollowing ? '✓ Following' : '+ Follow'}
                </button>
                <button class="btn-details" onclick="showTraderDetails(${trader.id})" title="View Details">
                    📊
                </button>
            </div>
        </div>
    `;
}

/**
 * Toggle follow status for a trader
 */
function toggleFollow(traderId) {
    if (followedTraders.has(traderId)) {
        followedTraders.delete(traderId);
    } else {
        followedTraders.add(traderId);
    }
    
    saveFollowedTraders();
    renderTraders(allTraders);
    
    const trader = allTraders.find(t => t.id === traderId);
    const action = followedTraders.has(traderId) ? 'following' : 'unfollowed';
    showToast(`${action === 'following' ? 'Now following' : 'Unfollowed'} ${trader.name}`, 'success');
}

/**
 * Show trader details
 */
function showTraderDetails(traderId) {
    const trader = allTraders.find(t => t.id === traderId);
    if (!trader) return;
    
    alert(`Detailed analysis for ${trader.name}:\n\n` +
          `Total Return: +${trader.performance}%\n` +
          `Win Rate: ${trader.winRate}%\n` +
          `Sharpe Ratio: ${trader.sharpeRatio}\n` +
          `Max Drawdown: ${trader.maxDrawdown}%\n` +
          `Total Trades: ${trader.totalTrades}\n` +
          `Strategies: ${trader.strategies.join(', ')}\n\n` +
          `Full analytics dashboard coming soon!`);
}

/**
 * Filter traders based on selected criteria
 */
function filterTraders() {
    const strategy = document.getElementById('strategyFilter').value;
    const risk = document.getElementById('riskFilter').value;
    const minReturn = parseFloat(document.getElementById('returnFilter').value);
    
    let filtered = [...sampleTraders];
    
    // Filter by strategy
    if (strategy !== 'all') {
        filtered = filtered.filter(t => 
            t.strategies.some(s => s.toLowerCase() === strategy.toLowerCase())
        );
    }
    
    // Filter by risk
    if (risk !== 'all') {
        filtered = filtered.filter(t => t.riskLevel === risk);
    }
    
    // Filter by minimum return
    if (minReturn > 0) {
        filtered = filtered.filter(t => t.performance >= minReturn);
    }
    
    allTraders = filtered;
    sortTraders();
}

/**
 * Sort traders by selected criteria
 */
function sortTraders() {
    const sortBy = document.getElementById('sortBy').value;
    
    switch (sortBy) {
        case 'performance':
            allTraders.sort((a, b) => b.performance - a.performance);
            break;
        case 'followers':
            allTraders.sort((a, b) => b.followers - a.followers);
            break;
        case 'winrate':
            allTraders.sort((a, b) => b.winRate - a.winRate);
            break;
        case 'risk':
            allTraders.sort((a, b) => a.riskScore - b.riskScore);
            break;
    }
    
    renderTraders(allTraders);
}

/**
 * Render politician trades
 */
function renderPoliticianTrades(trades) {
    const grid = document.getElementById('politicianGrid');
    
    if (!grid) return;
    
    if (trades.length === 0) {
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">
                <div style="font-size: 3em; margin-bottom: 15px;">🏛️</div>
                <div>No politician trades found</div>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = trades.map(trade => createPoliticianTradeCard(trade)).join('');
}

/**
 * Create politician trade card HTML
 */
function createPoliticianTradeCard(trade) {
    const transactionClass = trade.transaction === 'Purchase' ? 'positive' : 'negative';
    const transactionIcon = trade.transaction === 'Purchase' ? '📈' : '📉';
    const partyColor = trade.party === 'Democrat' ? '#3b82f6' : '#ef4444';
    
    const daysAgo = Math.floor((new Date() - new Date(trade.date)) / (1000 * 60 * 60 * 24));
    const timeAgo = daysAgo === 0 ? 'Today' : daysAgo === 1 ? 'Yesterday' : `${daysAgo} days ago`;
    
    return `
        <div class="politician-card">
            <div class="politician-header">
                <div>
                    <div class="politician-name">${trade.politician}</div>
                    <div class="politician-info">
                        <span style="color: ${partyColor}">●</span>
                        ${trade.party} • ${trade.chamber} • ${trade.state}
                    </div>
                </div>
                <div class="transaction-badge ${transactionClass}">
                    ${transactionIcon} ${trade.transaction}
                </div>
            </div>
            
            <div class="trade-symbol">
                <div style="font-size: 1.4em; font-weight: 600; color: var(--text-primary);">
                    ${trade.symbol}
                </div>
                <div style="color: var(--text-secondary); font-size: 0.9em;">
                    ${trade.company}
                </div>
            </div>
            
            <div class="trade-details">
                <div class="detail-row">
                    <span class="detail-label">Amount:</span>
                    <span class="detail-value">${trade.amount_range}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Trade Date:</span>
                    <span class="detail-value">${trade.date} (${timeAgo})</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Filed:</span>
                    <span class="detail-value">${trade.filed_date}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Owner:</span>
                    <span class="detail-value">${trade.owner}</span>
                </div>
                ${trade.current_price ? `
                <div class="detail-row">
                    <span class="detail-label">Current Price:</span>
                    <span class="detail-value">$${trade.current_price}</span>
                </div>
                ` : ''}
            </div>
            
            <div class="trade-actions">
                <button class="btn-action btn-primary" onclick="addToWatchlist('${trade.symbol}')">
                    + Add to Watchlist
                </button>
                <button class="btn-action btn-secondary" onclick="viewSymbolDetails('${trade.symbol}')">
                    📊 Analyze
                </button>
            </div>
        </div>
    `;
}

/**
 * Filter politician trades
 */
function filterPoliticianTrades() {
    const chamber = document.getElementById('chamberFilter')?.value || 'all';
    const party = document.getElementById('partyFilter')?.value || 'all';
    const transaction = document.getElementById('transactionFilter')?.value || 'all';
    
    let filtered = [...politicianTrades];
    
    if (chamber !== 'all') {
        filtered = filtered.filter(t => t.chamber === chamber);
    }
    
    if (party !== 'all') {
        filtered = filtered.filter(t => t.party === party);
    }
    
    if (transaction !== 'all') {
        filtered = filtered.filter(t => t.transaction === transaction);
    }
    
    renderPoliticianTrades(filtered);
}

/**
 * Sort politician trades
 */
function sortPoliticianTrades() {
    const sortBy = document.getElementById('politicianSortBy')?.value || 'date';
    let sorted = [...politicianTrades];
    
    switch (sortBy) {
        case 'date':
            sorted.sort((a, b) => new Date(b.date) - new Date(a.date));
            break;
        case 'amount':
            sorted.sort((a, b) => b.amount_max - a.amount_max);
            break;
        case 'politician':
            sorted.sort((a, b) => a.politician.localeCompare(b.politician));
            break;
        case 'symbol':
            sorted.sort((a, b) => a.symbol.localeCompare(b.symbol));
            break;
    }
    
    renderPoliticianTrades(sorted);
}

/**
 * Add symbol to watchlist - shows selection modal
 */
function addToWatchlist(symbol) {
    if (window.watchlistManager) {
        showWatchlistSelectionModal(symbol);
    } else {
        // Fallback to direct add
        addToWatchlistDirect(symbol, null);
    }
}

/**
 * Show modal to select which watchlist to add to
 */
function showWatchlistSelectionModal(symbol) {
    const watchlists = window.watchlistManager.getAllWatchlistNames();
    const currentWatchlist = window.watchlistManager.getCurrentWatchlist();
    
    // Create modal HTML
    const modalHTML = `
        <div class="watchlist-modal-overlay" id="watchlistModal" onclick="closeWatchlistModal(event)">
            <div class="watchlist-modal" onclick="event.stopPropagation()">
                <div class="watchlist-modal-header">
                    <h3>Add ${symbol} to Watchlist</h3>
                    <button class="close-btn" onclick="closeWatchlistModal()">&times;</button>
                </div>
                <div class="watchlist-modal-body">
                    <p style="margin-bottom: 15px; color: var(--text-secondary);">
                        Select which watchlist to add this symbol to:
                    </p>
                    <div class="watchlist-options">
                        ${watchlists.map(name => `
                            <div class="watchlist-option ${name === currentWatchlist ? 'current' : ''}" 
                                 onclick="addToSelectedWatchlist('${symbol}', '${name}')">
                                <span class="watchlist-icon">📋</span>
                                <span class="watchlist-name">${name}</span>
                                ${name === currentWatchlist ? '<span class="current-badge">Current</span>' : ''}
                            </div>
                        `).join('')}
                    </div>
                    <button class="btn-create-watchlist" onclick="createNewWatchlistForSymbol('${symbol}')">
                        + Create New Watchlist
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existing = document.getElementById('watchlistModal');
    if (existing) existing.remove();
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Close watchlist selection modal
 */
function closeWatchlistModal(event) {
    if (!event || event.target.classList.contains('watchlist-modal-overlay') || event.target.classList.contains('close-btn')) {
        const modal = document.getElementById('watchlistModal');
        if (modal) modal.remove();
    }
}

/**
 * Add symbol to selected watchlist
 */
async function addToSelectedWatchlist(symbol, watchlistName) {
    closeWatchlistModal();
    const previousWatchlist = window.watchlistManager.getCurrentWatchlist();
    
    // Switch to selected watchlist temporarily
    window.watchlistManager.setCurrentWatchlist(watchlistName);
    
    // Add to the selected watchlist
    await addToWatchlistDirect(symbol, watchlistName);
    
    // Switch back to previous watchlist
    window.watchlistManager.setCurrentWatchlist(previousWatchlist);
}

/**
 * Create new watchlist and add symbol
 */
function createNewWatchlistForSymbol(symbol) {
    closeWatchlistModal();
    const name = prompt('Enter name for new watchlist:');
    if (name && name.trim()) {
        if (window.watchlistManager.createWatchlist(name.trim())) {
            addToSelectedWatchlist(symbol, name.trim());
        } else {
            showToast('Watchlist name already exists or is invalid', 'error');
        }
    }
}

/**
 * Add symbol to watchlist directly (internal function)
 */
async function addToWatchlistDirect(symbol, watchlistName) {
    try {
        showToast(`Adding ${symbol} to ${watchlistName || 'watchlist'}...`, 'info');
        
        const response = await fetch('/api/watchlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                symbol: symbol,
                notes: `Added from politician trades to ${watchlistName || 'default'}`
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast(`${symbol} added to ${watchlistName || 'watchlist'}!`, 'success');
            
            // Also add locally if watchlistManager exists
            if (window.watchlistManager) {
                window.watchlistManager.add(symbol);
            } else {
                // Fallback to localStorage
                try {
                    const watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
                    if (!watchlist.includes(symbol)) {
                        watchlist.push(symbol);
                        localStorage.setItem('watchlist', JSON.stringify(watchlist));
                    }
                } catch (e) {
                    console.error('Error updating localStorage:', e);
                }
            }
        } else {
            if (data.error && data.error.includes('already in watchlist')) {
                showToast(`${symbol} is already in your watchlist`, 'info');
            } else {
                showToast(data.error || 'Failed to add to watchlist', 'error');
            }
        }
    } catch (e) {
        console.error('Error adding to watchlist:', e);
        showToast('Failed to add to watchlist', 'error');
    }
}

/**
 * View symbol details
 */
function viewSymbolDetails(symbol) {
    // Navigate to analysis dashboard with symbol
    window.location.href = `/dashboard?symbol=${symbol}`;
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Simple toast notification
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(400px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(400px); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
