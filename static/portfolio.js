/**
 * Portfolio Analytics Dashboard - JavaScript
 * Phase 4: Portfolio Management & Real-Time Intelligence
 */

let currentPortfolio = null;
let currentVix = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Portfolio dashboard initializing...');
    loadAccounts();
    loadPortfolioData();
    loadVixData();
    loadActiveAlerts();
    initPortfolioChart();
    
    // Auto-refresh every 60 seconds
    setInterval(() => {
        loadPortfolioData();
        loadVixData();
    }, 60000);
    
    // Add click-outside-to-close for all modals
    setupModalCloseHandlers();
});

/**
 * Setup modal close handlers (click outside to close)
 */
function setupModalCloseHandlers() {
    const modals = ['holdingModal', 'addPositionModal', 'createAlertModal'];
    
    modals.forEach(modalId => {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.addEventListener('click', (e) => {
                // Close if clicked on the modal backdrop (not the content)
                if (e.target === modal) {
                    modal.classList.remove('active');
                }
            });
        }
    });
    
    // ESC key to close active modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            modals.forEach(modalId => {
                const modal = document.getElementById(modalId);
                if (modal && modal.classList.contains('active')) {
                    modal.classList.remove('active');
                    // Reset forms if needed
                    if (modalId === 'addPositionModal') {
                        document.getElementById('addPositionForm').reset();
                    } else if (modalId === 'createAlertModal') {
                        document.getElementById('createAlertForm').reset();
                    }
                }
            });
        }
    });
}

/**
 * Load portfolio data
 */
async function loadPortfolioData() {
    try {
        const response = await fetch('/api/portfolio');
        
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }
            throw new Error('Failed to load portfolio');
        }
        
        const data = await response.json();
        currentPortfolio = data;
        
        displayPortfolioSummary(data);
        await loadHoldings();
        
    } catch (error) {
        console.error('Error loading portfolio:', error);
        showError('Could not load portfolio data');
    }
}

/**
 * Display portfolio summary stats
 */
