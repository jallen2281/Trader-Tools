/**
 * Volatile Stocks Scanner
 * Displays top volatile stocks, fastest movers, volume leaders, and momentum stocks
 */

let volatileStocksData = {
    volatile: [],
    movers: [],
    volume: [],
    momentum: []
};

let currentTab = 'volatile';

// Initialize when DOM loads
document.addEventListener('DOMContentLoaded', function() {
    initializeVolatileStocks();
});

function initializeVolatileStocks() {
    const modal = document.getElementById('volatileStocksModal');
    const btn = document.getElementById('volatileStocksBtn');
    const closeBtn = modal?.querySelector('.modal-close');
    const refreshBtn = document.getElementById('refreshVolatileStocks');
    
    // Open modal
    btn?.addEventListener('click', function() {
        modal.style.display = 'flex';
        if (volatileStocksData.volatile.length === 0) {
            loadVolatileStocks();
        }
    });
    
    // Close modal
    closeBtn?.addEventListener('click', function() {
        modal.style.display = 'none';
    });
    
    // Close on outside click
    window.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Refresh button
    refreshBtn?.addEventListener('click', function() {
        loadVolatileStocks(true);
    });
    
    // Tab switching
    const tabButtons = modal?.querySelectorAll('.tab-button');
    tabButtons?.forEach(button => {
        button.addEventListener('click', function() {
            switchVolatileTab(this.dataset.tab);
        });
    });
}

function switchVolatileTab(tab) {
    currentTab = tab;
    
    // Update tab buttons
    document.querySelectorAll('#volatileStocksModal .tab-button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tab) {
            btn.classList.add('active');
        }
    });
    
    // Update tab content
    document.querySelectorAll('#volatileStocksModal .tab-content').forEach(content => {
        content.style.display = 'none';
    });
    
    const tabMap = {
        'volatile': 'volatileTab',
        'movers': 'moversTab',
        'volume': 'volumeTab',
        'momentum': 'momentumTab'
    };
    
    const activeContent = document.getElementById(tabMap[tab]);
    if (activeContent) {
        activeContent.style.display = 'block';
    }
    
    // Load data if not already loaded
    if (tab === 'volatile' && volatileStocksData.volatile.length === 0) {
        loadVolatileStocks();
    } else if (tab === 'movers' && volatileStocksData.movers.length === 0) {
        loadFastestMovers();
    } else if (tab === 'volume' && volatileStocksData.volume.length === 0) {
        loadVolumeLeaders();
    } else if (tab === 'momentum' && volatileStocksData.momentum.length === 0) {
        loadMomentumStocks();
    }
}

async function loadVolatileStocks(forceRefresh = false) {
    const loadingEl = document.getElementById('volatileStocksLoading');
    const errorEl = document.getElementById('volatileStocksError');
    const listEl = document.getElementById('volatileStocksList');
    
    if (!listEl) return;
    
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    listEl.innerHTML = '';
    
    try {
        const response = await fetch('/api/market/volatile-stocks?limit=50');
        
        if (!response.ok) {
            throw new Error('Failed to fetch volatile stocks');
        }
        
        const data = await response.json();
        volatileStocksData.volatile = data.stocks || [];
        
        loadingEl.style.display = 'none';
        renderStocksList(volatileStocksData.volatile, listEl, 'volatile');
        
    } catch (error) {
        console.error('Error loading volatile stocks:', error);
        loadingEl.style.display = 'none';
        errorEl.textContent = '⚠️ Failed to load volatile stocks. Please try again.';
        errorEl.style.display = 'block';
    }
}