function displayPortfolioSummary(data) {
    // Handle empty or missing data
    const totalValue = data.total_value || 0;
    const totalPnl = data.total_pnl || 0;
    const totalPnlPct = data.total_pnl_pct || 0;
    
    // Total value
    document.getElementById('totalValue').textContent = `$${totalValue.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    
    // Total P&L
    const pnlElement = document.getElementById('totalPnL');
    const pnlPctElement = document.getElementById('totalPnLPct');
    
    pnlElement.textContent = `$${totalPnl.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    pnlPctElement.textContent = `${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(2)}%`;
    
    if (totalPnl >= 0) {
        pnlElement.classList.add('pnl-positive');
        pnlElement.classList.remove('pnl-negative');
        pnlPctElement.classList.add('pnl-positive');
        pnlPctElement.classList.remove('pnl-negative');
    } else {
        pnlElement.classList.add('pnl-negative');
        pnlElement.classList.remove('pnl-positive');
        pnlPctElement.classList.add('pnl-negative');
        pnlPctElement.classList.remove('pnl-positive');
    }
    
    // Daily change
    if (data.daily_change) {
        const dailyElement = document.getElementById('dailyChange');
        const dailyPctElement = document.getElementById('dailyChangePct');
        
        const dailyValue = data.daily_change.value || 0;
        const dailyPct = data.daily_change.pct || 0;
        
        dailyElement.textContent = `$${dailyValue.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        dailyPctElement.textContent = `${dailyPct >= 0 ? '+' : ''}${dailyPct.toFixed(2)}%`;
        
        if (dailyValue >= 0) {
            dailyElement.classList.add('pnl-positive');
            dailyPctElement.classList.add('pnl-positive');
        } else {
            dailyElement.classList.add('pnl-negative');
            dailyPctElement.classList.add('pnl-negative');
        }
    } else {
        // No daily change data
        document.getElementById('dailyChange').textContent = '$0.00';
        document.getElementById('dailyChangePct').textContent = '0.00%';
    }
    
    // Holdings count
    document.getElementById('holdingsCount').textContent = data.holdings_count || 0;
    
    // Allocation
    if (data.allocation) {
        document.getElementById('allocation').textContent = 
            `${data.allocation.stocks || 0}% stocks / ${data.allocation.options || 0}% options`;
    } else {
        document.getElementById('allocation').textContent = '0% stocks / 0% options';
    }
}

/**
 * Load holdings table
 */
async function loadHoldings() {
    try {
        // Get stock holdings
        // Get stock holdings, filtered by selected account
        const accountId = document.getElementById('accountSelector')?.value || 'all';
        const accountParam = accountId !== 'all' ? `?account_id=${accountId}` : '';
        const stockResponse = await fetch('/api/portfolio/list' + accountParam);
        if (!stockResponse.ok) throw new Error('Failed to load holdings');
        
        const stocksData = await stockResponse.json();
        const stocks = stocksData.holdings || [];
        
        // Get options positions
        const optionsResponse = await fetch('/api/options');
        const optionsData = await optionsResponse.json();
        const options = optionsData.positions || [];
        
        const tableBody = document.getElementById('holdingsTableBody');
        tableBody.innerHTML = '';
        
        if (stocks.length === 0 && options.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px; color: #999;">
                        No holdings yet. Add positions to track your portfolio.
                    </td>
                </tr>
            `;
            return;
        }
        
        // Add stock holdings
        stocks.forEach(holding => {
            const row = createHoldingRow(holding, 'stock');
            tableBody.appendChild(row);
        });
        
        // Add options positions
        options.forEach(option => {
            const row = createOptionRow(option);
            tableBody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Error loading holdings:', error);
    }
}

/**
 * Create table row for stock holding
 */
function createHoldingRow(holding, type = 'stock') {
    const row = document.createElement('tr');
    row.onclick = () => openHoldingModal(holding.id, type);
    
    const pnlClass = holding.gain_loss >= 0 ? 'pnl-positive' : 'pnl-negative';
    
    // Generate recommendation badge
    let recommendation = 'HOLD';
    let actionClass = 'action-hold';
    
    if (holding.gain_loss_pct > 30) {
        recommendation = 'TRIM';
        actionClass = 'action-trim';
    } else if (holding.gain_loss_pct > 15) {
        recommendation = 'HOLD';
        actionClass = 'action-hold';
    } else if (holding.gain_loss_pct < -20) {
        recommendation = 'REVIEW';
        actionClass = 'action-sell';
    }
    
    row.innerHTML = `
        <td><strong>${holding.symbol}</strong></td>
        <td>${holding.quantity.toLocaleString()}</td>
        <td>$${holding.average_cost.toFixed(4)}</td>
        <td>$${holding.current_price.toFixed(2)}</td>
        <td>$${holding.market_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="${pnlClass}">$${holding.gain_loss.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="${pnlClass}">${holding.gain_loss_pct >= 0 ? '+' : ''}${holding.gain_loss_pct.toFixed(2)}%</td>
        <td><span class="action-badge ${actionClass}">${recommendation}</span></td>
    `;
    
    return row;
}

/**
 * Create table row for option position
 */
function createOptionRow(option) {
    const row = document.createElement('tr');
    row.onclick = () => openHoldingModal(option.id, 'option');
    
    const pnlClass = option.gain_loss >= 0 ? 'pnl-positive' : 'pnl-negative';
    const optionLabel = `${option.underlying_symbol} ${option.strike_price} ${option.option_type.toUpperCase()}`;
    
    row.innerHTML = `
        <td><strong>${optionLabel}</strong><br><small>${option.expiration_date}</small></td>
        <td>${option.quantity} contracts</td>
        <td>$${option.premium_paid.toFixed(4)}</td>
        <td>$${option.current_premium.toFixed(2)}</td>
        <td>$${option.market_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="${pnlClass}">$${option.gain_loss.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="${pnlClass}">${option.gain_loss_pct >= 0 ? '+' : ''}${option.gain_loss_pct.toFixed(2)}%</td>
        <td><span class="action-badge action-hold">MONITOR</span></td>
    `;
    
    return row;
}

/**
 * Open holding detail modal
 */
async function openHoldingModal(holdingId, type = 'stock') {
    try {
        const response = await fetch(`/api/portfolio/holding/${holdingId}?type=${type}`);
        if (!response.ok) throw new Error('Failed to load holding details');
        
        const data = await response.json();
        
        document.getElementById('modalSymbol').textContent = data.symbol;
        
        // Build account options for dropdown
        const accountOptions = portfolioAccounts.map(acc => {
            const selected = acc.id === data.account_id ? 'selected' : '';
            const style = STYLE_COLORS[acc.investment_style] || STYLE_COLORS.balanced;
            return `<option value="${acc.id}" ${selected}>${acc.name} (${style.label})</option>`;
        }).join('');
        const noAccountSelected = !data.account_id ? 'selected' : '';
        
        const detailsDiv = document.getElementById('holdingDetails');
        detailsDiv.innerHTML = `
            <div style="margin-bottom: 20px;">
                <h3>Position Details</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                    <div>
                        <strong>Quantity:</strong> ${data.quantity.toLocaleString()}
                    </div>
                    <div>
                        <strong>Cost Basis:</strong> $${data.cost_basis.toFixed(4)}
                    </div>
                    ${data.purchase_date ? `<div>
                        <strong>Purchase Date:</strong> ${new Date(data.purchase_date).toLocaleDateString()}
                    </div>` : ''}
                    <div>
                        <strong>Current Price:</strong> $${data.current_price.toFixed(2)}
                    </div>
                    <div>
                        <strong>Market Value:</strong> $${data.market_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </div>
                    <div class="${data.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                        <strong>P&L:</strong> $${data.pnl.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${data.pnl_pct.toFixed(2)}%)
                    </div>
                </div>
            </div>
            
            <div style="margin-bottom: 20px; padding: 15px; background: var(--light); border-radius: 8px;">
                <h3 style="margin-bottom: 10px;">📂 Account</h3>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <select id="holdingAccountSelect" style="flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color, #ccc); background: var(--card-bg, #fff); color: var(--text-color, #333); font-size: 0.95em;">
                        <option value="" ${noAccountSelected}>No Account</option>
                        ${accountOptions}
                    </select>
                    <button onclick="changeHoldingAccount(${holdingId}, '${type}')" class="btn btn-primary" style="padding: 8px 16px; white-space: nowrap;">Move</button>
                </div>
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button onclick="openSellPositionModal(${holdingId}, '${type}')" class="btn btn-primary" style="flex: 1;">💰 Sell/Edit Position</button>
                <button onclick="deletePosition(${holdingId}, '${type}')" class="btn btn-danger">🗑️ Delete</button>
            </div>
            
            ${data.phase3 ? `
            <div style="margin-bottom: 20px;">
                <h3>Market Analysis</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                    <div>
                        <strong>Sentiment:</strong> ${data.phase3.sentiment} (${data.phase3.sentiment_score}/100)
                    </div>
                    <div>
                        <strong>Risk Grade:</strong> ${data.phase3.risk_grade}
                    </div>
                    <div>
                        <strong>Entry Score:</strong> ${data.phase3.entry_score}/100
                    </div>
                    <div>
                        <strong>Recommendation:</strong> ${data.phase3.entry_recommendation}
                    </div>
                </div>
            </div>
            ` : ''}
            
            <div style="padding: 20px; background: var(--light); border-radius: 8px;">
                <h3>Our Recommendation</h3>
                <div style="margin-top: 10px;">
                    <span class="action-badge ${getActionClass(data.recommendation.action)}" style="font-size: 1.1em; padding: 8px 16px;">
                        ${data.recommendation.action}
                    </span>
                    <p style="margin-top: 15px; line-height: 1.6;">${data.recommendation.reason}</p>
                </div>
            </div>
        `;
        
        document.getElementById('holdingModal').classList.add('active');
        
    } catch (error) {
        console.error('Error loading holding details:', error);
        alert('Could not load holding details');
    }
}

// Make function globally accessible
window.openHoldingModal = openHoldingModal;

async function changeHoldingAccount(holdingId, type) {
    const select = document.getElementById('holdingAccountSelect');
    const newAccountId = select.value ? parseInt(select.value) : null;
    
    try {
        const response = await fetch(`/api/portfolio/holding/${holdingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: newAccountId })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to move holding');
        }
        
        const accountName = newAccountId 
            ? portfolioAccounts.find(a => a.id === newAccountId)?.name || 'account'
            : 'No Account';
        showToast(`Moved to ${accountName}`, 'success');
        closeHoldingModal();
        loadHoldings();
    } catch (error) {
        console.error('Error changing holding account:', error);
        showToast(error.message, 'error');
    }
}
window.changeHoldingAccount = changeHoldingAccount;

function getActionClass(action) {
    const classMap = {
        'BUY MORE': 'action-buy-more',
        'ADD': 'action-buy-more',
        'HOLD': 'action-hold',
        'TRIM': 'action-trim',
        'SELL': 'action-sell',
        'CONSIDER_SELLING': 'action-sell',
        'REVIEW': 'action-sell'
    };
    return classMap[action] || 'action-hold';
}

function closeHoldingModal() {
    document.getElementById('holdingModal').classList.remove('active');
}

// Make function globally accessible
window.closeHoldingModal = closeHoldingModal;

/**
 * Load VIX data
 */
async function loadVixData() {
    try {
        const response = await fetch('/api/market/vix');
        if (!response.ok) throw new Error('VIX data not available');
        
        const data = await response.json();
        currentVix = data;
        
        // Display VIX level
        document.getElementById('vixLevel').textContent = data.current;
        
        // Display change
        const changeElement = document.getElementById('vixChange');
        const changeText = `${data.change >= 0 ? '+' : ''}${data.change} (${data.change_pct >= 0 ? '+' : ''}${data.change_pct}%)`;
        changeElement.textContent = changeText;
        changeElement.style.color = data.change >= 0 ? 'var(--danger)' : 'var(--success)';
        
        // Display regime
        const regimeElement = document.getElementById('vixRegime');
        regimeElement.textContent = data.regime.toUpperCase();
        regimeElement.className = `vix-regime regime-${data.regime}`;
        
        // Display interpretation
        document.getElementById('vixInterpretation').textContent = data.interpretation;
        
    } catch (error) {
        console.error('Error loading VIX data:', error);
        document.getElementById('vixLevel').textContent = 'N/A';
    }
}

/**
 * Load active alerts
 */
// Store alerts globally for sorting
let currentAlerts = [];

async function loadActiveAlerts() {
    try {
        const response = await fetch('/api/alerts');
        if (!response.ok) throw new Error('Failed to load alerts');
        
        const data = await response.json();
        currentAlerts = data.alerts || [];
        
        // Load saved sort preference
        const sortBy = localStorage.getItem('alertSortBy') || 'priority-desc';
        if (document.getElementById('alertSortBy')) {
            document.getElementById('alertSortBy').value = sortBy;
        }
        
        renderAlerts();
        
    } catch (error) {
        console.error('Error loading alerts:', error);
    }
}

function sortAlerts() {
    const sortBy = document.getElementById('alertSortBy').value;
    localStorage.setItem('alertSortBy', sortBy);
    renderAlerts();
}

// Make function globally accessible
window.sortAlerts = sortAlerts;

function renderAlerts() {
    const alertsDiv = document.getElementById('activeAlerts');
    
    if (currentAlerts.length === 0) {
        alertsDiv.innerHTML = '<p style="color: #999;">No active alerts</p>';
        return;
    }
    
    // Get sort preference
    const sortBy = document.getElementById('alertSortBy')?.value || localStorage.getItem('alertSortBy') || 'priority-desc';
    
    // Sort alerts
    const sortedAlerts = [...currentAlerts].sort((a, b) => {
        switch (sortBy) {
            case 'priority-desc':
                const priorityOrder = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                return (priorityOrder[b.priority] || 0) - (priorityOrder[a.priority] || 0);
            case 'priority-asc':
                const priorityOrderAsc = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                return (priorityOrderAsc[a.priority] || 0) - (priorityOrderAsc[b.priority] || 0);
            case 'symbol-asc':
                return a.symbol.localeCompare(b.symbol);
            case 'symbol-desc':
                return b.symbol.localeCompare(a.symbol);
            case 'type-asc':
                return a.alert_type.localeCompare(b.alert_type);
            case 'date-desc':
                return new Date(b.created_at) - new Date(a.created_at);
            case 'date-asc':
                return new Date(a.created_at) - new Date(b.created_at);
            default:
                return 0;
        }
    });
    
    // Group by symbol if sorted by symbol
    let html = '';
    if (sortBy.startsWith('symbol-')) {
        let lastSymbol = null;
        sortedAlerts.forEach(alert => {
            if (alert.symbol !== lastSymbol) {
                if (lastSymbol !== null) {
                    html += '<div style="border-bottom: 1px solid var(--border); margin: 10px 0;"></div>';
                }
                lastSymbol = alert.symbol;
            }
            html += renderAlertItem(alert);
        });
    } else {
        html = sortedAlerts.map(alert => renderAlertItem(alert)).join('');
    }
    
    alertsDiv.innerHTML = html;
}

function renderAlertItem(alert) {
    const priorityIcons = {
        'critical': '🚨',
        'high': '⚠️',
        'medium': '🔔',
        'low': 'ℹ️'
    };
    
    const priorityIcon = priorityIcons[alert.priority] || '🔔';
    const date = new Date(alert.created_at).toLocaleDateString();
    
    return `
        <div class="alert-item priority-${alert.priority}">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 1.2em;">${priorityIcon}</span>
                        <strong>${alert.symbol}</strong>
                        <span style="color: #666; font-size: 0.85em;">• ${alert.alert_type}</span>
                        <span style="color: #999; font-size: 0.8em;">• ${date}</span>
                    </div>
                    <div style="color: #666; font-size: 0.9em; margin-top: 5px; margin-left: 28px;">${alert.condition}</div>
                </div>
                <div class="alert-actions" style="margin-left: 10px;">
                    <button class="btn btn-sm btn-danger" onclick="deleteAlert(${alert.id})" title="Delete alert">🗑️</button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Open create alert modal
 */
function openCreateAlertModal() {
    document.getElementById('createAlertModal').classList.add('active');
}

// Make function globally accessible
window.openCreateAlertModal = openCreateAlertModal;

function closeCreateAlertModal() {
    document.getElementById('createAlertModal').classList.remove('active');
    document.getElementById('createAlertForm').reset();
}

// Make function globally accessible
window.closeCreateAlertModal = closeCreateAlertModal;

function updateAlertConditionField() {
    const type = document.getElementById('alertType').value;
    const conditionInput = document.getElementById('alertCondition');
    
    const placeholders = {
        'price': 'price > 150',
        'technical': 'RSI < 30',
        'sentiment': 'Very Bearish',
        'risk': 'D',
        'pnl': 'pnl_pct > 20'
    };
    
    conditionInput.placeholder = placeholders[type] || 'Enter condition';
}

// Make function globally accessible
window.updateAlertConditionField = updateAlertConditionField;

/**
 * Create new alert
 */
async function createAlert(event) {
    event.preventDefault();
    
    const symbol = document.getElementById('alertSymbol').value.toUpperCase();
    const alertType = document.getElementById('alertType').value;
    const condition = document.getElementById('alertCondition').value;
    const priority = document.getElementById('alertPriority').value;
    
    try {
        const response = await fetch('/api/alerts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                symbol,
                alert_type: alertType,
                condition,
                priority
            })
        });
        
        if (!response.ok) throw new Error('Failed to create alert');
        
        alert('Alert created successfully!');
        closeCreateAlertModal();
        loadActiveAlerts();
        
    } catch (error) {
        console.error('Error creating alert:', error);
        alert('Failed to create alert: ' + error.message);
    }
}

// Make function globally accessible
window.createAlert = createAlert;

/**
 * Delete alert
 */
async function deleteAlert(alertId) {
    if (!confirm('Are you sure you want to delete this alert?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/alerts/${alertId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete alert');
        
        loadActiveAlerts();
        
    } catch (error) {
        console.error('Error deleting alert:', error);
        alert('Failed to delete alert');
    }
}

// Make function globally accessible
window.deleteAlert = deleteAlert;

/**
 * Portfolio Value Chart
 */
let portfolioChart = null;
let currentChartPeriod = '1m';

function initPortfolioChart() {
    const buttons = document.querySelectorAll('.period-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentChartPeriod = btn.dataset.period;
            loadPortfolioHistory(currentChartPeriod);
        });
    });
    loadPortfolioHistory(currentChartPeriod);
}