async function loadFastestMovers() {
    const loadingEl = document.getElementById('volatileStocksLoading');
    const errorEl = document.getElementById('volatileStocksError');
    const listEl = document.getElementById('fastestMoversList');
    
    if (!listEl) return;
    
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    listEl.innerHTML = '';
    
    try {
        const response = await fetch('/api/market/fastest-movers?limit=25');
        
        if (!response.ok) {
            throw new Error('Failed to fetch fastest movers');
        }
        
        const data = await response.json();
        volatileStocksData.movers = data.movers || [];
        
        loadingEl.style.display = 'none';
        renderStocksList(volatileStocksData.movers, listEl, 'movers');
        
    } catch (error) {
        console.error('Error loading fastest movers:', error);
        loadingEl.style.display = 'none';
        errorEl.textContent = '⚠️ Failed to load fastest movers. Please try again.';
        errorEl.style.display = 'block';
    }
}

async function loadVolumeLeaders() {
    const loadingEl = document.getElementById('volatileStocksLoading');
    const errorEl = document.getElementById('volatileStocksError');
    const listEl = document.getElementById('volumeLeadersList');
    
    if (!listEl) return;
    
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    listEl.innerHTML = '';
    
    try {
        const response = await fetch('/api/market/volume-leaders?limit=25');
        
        if (!response.ok) {
            throw new Error('Failed to fetch volume leaders');
        }
        
        const data = await response.json();
        volatileStocksData.volume = data.leaders || [];
        
        loadingEl.style.display = 'none';
        renderStocksList(volatileStocksData.volume, listEl, 'volume');
        
    } catch (error) {
        console.error('Error loading volume leaders:', error);
        loadingEl.style.display = 'none';
        errorEl.textContent = '⚠️ Failed to load volume leaders. Please try again.';
        errorEl.style.display = 'block';
    }
}

async function loadMomentumStocks() {
    const loadingEl = document.getElementById('volatileStocksLoading');
    const errorEl = document.getElementById('volatileStocksError');
    const listEl = document.getElementById('momentumStocksList');
    
    if (!listEl) return;
    
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    listEl.innerHTML = '';
    
    try {
        const response = await fetch('/api/market/momentum-stocks?limit=25');
        
        if (!response.ok) {
            throw new Error('Failed to fetch momentum stocks');
        }
        
        const data = await response.json();
        volatileStocksData.momentum = data.stocks || [];
        
        loadingEl.style.display = 'none';
        renderStocksList(volatileStocksData.momentum, listEl, 'momentum');
        
    } catch (error) {
        console.error('Error loading momentum stocks:', error);
        loadingEl.style.display = 'none';
        errorEl.textContent = '⚠️ Failed to load momentum stocks. Please try again.';
        errorEl.style.display = 'block';
    }
}

function renderStocksList(stocks, container, type) {
    if (!stocks || stocks.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary);">No stocks found</div>';
        return;
    }
    
    container.innerHTML = stocks.map(stock => createStockCard(stock, type)).join('');
    
    // Add event listeners to action buttons
    container.querySelectorAll('.stock-action-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const symbol = this.dataset.symbol;
            const action = this.dataset.action;
            
            if (action === 'analyze') {
                analyzeStock(symbol);
            } else if (action === 'watchlist') {
                addToWatchlistFromScanner(symbol);
            }
        });
    });
    
    // Make cards clickable
    container.querySelectorAll('.stock-card').forEach(card => {
        card.addEventListener('click', function() {
            const symbol = this.dataset.symbol;
            analyzeStock(symbol);
        });
    });
}