async function loadPortfolioHistory(period) {
    const canvas = document.getElementById('portfolioValueChart');
    if (!canvas) return;
    
    try {
        const res = await fetch(`/api/portfolio/history?period=${period}`);
        const data = await res.json();
        const history = data.history || [];
        
        if (history.length === 0) {
            renderEmptyChart(canvas);
            return;
        }
        
        renderPortfolioChart(canvas, history);
        renderPortfolioMetrics(history);
    } catch (e) {
        console.error('Error loading portfolio history:', e);
        renderEmptyChart(canvas);
    }
}

function renderPortfolioChart(canvas, history) {
    const ctx = canvas.getContext('2d');
    const isDark = document.body.classList.contains('dark-mode');
    
    const labels = history.map(h => {
        const d = new Date(h.timestamp);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    const values = history.map(h => h.total_value);
    const costBasis = history.map(h => h.total_cost_basis);
    
    const isUp = values.length > 1 && values[values.length - 1] >= values[0];
    const lineColor = isUp ? '#10b981' : '#ef4444';
    const fillColor = isUp ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
    
    if (portfolioChart) portfolioChart.destroy();
    
    portfolioChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Portfolio Value',
                    data: values,
                    borderColor: lineColor,
                    backgroundColor: fillColor,
                    fill: true,
                    tension: 0.3,
                    pointRadius: values.length > 60 ? 0 : 2,
                    borderWidth: 2
                },
                {
                    label: 'Cost Basis',
                    data: costBasis,
                    borderColor: isDark ? '#666' : '#ccc',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: isDark ? '#e5e5e5' : '#1f2937', font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2})}`
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: isDark ? '#a0a0a0' : '#6b7280', maxTicksLimit: 12 },
                    grid: { color: isDark ? '#333' : '#e5e7eb' }
                },
                y: {
                    ticks: {
                        color: isDark ? '#a0a0a0' : '#6b7280',
                        callback: v => '$' + v.toLocaleString()
                    },
                    grid: { color: isDark ? '#333' : '#e5e7eb' }
                }
            }
        }
    });
}

function renderEmptyChart(canvas) {
    if (portfolioChart) portfolioChart.destroy();
    const container = document.getElementById('portfolioMetrics');
    if (container) container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">No portfolio history yet. Data will build over time.</p>';
}

function renderPortfolioMetrics(history) {
    const container = document.getElementById('portfolioMetrics');
    if (!container || history.length === 0) return;
    
    const latest = history[history.length - 1];
    const first = history[0];
    const values = history.map(h => h.total_value);
    
    const periodReturn = latest.total_value - first.total_value;
    const periodReturnPct = first.total_value > 0 ? (periodReturn / first.total_value * 100) : 0;
    const highValue = Math.max(...values);
    const lowValue = Math.min(...values);
    const drawdown = highValue > 0 ? ((latest.total_value - highValue) / highValue * 100) : 0;
    const volatility = calcVolatility(values);
    
    const retClass = periodReturn >= 0 ? 'color:#10b981' : 'color:#ef4444';
    const ddClass = drawdown < -5 ? 'color:#ef4444' : 'color:var(--text-primary)';
    
    container.innerHTML = `
        <div class="metric-mini">
            <div class="metric-label">Period Return</div>
            <div class="metric-value" style="${retClass}">${periodReturn >= 0 ? '+' : ''}$${periodReturn.toFixed(2)}</div>
        </div>
        <div class="metric-mini">
            <div class="metric-label">Period Return %</div>
            <div class="metric-value" style="${retClass}">${periodReturnPct >= 0 ? '+' : ''}${periodReturnPct.toFixed(2)}%</div>
        </div>
        <div class="metric-mini">
            <div class="metric-label">Period High</div>
            <div class="metric-value">$${highValue.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
        </div>
        <div class="metric-mini">
            <div class="metric-label">Period Low</div>
            <div class="metric-value">$${lowValue.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
        </div>
        <div class="metric-mini">
            <div class="metric-label">Max Drawdown</div>
            <div class="metric-value" style="${ddClass}">${drawdown.toFixed(2)}%</div>
        </div>
        <div class="metric-mini">
            <div class="metric-label">Volatility</div>
            <div class="metric-value">${volatility.toFixed(2)}%</div>
        </div>
    `;
}

function calcVolatility(values) {
    if (values.length < 2) return 0;
    const returns = [];
    for (let i = 1; i < values.length; i++) {
        if (values[i-1] > 0) returns.push((values[i] - values[i-1]) / values[i-1]);
    }
    if (returns.length === 0) return 0;
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
    return Math.sqrt(variance) * Math.sqrt(252) * 100;
}

/**
 * Refresh all data
 */
function refreshAll() {
    loadPortfolioData();
    loadVixData();
    loadActiveAlerts();
}

// Make function globally accessible
window.refreshAll = refreshAll;

/**
 * Show error message
 */
function showError(message) {
    // Could implement a nice toast notification here
    console.error(message);
}

/**
 * Add Position Modal Functions
 */
function openAddPositionModal() {
    document.getElementById('addPositionModal').classList.add('active');
    // Reset form
    document.getElementById('addPositionForm').reset();
    updateTotalCost();
    
    // Set default purchase date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('purchaseDate').value = today;
    document.getElementById('purchaseDate').max = today;
}

// Make function globally accessible
window.openAddPositionModal = openAddPositionModal;

function closeAddPositionModal() {
    document.getElementById('addPositionModal').classList.remove('active');
    document.getElementById('addPositionForm').reset();
}

// Make function globally accessible
window.closeAddPositionModal = closeAddPositionModal;

function updateTotalCost() {
    const assetType = document.getElementById('positionAssetType').value;
    
    if (assetType === 'option') {
        const quantity = parseFloat(document.getElementById('optionQuantity').value) || 0;
        const premium = parseFloat(document.getElementById('premiumPaid').value) || 0;
        const total = quantity * premium * 100; // Each contract = 100 shares
        
        document.getElementById('totalCost').textContent = `$${total.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        })}`;
    } else {
        const quantity = parseFloat(document.getElementById('positionQuantity').value) || 0;
        const price = parseFloat(document.getElementById('positionPrice').value) || 0;
        const total = quantity * price;
        
        document.getElementById('totalCost').textContent = `$${total.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        })}`;
    }
}

function toggleOptionsFields() {
    const assetType = document.getElementById('positionAssetType').value;
    const stockFields = document.getElementById('stockFields');
    const optionsFields = document.getElementById('optionsFields');
    
    if (assetType === 'option') {
        stockFields.style.display = 'none';
        optionsFields.style.display = 'block';
        // Make option fields required
        document.getElementById('strikePrice').required = true;
        document.getElementById('expirationDate').required = true;
        document.getElementById('optionQuantity').required = true;
        document.getElementById('premiumPaid').required = true;
        // Make stock fields optional
        document.getElementById('positionQuantity').required = false;
        document.getElementById('positionPrice').required = false;
    } else {
        stockFields.style.display = 'block';
        optionsFields.style.display = 'none';
        // Make stock fields required
        document.getElementById('positionQuantity').required = true;
        document.getElementById('positionPrice').required = true;
        // Make option fields optional
        document.getElementById('strikePrice').required = false;
        document.getElementById('expirationDate').required = false;
        document.getElementById('optionQuantity').required = false;
        document.getElementById('premiumPaid').required = false;
    }
    
    updateTotalCost();
}

// Make function globally accessible
window.toggleOptionsFields = toggleOptionsFields;

// Update total cost when inputs change
document.addEventListener('DOMContentLoaded', () => {
    const quantityInput = document.getElementById('positionQuantity');
    const priceInput = document.getElementById('positionPrice');
    const optionQuantityInput = document.getElementById('optionQuantity');
    const premiumInput = document.getElementById('premiumPaid');
    
    if (quantityInput && priceInput) {
        quantityInput.addEventListener('input', updateTotalCost);
        priceInput.addEventListener('input', updateTotalCost);
    }
    
    if (optionQuantityInput && premiumInput) {
        optionQuantityInput.addEventListener('input', updateTotalCost);
        premiumInput.addEventListener('input', updateTotalCost);
    }
});

/**
 * Add new position to portfolio
 */
async function addPosition(event) {
    event.preventDefault();
    
    const symbol = document.getElementById('positionSymbol').value.toUpperCase();
    const assetType = document.getElementById('positionAssetType').value;
    
    try {
        let response;
        
        if (assetType === 'option') {
            // Add options position
            const optionType = document.getElementById('optionType').value;
            const strikePrice = parseFloat(document.getElementById('strikePrice').value);
            const expirationDate = document.getElementById('expirationDate').value;
            const quantity = parseInt(document.getElementById('optionQuantity').value);
            const premiumPaid = parseFloat(document.getElementById('premiumPaid').value);
            
            if (!symbol || !strikePrice || !expirationDate || quantity <= 0 || premiumPaid <= 0) {
                alert('Please fill in all fields with valid values');
                return;
            }
            
            response = await fetch('/api/options', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    symbol,
                    option_type: optionType,
                    strike_price: strikePrice,
                    expiration_date: expirationDate,
                    quantity,
                    premium_paid: premiumPaid
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to add option position');
            }
            
            showToast(`✓ Added ${quantity} ${optionType.toUpperCase()} contracts of ${symbol} @ $${strikePrice}`, 'success');
            
        } else {
            // Add stock/ETF/crypto position
            const quantity = parseFloat(document.getElementById('positionQuantity').value);
            const price = parseFloat(document.getElementById('positionPrice').value);
            const purchaseDate = document.getElementById('purchaseDate').value;
            
            if (!symbol || quantity <= 0 || price <= 0) {
                alert('Please fill in all fields with valid values');
                return;
            }
            
            response = await fetch('/api/portfolio', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    symbol,
                    asset_type: assetType,
                    quantity,
                    price,
                    purchase_date: purchaseDate || null,
                    account_id: document.getElementById('positionAccount')?.value || null
                })
            });
            
            if (!response.ok) {
                const errData = await response.json();
                const msg = errData.error || 'Failed to add position';
                const tb = errData.traceback ? '\n\nTraceback:\n' + errData.traceback : '';
                console.error('Server error details:', msg, tb);
                throw new Error(msg);
            }
            
            showToast(`✓ Added ${quantity} shares of ${symbol} at $${price}`, 'success');
        }
        
        // Close modal and refresh
        closeAddPositionModal();
        loadPortfolioData();
        
    } catch (error) {
        console.error('Error adding position:', error);
        alert('Failed to add position: ' + error.message);
    }
}

// Make function globally accessible
window.addPosition = addPosition;

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        z-index: 10001;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        animation: slideIn 0.3s ease-out;
    `;
    
    const colors = {
        success: '#4CAF50',
        error: '#f44336',
        info: '#2196F3',
        warning: '#ff9800'
    };
    
    toast.style.background = colors[type] || colors.info;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Delete a position completely
 */
async function deletePosition(holdingId, type = 'stock') {
    if (!confirm('Are you sure you want to delete this position? This cannot be undone.')) {
        return;
    }
    
    try {
        const endpoint = type === 'stock' ? `/api/portfolio/holding/${holdingId}` : `/api/options/${holdingId}`;
        const response = await fetch(endpoint, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Position deleted successfully', 'success');
            closeHoldingModal();
            await loadPortfolioData();
        } else {
            throw new Error('Failed to delete position');
        }
    } catch (error) {
        console.error('Error deleting position:', error);
        showToast('Failed to delete position', 'error');
    }
}

/**
 * Open modal to sell/edit a position
 */
async function openSellPositionModal(holdingId, type = 'stock') {
    closeHoldingModal();
    
    // Fetch holding data to get current values
    let holdingData = null;
    try {
        const response = await fetch(`/api/portfolio/holding/${holdingId}?type=${type}`);
        if (response.ok) {
            holdingData = await response.json();
        }
    } catch (error) {
        console.error('Error fetching holding data:', error);
    }
    
    const modal = document.createElement('div');
    modal.id = 'sellPositionModal';
    modal.className = 'modal active';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Sell/Edit Position</h2>
                <span class="close-modal" onclick="document.getElementById('sellPositionModal').remove()">&times;</span>
            </div>
            <form id="sellPositionForm" onsubmit="processSellPosition(event, ${holdingId}, '${type}')">
                <div class="form-group">
                    <label>Action</label>
                    <select id="sellAction" required onchange="toggleSellFields()">
                        <option value="partial">Sell Partial Quantity</option>
                        <option value="full">Sell All</option>
                        <option value="edit">Edit Cost Basis</option>
                    </select>
                </div>
                
                <div class="form-group" id="sellQuantityGroup">
                    <label>Quantity to Sell</label>
                    <input type="number" id="sellQuantity" min="1" step="any" required>
                </div>
                
                <div class="form-group" id="sellPriceGroup">
                    <label>Sell Price</label>
                    <input type="number" id="sellPrice" step="0.01" min="0" required>
                </div>
                
                <div class="form-group" id="editCostGroup" style="display: none;">
                    <label>New Cost Basis</label>
                    <input type="number" id="newCostBasis" step="0.0001" min="0" value="${holdingData ? holdingData.cost_basis : ''}">
                </div>
                
                <div class="form-group" id="editDateGroup" style="display: none;">
                    <label>Purchase Date</label>
                    <input type="date" id="editPurchaseDate" value="${holdingData && holdingData.purchase_date ? new Date(holdingData.purchase_date).toISOString().split('T')[0] : ''}">
                </div>
                
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="button" onclick="document.getElementById('sellPositionModal').remove()" class="btn btn-secondary" style="flex: 1;">Cancel</button>
                    <button type="submit" class="btn btn-primary" style="flex: 1;">Submit</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
}