function createStockCard(stock, type) {
    const changeClass = stock.daily_change_pct >= 0 ? 'positive' : 'negative';
    const changeIcon = stock.daily_change_pct >= 0 ? '📈' : '📉';
    const momentumClass = stock.momentum_5d >= 0 ? 'positive' : 'negative';
    
    // Format market cap
    const marketCap = stock.market_cap ? formatMarketCap(stock.market_cap) : 'N/A';
    
    // Truncate long names
    const displayName = stock.name.length > 25 ? stock.name.substring(0, 22) + '...' : stock.name;
    const displaySector = stock.sector.length > 15 ? stock.sector.substring(0, 12) + '...' : stock.sector;
    
    // Main metric based on type
    let primaryMetric = '';
    if (type === 'volatile') {
        primaryMetric = `<div class="metric-highlight">Vol Score: <strong>${stock.volatility_score}</strong></div>`;
    } else if (type === 'movers') {
        primaryMetric = `<div class="metric-highlight ${changeClass}">Change: <strong>${stock.daily_change_pct > 0 ? '+' : ''}${stock.daily_change_pct}%</strong></div>`;
    } else if (type === 'volume') {
        primaryMetric = `<div class="metric-highlight">Vol Surge: <strong>${stock.volume_ratio}x</strong></div>`;
    } else if (type === 'momentum') {
        primaryMetric = `<div class="metric-highlight ${momentumClass}">5D Mom: <strong>${stock.momentum_5d > 0 ? '+' : ''}${stock.momentum_5d}%</strong></div>`;
    }
    
    return `
        <div class="stock-card" data-symbol="${stock.symbol}">
            <div class="stock-card-header">
                <div>
                    <div class="stock-symbol">${stock.symbol}</div>
                    <div class="stock-name" title="${stock.name}">${displayName}</div>
                </div>
                <div class="stock-price">
                    <div class="price-value">$${stock.price}</div>
                    <div class="price-change ${changeClass}">
                        ${changeIcon} ${stock.daily_change_pct > 0 ? '+' : ''}${stock.daily_change_pct}%
                    </div>
                </div>
            </div>
            
            ${primaryMetric}
            
            <div class="stock-metrics">
                <div class="metric-row">
                    <span class="metric-label">ATR:</span>
                    <span class="metric-value">${stock.atr_percent}%</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Vol:</span>
                    <span class="metric-value">${stock.hist_volatility}%</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Ratio:</span>
                    <span class="metric-value">${stock.volume_ratio}x</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Range:</span>
                    <span class="metric-value">${stock.today_range_pct}%</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Sector:</span>
                    <span class="metric-value" title="${stock.sector}">${displaySector}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Mkt Cap:</span>
                    <span class="metric-value">${marketCap}</span>
                </div>
            </div>
            
            <div class="stock-actions">
                <button class="stock-action-btn" data-symbol="${stock.symbol}" data-action="analyze" title="Analyze">
                    🔍 Analyze
                </button>
                <button class="stock-action-btn" data-symbol="${stock.symbol}" data-action="watchlist" title="Add to Watchlist">
                    ⭐ Watch
                </button>
            </div>
        </div>
    `;
}

function formatMarketCap(marketCap) {
    if (marketCap >= 1e12) {
        return `$${(marketCap / 1e12).toFixed(2)}T`;
    } else if (marketCap >= 1e9) {
        return `$${(marketCap / 1e9).toFixed(2)}B`;
    } else if (marketCap >= 1e6) {
        return `$${(marketCap / 1e6).toFixed(2)}M`;
    }
    return '$' + marketCap.toLocaleString();
}

function analyzeStock(symbol) {
    // Close the volatile stocks modal
    document.getElementById('volatileStocksModal').style.display = 'none';
    
    // Set the symbol in the analyze form
    const symbolInput = document.getElementById('symbol');
    if (symbolInput) {
        symbolInput.value = symbol;
        
        // Trigger analysis
        const analyzeForm = document.getElementById('analyzeForm');
        if (analyzeForm) {
            analyzeForm.dispatchEvent(new Event('submit'));
        }
    }
}

function addToWatchlistFromScanner(symbol) {
    // Use the existing watchlist functionality
    if (typeof watchlistManager !== 'undefined') {
        watchlistManager.add(symbol);
        showToast(`${symbol} added to watchlist`, 'success');
    } else {
        // Fallback to direct add
        const watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
        if (!watchlist.includes(symbol)) {
            watchlist.push(symbol);
            localStorage.setItem('watchlist', JSON.stringify(watchlist));
            showToast(`${symbol} added to watchlist`, 'success');
        } else {
            showToast(`${symbol} already in watchlist`, 'info');
        }
    }
}

function showToast(message, type = 'info') {
    // Simple toast notification
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 10001;
        animation: slideInUp 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