/**
 * Toggle sell form fields based on action
 */
function toggleSellFields() {
    const action = document.getElementById('sellAction').value;
    const quantityGroup = document.getElementById('sellQuantityGroup');
    const priceGroup = document.getElementById('sellPriceGroup');
    const editGroup = document.getElementById('editCostGroup');
    const dateGroup = document.getElementById('editDateGroup');
    
    if (action === 'full') {
        quantityGroup.style.display = 'none';
        priceGroup.style.display = 'block';
        editGroup.style.display = 'none';
        dateGroup.style.display = 'none';
        document.getElementById('sellQuantity').required = false;
        document.getElementById('sellPrice').required = true;
    } else if (action === 'partial') {
        quantityGroup.style.display = 'block';
        priceGroup.style.display = 'block';
        editGroup.style.display = 'none';
        dateGroup.style.display = 'none';
        document.getElementById('sellQuantity').required = true;
        document.getElementById('sellPrice').required = true;
    } else if (action === 'edit') {
        quantityGroup.style.display = 'none';
        priceGroup.style.display = 'none';
        editGroup.style.display = 'block';
        dateGroup.style.display = 'block';
        document.getElementById('sellQuantity').required = false;
        document.getElementById('sellPrice').required = false;
    }
}

/**
 * Process sell/edit transaction
 */
async function processSellPosition(event, holdingId, type = 'stock') {
    event.preventDefault();
    
    const action = document.getElementById('sellAction').value;
    
    try {
        if (action === 'edit') {
            // Edit cost basis and purchase date
            const newCostBasis = parseFloat(document.getElementById('newCostBasis').value);
            const purchaseDate = document.getElementById('editPurchaseDate').value;
            const endpoint = type === 'stock' ? `/api/portfolio/holding/${holdingId}` : `/api/options/${holdingId}`;
            
            const body = { cost_basis: newCostBasis };
            if (purchaseDate) {
                body.purchase_date = purchaseDate;
            }
            
            const response = await fetch(endpoint, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            
            if (response.ok) {
                showToast('Position updated successfully', 'success');
            } else {
                throw new Error('Failed to update position');
            }
        } else {
            // Process sell transaction
            const quantity = action === 'full' ? null : parseFloat(document.getElementById('sellQuantity').value);
            const sellPrice = parseFloat(document.getElementById('sellPrice').value);
            
            const response = await fetch('/api/portfolio/transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    holding_id: holdingId,
                    transaction_type: 'sell',
                    quantity: quantity,
                    price: sellPrice,
                    sell_all: action === 'full'
                })
            });
            
            if (response.ok) {
                showToast('Transaction recorded successfully', 'success');
            } else {
                throw new Error('Failed to record transaction');
            }
        }
        
        document.getElementById('sellPositionModal').remove();
        await loadPortfolioData();
        
    } catch (error) {
        console.error('Error processing transaction:', error);
        showToast('Failed to process transaction', 'error');
    }
}

// ===========================
// PORTFOLIO ACCOUNT MANAGEMENT
// ===========================

let portfolioAccounts = [];

const STYLE_COLORS = {
    aggressive: { bg: 'rgba(239,68,68,0.15)', color: '#ef4444', label: '🔥 Aggressive' },
    moderate: { bg: 'rgba(59,130,246,0.15)', color: '#3b82f6', label: '⚖️ Moderate' },
    conservative: { bg: 'rgba(16,185,129,0.15)', color: '#10b981', label: '🛡️ Conservative' },
    balanced: { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', label: '🎯 Balanced' }
};

async function loadAccounts() {
    try {
        const res = await fetch('/api/portfolio/accounts');
        if (!res.ok) return;
        const data = await res.json();
        portfolioAccounts = data.accounts || [];
        
        // Populate account selector
        const selector = document.getElementById('accountSelector');
        if (!selector) return;
        
        const currentVal = selector.value;
        selector.innerHTML = '<option value="all">All Accounts</option>';
        
        portfolioAccounts.forEach(acc => {
            const style = STYLE_COLORS[acc.investment_style] || STYLE_COLORS.moderate;
            const opt = document.createElement('option');
            opt.value = acc.id;
            opt.textContent = `${acc.name} (${style.label})`;
            selector.appendChild(opt);
        });
        
        if (data.unassigned_count > 0) {
            const opt = document.createElement('option');
            opt.value = 'unassigned';
            opt.textContent = `Unassigned (${data.unassigned_count})`;
            selector.appendChild(opt);
        }
        
        // Restore previous selection
        if (currentVal) selector.value = currentVal;
        
        // Update account badge
        updateAccountStyleBadge();
        
        // Populate add-position account dropdown
        const posAcct = document.getElementById('positionAccount');
        if (posAcct) {
            posAcct.innerHTML = '<option value="">No Account (Unassigned)</option>';
            portfolioAccounts.forEach(acc => {
                const opt = document.createElement('option');
                opt.value = acc.id;
                opt.textContent = acc.name;
                posAcct.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Error loading accounts:', e);
    }
}

function switchAccount() {
    updateAccountStyleBadge();
    loadPortfolioData();
}

function updateAccountStyleBadge() {
    const badge = document.getElementById('accountStyleBadge');
    const selector = document.getElementById('accountSelector');
    if (!badge || !selector) return;
    
    const val = selector.value;
    const account = portfolioAccounts.find(a => a.id == val);
    
    if (account) {
        const style = STYLE_COLORS[account.investment_style] || STYLE_COLORS.moderate;
        badge.textContent = style.label;
        badge.style.background = style.bg;
        badge.style.color = style.color;
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

function openCreateAccountModal() {
    const existing = document.getElementById('createAccountModal');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.id = 'createAccountModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10000;';
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    
    modal.innerHTML = `
        <div style="background:var(--modal-bg);border-radius:12px;padding:30px;max-width:500px;width:90%;color:var(--text-primary);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                <h2 style="margin:0;">📁 Create Account</h2>
                <button onclick="document.getElementById('createAccountModal').remove()" style="background:none;border:none;font-size:24px;cursor:pointer;color:var(--text-secondary);">&times;</button>
            </div>
            <div class="form-group">
                <label>Account Name</label>
                <input type="text" id="newAccountName" placeholder="e.g., Roth IRA, Brokerage, 401k" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-primary);color:var(--text-primary);">
            </div>
            <div class="form-group">
                <label>Investment Style</label>
                <select id="newAccountStyle" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-primary);color:var(--text-primary);">
                    <option value="aggressive">🔥 Aggressive — High risk, high reward</option>
                    <option value="moderate" selected>⚖️ Moderate — Balanced approach</option>
                    <option value="conservative">🛡️ Conservative — Capital preservation</option>
                    <option value="balanced">🎯 Balanced — Diversified mix</option>
                </select>
            </div>
            <div class="form-group">
                <label>Description (optional)</label>
                <input type="text" id="newAccountDesc" placeholder="Brief description..." style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-primary);color:var(--text-primary);">
            </div>
            <button onclick="createAccount()" style="width:100%;padding:12px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;">Create Account</button>
        </div>
    `;
    
    document.body.appendChild(modal);
    document.getElementById('newAccountName').focus();
}

async function createAccount() {
    const name = document.getElementById('newAccountName').value.trim();
    const style = document.getElementById('newAccountStyle').value;
    const desc = document.getElementById('newAccountDesc').value.trim();
    
    if (!name) { showToast('Account name is required', 'error'); return; }
    
    try {
        const res = await fetch('/api/portfolio/accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, investment_style: style, description: desc })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to create account');
        
        document.getElementById('createAccountModal')?.remove();
        showToast(`Account "${name}" created!`, 'success');
        await loadAccounts();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function openAccountManager() {
    const existing = document.getElementById('accountManagerModal');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.id = 'accountManagerModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10000;';
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    
    const accountCards = portfolioAccounts.length === 0
        ? '<p style="color:var(--text-secondary);text-align:center;padding:20px;">No accounts yet. Create one to organize your holdings.</p>'
        : portfolioAccounts.map(acc => {
            const style = STYLE_COLORS[acc.investment_style] || STYLE_COLORS.moderate;
            return `
                <div style="background:var(--bg-tertiary);border-radius:10px;padding:16px;margin-bottom:12px;border:1px solid var(--border);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div style="font-weight:600;font-size:1.1em;color:var(--text-primary);">${acc.name}</div>
                        <span style="padding:4px 10px;border-radius:12px;font-size:0.8em;font-weight:600;background:${style.bg};color:${style.color};">${style.label}</span>
                    </div>
                    ${acc.description ? `<div style="color:var(--text-secondary);font-size:0.9em;margin-bottom:8px;">${acc.description}</div>` : ''}
                    <div style="display:flex;gap:16px;font-size:0.85em;color:var(--text-secondary);margin-bottom:12px;">
                        <span>📊 ${acc.holdings_count} holdings</span>
                        <span>💰 $${(acc.total_value || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                        <span style="color:${(acc.gain_loss||0) >= 0 ? 'var(--success)' : 'var(--danger)'};">P&L: $${(acc.gain_loss || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button onclick="editAccountStyle(${acc.id}, '${acc.investment_style}')" style="flex:1;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;cursor:pointer;color:var(--text-primary);font-size:0.85em;">Edit Style</button>
                        <button onclick="deleteAccount(${acc.id}, '${acc.name}')" style="padding:8px 14px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:6px;cursor:pointer;color:#ef4444;font-size:0.85em;">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
    
    modal.innerHTML = `
        <div style="background:var(--modal-bg);border-radius:12px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;color:var(--text-primary);">
            <div style="padding:24px 24px 0;display:flex;justify-content:space-between;align-items:center;">
                <h2 style="margin:0;">📁 Manage Accounts</h2>
                <button onclick="document.getElementById('accountManagerModal').remove()" style="background:none;border:none;font-size:24px;cursor:pointer;color:var(--text-secondary);">&times;</button>
            </div>
            <div style="padding:20px 24px 24px;">
                ${accountCards}
                <button onclick="document.getElementById('accountManagerModal').remove();openCreateAccountModal()" style="width:100%;padding:12px;background:transparent;border:2px dashed var(--border);border-radius:8px;color:var(--text-secondary);font-weight:600;cursor:pointer;margin-top:8px;">+ Create New Account</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

async function editAccountStyle(accountId, currentStyle) {
    const existing = document.getElementById('editStyleModal');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.id = 'editStyleModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:10001;';
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    
    const styles = ['aggressive', 'moderate', 'conservative', 'balanced'];
    
    modal.innerHTML = `
        <div style="background:var(--modal-bg);border-radius:12px;padding:30px;max-width:400px;width:90%;color:var(--text-primary);">
            <h3 style="margin:0 0 16px;">Change Investment Style</h3>
            <div style="display:flex;flex-direction:column;gap:8px;">
                ${styles.map(s => {
                    const sc = STYLE_COLORS[s];
                    return `<button onclick="saveAccountStyle(${accountId},'${s}')" style="padding:14px;background:${s === currentStyle ? sc.bg : 'var(--bg-tertiary)'};border:2px solid ${s === currentStyle ? sc.color : 'var(--border)'};border-radius:8px;cursor:pointer;color:var(--text-primary);font-weight:600;text-align:left;">${sc.label}${s === currentStyle ? ' ✓' : ''}</button>`;
                }).join('')}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

async function saveAccountStyle(accountId, style) {
    try {
        const res = await fetch(`/api/portfolio/accounts/${accountId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ investment_style: style })
        });
        if (!res.ok) throw new Error('Failed to update');
        
        document.getElementById('editStyleModal')?.remove();
        document.getElementById('accountManagerModal')?.remove();
        showToast('Investment style updated', 'success');
        await loadAccounts();
    } catch (e) {
        showToast('Failed to update style', 'error');
    }
}

async function deleteAccount(accountId, name) {
    if (!confirm(`Delete account "${name}"? Holdings will be moved to unassigned.`)) return;
    
    try {
        const res = await fetch(`/api/portfolio/accounts/${accountId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete');
        
        document.getElementById('accountManagerModal')?.remove();
        showToast(`Account "${name}" deleted`, 'success');
        
        const selector = document.getElementById('accountSelector');
        if (selector && selector.value == accountId) selector.value = 'all';
        
        await loadAccounts();
        await loadPortfolioData();
    } catch (e) {
        showToast('Failed to delete account', 'error');
    }
}

// Expose account functions globally
window.openCreateAccountModal = openCreateAccountModal;
window.openAccountManager = openAccountManager;
window.switchAccount = switchAccount;
window.editAccountStyle = editAccountStyle;
window.saveAccountStyle = saveAccountStyle;
window.deleteAccount = deleteAccount;

