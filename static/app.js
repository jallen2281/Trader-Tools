/**
 * Main Application JavaScript
 * Coordinates watchlist, alerts, comparison, and analysis features
 */

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeDarkMode();
    initializeWatchlist();
    initializeAlerts();
    initializeComparison();
    initializeTechnicalChart();
    initializeAnalysis();
    initializeModals();
    initializeHeaderButtons();
    initializePortfolioWidget();
});

// =======================
// DARK MODE FUNCTIONALITY
// =======================

function initializeDarkMode() {
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
    }
}

function toggleDarkMode(enabled) {
    if (enabled) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
}

// =======================
// WATCHLIST FUNCTIONALITY
// =======================

function initializeWatchlist() {
    const watchlistItems = document.getElementById('watchlistItems');
    const addBtn = document.getElementById('addToWatchlist');
    const input = document.getElementById('watchlistSymbolInput');
    const refreshBtn = document.getElementById('refreshWatchlist');

    // Load and display watchlist
    renderWatchlist();

    // Add symbol
    addBtn.addEventListener('click', () => {
        const symbol = input.value.trim();
        if (symbol && watchlistManager.add(symbol)) {
            input.value = '';
            renderWatchlist();
        }
    });

    // Enter key
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addBtn.click();
        }
    });

    // Refresh prices
    refreshBtn.addEventListener('click', () => {
        refreshWatchlist();
    });

    // Listen for changes
    window.addEventListener('watchlistchange', () => {
        renderWatchlist();
    });

    // Auto-refresh every 60 seconds
    setInterval(refreshWatchlist, 60000);
}

async function renderWatchlist() {
    const container = document.getElementById('watchlistItems');
    const currentWatchlist = watchlistManager.getCurrentWatchlist();
    const allNames = watchlistManager.getAllWatchlistNames();
    
    // Render watchlist selector
    const selectorHTML = `
        <div style="margin-bottom: 15px;">
            <select id="watchlistSelector" onchange="switchWatchlist(this.value)" style="width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); cursor: pointer;">
                <option value="portfolio" ${currentWatchlist === 'portfolio' ? 'selected' : ''}>💼 My Portfolio</option>
                ${allNames.map(name => `
                    <option value="${name}" ${currentWatchlist === name ? 'selected' : ''}>
                        ${name === 'default' ? '⭐ Default' : '📊 ' + name}
                    </option>
                `).join('')}
                <option value="__new__">+ New Watchlist</option>
            </select>
            ${currentWatchlist !== 'default' && currentWatchlist !== 'portfolio' ? `
                <div style="display: flex; gap: 5px; margin-top: 8px;">
                    <button onclick="renameCurrentWatchlist()" class="btn-icon" title="Rename" style="flex: 1; padding: 6px; font-size: 0.85em;">Rename</button>
                    <button onclick="deleteCurrentWatchlist()" class="btn-icon" title="Delete" style="flex: 1; padding: 6px; font-size: 0.85em; color: var(--danger);">Delete</button>
                </div>
            ` : ''}
        </div>
    `;
    
    container.innerHTML = '<div class="loading-small">Loading...</div>';
    
    let symbols = [];
    let prices = {};
    let recommendations = {};
    
    if (currentWatchlist === 'portfolio') {
        // Fetch portfolio holdings
        const holdings = await watchlistManager.fetchPortfolioHoldings();
        symbols = holdings.map(h => h.symbol);
        
        // Fetch prices for portfolio symbols
        if (symbols.length > 0) {
            prices = await watchlistManager.fetchPrices(symbols);
            console.log('Portfolio prices fetched:', prices);
            
            // Fetch recommendations for each holding (Phase 4 feature)
            for (const holding of holdings) {
                try {
                    const response = await fetch(`/api/portfolio/holding/${holding.id}`, {
                        headers: {
                            'X-API-Key': localStorage.getItem('apiKey') || ''
                        }
                    });
                    if (response.ok) {
                        const data = await response.json();
                        console.log(`Recommendation for ${holding.symbol}:`, data.recommendation);
                        // Recommendation is an object with action, reason, confidence
                        recommendations[holding.symbol] = data.recommendation?.action || 'HOLD';
                    } else if (response.status === 503) {
                        // Phase 4 not enabled, skip recommendations
                        console.log('Phase 4 not enabled, skipping recommendations');
                        break;
                    } else {
                        console.warn(`Failed to fetch recommendation for ${holding.symbol}:`, response.status);
                        recommendations[holding.symbol] = 'HOLD';
                    }
                } catch (e) {
                    console.error(`Error fetching recommendation for ${holding.symbol}:`, e);
                    recommendations[holding.symbol] = 'HOLD';
                }
            }
        }
    } else {
        symbols = watchlistManager.getAll();
        if (symbols.length > 0) {
            prices = await watchlistManager.fetchPrices();
        }
    }
    
    if (symbols.length === 0) {
        container.innerHTML = selectorHTML + '<div class="empty-state">No symbols in this watchlist</div>';
        return;
    }

    console.log('Watchlist prices:', prices);
    console.log('Watchlist recommendations:', recommendations);

    const itemsHTML = symbols.map(symbol => {
        const data = prices[symbol] || {};
        const change = data.return_pct || 0;
        const price = data.current_price || '--';
        const changeClass = change >= 0 ? 'positive' : 'negative';
        const recommendation = recommendations[symbol];
        const recBadge = recommendation ? getRecommendationBadge(recommendation) : '';
        
        return `
            <div class="watchlist-item">
                <div style="flex: 1;">
                    <div class="watchlist-symbol" onclick="analyzeSymbol('${symbol}')">
                        ${symbol}
                    </div>
                    ${recBadge}
                </div>
                <div style="text-align: right;">
                    <div class="watchlist-price">$${price}</div>
                    <div class="watchlist-change ${changeClass}">
                        ${change >= 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%
                    </div>
                </div>
                ${currentWatchlist !== 'portfolio' ? `
                    <button class="watchlist-remove" onclick="removeFromWatchlist('${symbol}')" title="Remove">×</button>
                ` : ''}
            </div>
        `;
    }).join('');
    
    container.innerHTML = selectorHTML + itemsHTML;
}

function getRecommendationBadge(rec) {
    if (!rec || typeof rec !== 'string') return '';
    
    const badges = {
        'BUY MORE': '<span style="background: rgba(16, 185, 129, 0.2); color: var(--success); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🟢 BUY MORE</span>',
        'ADD': '<span style="background: rgba(16, 185, 129, 0.2); color: var(--success); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🟢 ADD</span>',
        'HOLD': '<span style="background: rgba(59, 130, 246, 0.2); color: var(--info); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🔵 HOLD</span>',
        'TRIM': '<span style="background: rgba(251, 191, 36, 0.2); color: var(--warning); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🟡 TRIM</span>',
        'REVIEW': '<span style="background: rgba(251, 191, 36, 0.2); color: var(--warning); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🟡 REVIEW</span>',
        'SELL': '<span style="background: rgba(239, 68, 68, 0.2); color: var(--danger); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🔴 SELL</span>',
        'CONSIDER_SELLING': '<span style="background: rgba(239, 68, 68, 0.2); color: var(--danger); padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; display: inline-block; margin-top: 4px;">🔴 CONSIDER SELLING</span>'
    };
    return badges[rec.toUpperCase()] || '';
}

function switchWatchlist(name) {
    if (name === '__new__') {
        const newName = prompt('Enter new watchlist name:');
        if (newName && watchlistManager.createWatchlist(newName)) {
            watchlistManager.setCurrentWatchlist(newName);
            renderWatchlist();
        } else {
            renderWatchlist(); // Reset selector
        }
    } else {
        watchlistManager.setCurrentWatchlist(name);
        renderWatchlist();
    }
}

function renameCurrentWatchlist() {
    const current = watchlistManager.getCurrentWatchlist();
    const newName = prompt(`Rename "${current}" to:`, current);
    if (newName && watchlistManager.renameWatchlist(current, newName)) {
        renderWatchlist();
    }
}

function deleteCurrentWatchlist() {
    const current = watchlistManager.getCurrentWatchlist();
    if (confirm(`Delete watchlist "${current}"?`)) {
        if (watchlistManager.deleteWatchlist(current)) {
            renderWatchlist();
        }
    }
}

// Make functions globally available
window.switchWatchlist = switchWatchlist;
window.renameCurrentWatchlist = renameCurrentWatchlist;
window.deleteCurrentWatchlist = deleteCurrentWatchlist;

async function refreshWatchlist() {
    await renderWatchlist();
}

function removeFromWatchlist(symbol) {
    watchlistManager.remove(symbol);
    renderWatchlist();
}

function analyzeSymbol(symbol) {
    document.getElementById('symbol').value = symbol;
    document.getElementById('analyzeForm').dispatchEvent(new Event('submit'));
}

// =======================
// ALERTS FUNCTIONALITY
// =======================

function initializeAlerts() {
    const manageBtn = document.getElementById('manageAlerts');
    const createBtn = document.getElementById('createAlert');

    manageBtn.addEventListener('click', () => {
        openAlertsModal();
    });

    createBtn.addEventListener('click', () => {
        createNewAlert();
    });

    // Update alert count
    window.addEventListener('alertschange', () => {
        updateAlertCount();
        renderAlertsList();
    });

    updateAlertCount();
}

function updateAlertCount() {
    const count = alertsManager.getActive().length;
    document.getElementById('alertCount').textContent = count;
}

function openAlertsModal() {
    document.getElementById('alertsModal').style.display = 'flex';
    renderAlertsList();
}

function createNewAlert() {
    const symbol = document.getElementById('alertSymbol').value.trim().toUpperCase();
    const type = document.getElementById('alertType').value;
    const price = parseFloat(document.getElementById('alertPrice').value);
    const notes = document.getElementById('alertNotes').value.trim();

    if (!symbol || !price || isNaN(price)) {
        alert('Please enter valid symbol and price');
        return;
    }

    alertsManager.add(symbol, type, price, notes);
    
    // Clear form
    document.getElementById('alertSymbol').value = '';
    document.getElementById('alertPrice').value = '';
    document.getElementById('alertNotes').value = '';

    // Start monitoring if not already
    if (alertsManager.getActive().length > 0 && !alertsManager.checkInterval) {
        alertsManager.startMonitoring(1);
    }

    renderAlertsList();
}

function renderAlertsList() {
    const container = document.getElementById('alertsList');
    const alerts = alertsManager.getAll();

    if (alerts.length === 0) {
        container.innerHTML = '<div class="empty-state">No alerts set</div>';
        return;
    }

    container.innerHTML = alerts.map(alert => {
        const statusClass = alert.triggered ? 'triggered' : 'active';
        const statusText = alert.triggered ? 'TRIGGERED' : 'ACTIVE';
        const typeIcon = alert.type === 'high' ? '📈' : '📉';

        return `
            <div class="alert-item ${statusClass}">
                <div class="alert-info">
                    <div class="alert-symbol">${typeIcon} ${alert.symbol}</div>
                    <div class="alert-details">
                        ${alert.type === 'high' ? 'Above' : 'Below'} $${alert.price.toFixed(2)}
                        ${alert.notes ? `<br><small>${alert.notes}</small>` : ''}
                    </div>
                </div>
                <div class="alert-status">
                    <span class="alert-badge ${statusClass}">${statusText}</span>
                    <button class="btn-icon" onclick="deleteAlert(${alert.id})">🗑️</button>
                </div>
            </div>
        `;
    }).join('');
}

function deleteAlert(alertId) {
    alertsManager.remove(alertId);
    renderAlertsList();
}

// =======================
// COMPARISON FUNCTIONALITY
// =======================

function initializeComparison() {
    const openBtn = document.getElementById('openComparison');
    const addBtn = document.getElementById('addComparisonSymbol');
    const generateBtn = document.getElementById('generateComparison');
    const input = document.getElementById('comparisonSymbolInput');

    openBtn.addEventListener('click', () => {
        openComparisonModal();
    });

    addBtn.addEventListener('click', () => {
        const symbol = input.value.trim();
        if (symbol && comparisonTool.addSymbol(symbol)) {
            input.value = '';
            renderComparisonSymbols();
        }
    });

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addBtn.click();
        }
    });

    generateBtn.addEventListener('click', async () => {
        await generateComparisonChart();
    });

    window.addEventListener('comparisonchange', () => {
        renderComparisonSymbols();
    });
}

function openComparisonModal() {
    document.getElementById('comparisonModal').style.display = 'flex';
    renderComparisonSymbols();
}

function renderComparisonSymbols() {
    const container = document.getElementById('comparisonSymbols');
    const symbols = comparisonTool.getSymbols();

    if (symbols.length === 0) {
        container.innerHTML = '<div class="empty-state">Add symbols to compare</div>';
        return;
    }

    container.innerHTML = symbols.map(symbol => `
        <div class="symbol-chip">
            ${symbol}
            <button onclick="removeComparisonSymbol('${symbol}')">×</button>
        </div>
    `).join('');
}

function removeComparisonSymbol(symbol) {
    comparisonTool.removeSymbol(symbol);
    renderComparisonSymbols();
}

async function generateComparisonChart() {
    const container = document.getElementById('comparisonChart');
    const tableContainer = document.getElementById('comparisonTable');
    const period = document.getElementById('comparisonPeriod').value;
    const normalize = document.getElementById('normalizeChart').checked;

    container.innerHTML = '<div class="loading">Generating comparison chart...</div>';
    tableContainer.innerHTML = '';

    try {
        const data = await comparisonTool.generateChart(period, normalize);
        
        if (data.chart) {
            container.innerHTML = `<img src="${data.chart}" alt="Comparison Chart" style="width: 100%;" />`;
        }

        // Render comparison table
        const symbols = data.symbols || {};
        const rows = Object.entries(symbols).map(([symbol, info]) => {
            const changeClass = info.return_pct >= 0 ? 'positive' : 'negative';
            return `
                <tr>
                    <td><strong>${symbol}</strong></td>
                    <td>$${info.current_price}</td>
                    <td class="${changeClass}">${info.return_pct >= 0 ? '▲' : '▼'} ${info.return_pct}%</td>
                    <td>${info.volatility}%</td>
                    <td>$${info.high}</td>
                    <td>$${info.low}</td>
                </tr>
            `;
        }).join('');

        tableContainer.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Price</th>
                        <th>Return</th>
                        <th>Volatility</th>
                        <th>High</th>
                        <th>Low</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        `;

    } catch (e) {
        container.innerHTML = `<div class="error">Error: ${e.message}</div>`;
    }
}

// =======================
// ANALYSIS FUNCTIONALITY
// =======================

function initializeAnalysis() {
    const form = document.getElementById('analyzeForm');
    const addAlertBtn = document.getElementById('addAlertBtn');
    const addWatchlistBtn = document.getElementById('addToWatchlistBtn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await analyzeStock();
    });

    addAlertBtn.addEventListener('click', () => {
        const symbol = document.getElementById('symbol').value.trim();
        if (symbol) {
            document.getElementById('alertSymbol').value = symbol.toUpperCase();
            openAlertsModal();
        }
    });

    addWatchlistBtn.addEventListener('click', () => {
        const symbol = document.getElementById('symbol').value.trim();
        if (symbol && watchlistManager.add(symbol.toUpperCase())) {
            alert(`Added ${symbol.toUpperCase()} to watchlist`);
            renderWatchlist();
        }
    });
}

async function analyzeStock() {
    const loading = document.getElementById('loading');
    const error = document.getElementById('error');
    const resultsGrid = document.getElementById('resultsGrid');

    const formData = {
        symbol: document.getElementById('symbol').value.trim().toUpperCase(),
        period: document.getElementById('period').value,
        chart_type: document.getElementById('chartType').value
    };

    loading.style.display = 'block';
    error.style.display = 'none';
    resultsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        const data = await response.json();
        displayResults(data);

    } catch (e) {
        error.textContent = `Error: ${e.message}`;
        error.style.display = 'block';
    } finally {
        loading.style.display = 'none';
    }
}

function displayResults(data) {
    const resultsGrid = document.getElementById('resultsGrid');
    
    const changeClass = data.price_change >= 0 ? 'positive' : 'negative';
    const changeIcon = data.price_change >= 0 ? '▲' : '▼';

    resultsGrid.innerHTML = `
        <div class="result-card">
            <h3>${data.symbol} - ${data.company_info?.name || data.symbol}</h3>
            <div class="price-display">
                <div class="current-price">$${data.current_price}</div>
                <div class="price-change ${changeClass}">
                    ${changeIcon} $${Math.abs(data.price_change).toFixed(2)} (${data.price_change_pct}%)
                </div>
            </div>
            <div class="indicators-grid">
                <div class="indicator">
                    <span class="label">RSI:</span>
                    <span class="value">${data.indicators?.RSI || 'N/A'}</span>
                </div>
                <div class="indicator">
                    <span class="label">MACD:</span>
                    <span class="value">${data.indicators?.MACD || 'N/A'}</span>
                </div>
                <div class="indicator">
                    <span class="label">Volume:</span>
                    <span class="value">${(data.volume || 0).toLocaleString()}</span>
                </div>
                <div class="indicator">
                    <span class="label">Trend:</span>
                    <span class="value">${data.trend || 'N/A'}</span>
                </div>
            </div>
        </div>

        ${data.chart ? `
            <div class="result-card chart-card">
                <img src="${data.chart}" alt="${data.symbol} Chart" style="width: 100%;" />
            </div>
        ` : ''}

        ${data.llm_analysis ? `
            <div class="result-card analysis-card">
                <h3>🤖 AI Analysis</h3>
                <div class="analysis-text">${data.llm_analysis}</div>
            </div>
        ` : ''}

        ${data.ml_prediction ? `
            <div class="result-card ml-prediction-card">
                <h3>🔮 ML Price Prediction</h3>
                <div class="ml-prediction-content">
                    <div class="prediction-main">
                        <div class="prediction-direction ${data.ml_prediction.predicted_direction}">
                            ${data.ml_prediction.predicted_direction === 'up' ? '📈' : data.ml_prediction.predicted_direction === 'down' ? '📉' : '➡️'} 
                            ${data.ml_prediction.predicted_direction.toUpperCase()}
                        </div>
                        <div class="prediction-price">
                            Target: <strong>$${data.ml_prediction.predicted_price}</strong>
                            <span class="prediction-change ${data.ml_prediction.price_change_pct >= 0 ? 'positive' : 'negative'}">
                                (${data.ml_prediction.price_change_pct >= 0 ? '+' : ''}${data.ml_prediction.price_change_pct}%)
                            </span>
                        </div>
                    </div>
                    <div class="prediction-meta">
                        <span class="prediction-confidence">Confidence: ${(data.ml_prediction.confidence * 100).toFixed(0)}%</span>
                        <span class="prediction-horizon">Horizon: ${data.ml_prediction.time_horizon}</span>
                    </div>
                </div>
            </div>
        ` : ''}

        ${data.ml_patterns && data.ml_patterns.length > 0 ? `
            <div class="result-card ml-patterns-card">
                <h3>🧠 ML Pattern Detection</h3>
                <div class="ml-patterns-list">
                    ${data.ml_patterns.map(pattern => `
                        <div class="ml-pattern-item">
                            <div class="pattern-header">
                                <span class="pattern-type">${formatPatternType(pattern.pattern_type)}</span>
                                <span class="pattern-confidence">${(pattern.confidence * 100).toFixed(0)}%</span>
                            </div>
                            <div class="pattern-prediction ${pattern.prediction}">
                                ${pattern.prediction === 'bullish' ? '🟢 Bullish' : pattern.prediction === 'bearish' ? '🔴 Bearish' : '🟡 Neutral'}
                                <span class="pattern-horizon">(${pattern.time_horizon})</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}

        ${data.sentiment ? `
            <div class="result-card sentiment-card">
                <h3>💭 Market Sentiment Analysis</h3>
                <div class="sentiment-content">
                    <div class="sentiment-main">
                        <div class="sentiment-gauge">
                            <div class="sentiment-score">${data.sentiment.overall_score}</div>
                            <div class="sentiment-label">${data.sentiment.emoji} ${data.sentiment.sentiment_label}</div>
                        </div>
                        <div class="sentiment-consensus">
                            <div class="consensus-bar">
                                <div class="consensus-bullish" style="width: ${(data.sentiment.bullish_indicators / (data.sentiment.bullish_indicators + data.sentiment.bearish_indicators + data.sentiment.neutral_indicators)) * 100}%"></div>
                            </div>
                            <div class="consensus-labels">
                                <span class="bullish">🟢 Bullish: ${data.sentiment.bullish_indicators}</span>
                                <span class="bearish">🔴 Bearish: ${data.sentiment.bearish_indicators}</span>
                                <span class="neutral">🟡 Neutral: ${data.sentiment.neutral_indicators}</span>
                            </div>
                        </div>
                    </div>
                    <div class="sentiment-recommendation">
                        ${data.sentiment.recommendation}
                    </div>
                </div>
            </div>
        ` : ''}

        ${data.risk ? `
            <div class="result-card risk-card">
                <h3>⚠️ Risk Assessment</h3>
                <div class="risk-content">
                    <div class="risk-grade-container">
                        <div class="risk-grade" style="background-color: ${data.risk.risk_grade.color}">
                            ${data.risk.risk_grade.grade}
                        </div>
                        <div class="risk-description">
                            <strong>${data.risk.risk_grade.description}</strong>
                            <div class="risk-score">Score: ${data.risk.overall_risk_score}/100</div>
                        </div>
                    </div>
                    <div class="risk-metrics">
                        <div class="risk-metric">
                            <span class="metric-label">Volatility:</span>
                            <span class="metric-value">${data.risk.volatility.annual_volatility}%</span>
                        </div>
                        <div class="risk-metric">
                            <span class="metric-label">1-Day VaR:</span>
                            <span class="metric-value">$${Math.abs(data.risk.value_at_risk.var_1day_dollar)}</span>
                        </div>
                        <div class="risk-metric">
                            <span class="metric-label">Max Drawdown:</span>
                            <span class="metric-value">${data.risk.value_at_risk.max_drawdown_pct}%</span>
                        </div>
                    </div>
                    ${data.risk.recommendations ? `
                        <div class="risk-recommendations">
                            ${data.risk.recommendations.map(rec => `<div class="risk-rec">${rec}</div>`).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        ` : ''}

        ${data.timing && data.timing.entry ? `
            <div class="result-card timing-card">
                <h3>⏰ Trading Time Intelligence</h3>
                <div class="timing-content">
                    <div class="timing-section">
                        <h4>📥 Entry Analysis</h4>
                        <div class="timing-score entry-score">
                            <div class="score-bar">
                                <div class="score-fill" style="width: ${data.timing.entry.entry_score}%; background: ${data.timing.entry.entry_score >= 70 ? '#10b981' : data.timing.entry.entry_score >= 50 ? '#f59e0b' : '#ef4444'}"></div>
                            </div>
                            <div class="score-label">${data.timing.entry.entry_score}/100</div>
                        </div>
                        <div class="timing-recommendation">${data.timing.entry.recommendation}</div>
                        ${data.timing.entry.signals && data.timing.entry.signals.length > 0 ? `
                            <div class="timing-signals">
                                ${data.timing.entry.signals.slice(0, 3).map(signal => `
                                    <div class="signal-item">
                                        <strong>${signal.signal}:</strong> ${signal.description}
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                    ${data.timing.exit ? `
                        <div class="timing-section">
                            <h4>📤 Exit Analysis</h4>
                            <div class="timing-score exit-score">
                                <div class="score-bar">
                                    <div class="score-fill" style="width: ${data.timing.exit.exit_score}%; background: ${data.timing.exit.exit_score >= 70 ? '#ef4444' : data.timing.exit.exit_score >= 50 ? '#f59e0b' : '#10b981'}"></div>
                                </div>
                                <div class="score-label">${data.timing.exit.exit_score}/100</div>
                            </div>
                            <div class="timing-recommendation">${data.timing.exit.recommendation}</div>
                            ${data.timing.exit.price_targets ? `
                                <div class="price-targets">
                                    <div class="target-item stop-loss">
                                        Stop Loss: $${data.timing.exit.price_targets.stop_loss.price} (${data.timing.exit.price_targets.stop_loss.distance_pct}%)
                                    </div>
                                    <div class="target-item take-profit">
                                        Take Profit: $${data.timing.exit.price_targets.take_profit_1.price} (${data.timing.exit.price_targets.take_profit_1.distance_pct}%)
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                </div>
            </div>
        ` : ''}
    `;
}

function formatPatternType(type) {
    const patterns = {
        'double_top': 'Double Top',
        'double_bottom': 'Double Bottom',
        'head_and_shoulders': 'Head & Shoulders',
        'ascending_triangle': 'Ascending Triangle',
        'descending_triangle': 'Descending Triangle',
        'symmetrical_triangle': 'Symmetrical Triangle',
        'breakout': 'Breakout',
        'volume_surge': 'Volume Surge'
    };
    return patterns[type] || type.replace(/_/g, ' ').toUpperCase();
}

// =======================
// MODAL FUNCTIONALITY
// =======================

function initializeModals() {
    // Close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').style.display = 'none';
        });
    });

    // Click outside to close
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    });
}

// =======================
// HEADER BUTTONS
// =======================

function initializeHeaderButtons() {
    const multiChartBtn = document.getElementById('multiChartView');
    const settingsBtn = document.getElementById('settingsBtn');

    // Multi-Chart View - Opens grid layout with independent charts
    if (multiChartBtn) {
        multiChartBtn.addEventListener('click', () => {
            openMultiChartModal();
        });
    }

    // Settings Button - Placeholder for future settings
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            showSettingsMenu();
        });
    }
}

function showSettingsMenu() {
    // Create settings modal
    const existingModal = document.getElementById('settingsModal');
    if (existingModal) {
        existingModal.remove();
    }

    const autoRefresh = localStorage.getItem('autoRefreshWatchlist') !== 'false';
    const notifications = localStorage.getItem('notificationsEnabled') !== 'false';
    const darkMode = localStorage.getItem('darkMode') === 'true';

    const modal = document.createElement('div');
    modal.id = 'settingsModal';
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 10000;';
    
    modal.innerHTML = `
        <div style="background: white; border-radius: 12px; padding: 30px; max-width: 500px; width: 90%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="margin: 0;">⚙️ Settings</h2>
                <button onclick="document.getElementById('settingsModal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: flex; align-items: center; padding: 15px; background: #f5f5f5; border-radius: 8px; cursor: pointer; margin-bottom: 10px;">
                    <input type="checkbox" id="autoRefreshSetting" ${autoRefresh ? 'checked' : ''} style="margin-right: 10px; width: 20px; height: 20px; cursor: pointer;">
                    <div>
                        <div style="font-weight: 600;">Auto-refresh Watchlist</div>
                        <div style="font-size: 0.9em; color: #666;">Automatically update prices every 60 seconds</div>
                    </div>
                </label>
                
                <label style="display: flex; align-items: center; padding: 15px; background: #f5f5f5; border-radius: 8px; cursor: pointer; margin-bottom: 10px;">
                    <input type="checkbox" id="notificationsSetting" ${notifications ? 'checked' : ''} style="margin-right: 10px; width: 20px; height: 20px; cursor: pointer;">
                    <div>
                        <div style="font-weight: 600;">Enable Notifications</div>
                        <div style="font-size: 0.9em; color: #666;">Show browser notifications for alerts</div>
                    </div>
                </label>
                
                <label style="display: flex; align-items: center; padding: 15px; background: #f5f5f5; border-radius: 8px; cursor: pointer;">
                    <input type="checkbox" id="darkModeSetting" ${darkMode ? 'checked' : ''} style="margin-right: 10px; width: 20px; height: 20px; cursor: pointer;">
                    <div>
                        <div style="font-weight: 600;">Dark Mode</div>
                        <div style="font-size: 0.9em; color: #666;">Switch between light and dark themes</div>
                    </div>
                </label>
            </div>
            
            <button onclick="saveSettings()" style="width: 100%; padding: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer;">Save Settings</button>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function saveSettings() {
    const autoRefresh = document.getElementById('autoRefreshSetting').checked;
    const notifications = document.getElementById('notificationsSetting').checked;
    const darkMode = document.getElementById('darkModeSetting').checked;
    
    localStorage.setItem('autoRefreshWatchlist', autoRefresh);
    localStorage.setItem('notificationsEnabled', notifications);
    localStorage.setItem('darkMode', darkMode);
    
    // Apply dark mode immediately
    toggleDarkMode(darkMode);
    
    document.getElementById('settingsModal').remove();
    
    // Show confirmation
    const toast = document.createElement('div');
    toast.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #4CAF50; color: white; padding: 15px 20px; border-radius: 8px; z-index: 10001; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
    toast.textContent = '✓ Settings saved successfully!';
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
}

// Make saveSettings available globally
window.saveSettings = saveSettings;

// =======================
// MULTI-CHART GRID VIEW
// =======================

let multiChartSymbols = [];
const maxMultiCharts = 6;

function openMultiChartModal() {
    const modal = document.getElementById('multiChartModal');
    if (modal) {
        modal.style.display = 'flex';
        initializeMultiChartModal();
    }
}

function initializeMultiChartModal() {
    const addBtn = document.getElementById('addMultiChartSymbol');
    const clearBtn = document.getElementById('clearMultiCharts');
    const input = document.getElementById('multiChartSymbolInput');
    const closeBtn = document.querySelector('#multiChartModal .modal-close');
    
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('multiChartModal').style.display = 'none';
        });
    }
    
    if (addBtn) {
        addBtn.addEventListener('click', () => addMultiChartSymbol());
    }
    
    if (clearBtn) {
        clearBtn.addEventListener('click', () => clearMultiCharts());
    }
    
    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                addMultiChartSymbol();
            }
        });
    }
}

async function addMultiChartSymbol() {
    const input = document.getElementById('multiChartSymbolInput');
    const period = document.getElementById('multiChartPeriod').value;
    const chartType = document.getElementById('multiChartType').value;
    const symbol = input.value.toUpperCase().trim();
    
    if (!symbol) return;
    
    if (multiChartSymbols.length >= maxMultiCharts) {
        alert(`Maximum ${maxMultiCharts} charts allowed`);
        return;
    }
    
    if (multiChartSymbols.includes(symbol)) {
        alert(`${symbol} is already in the grid`);
        return;
    }
    
    const grid = document.getElementById('multiChartGrid');
    const chartContainer = document.createElement('div');
    chartContainer.className = 'multi-chart-item';
    chartContainer.id = `multi-chart-${symbol}`;
    chartContainer.innerHTML = `
        <div class="multi-chart-header">
            <h3>${symbol}</h3>
            <button class="remove-chart-btn" onclick="removeMultiChart('${symbol}')">&times;</button>
        </div>
        <div class="multi-chart-loading">Loading ${symbol}...</div>
    `;
    
    grid.appendChild(chartContainer);
    multiChartSymbols.push(symbol);
    input.value = '';
    
    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, period, chartType })
        });
        
        if (response.ok) {
            const data = await response.json();
            const chartHtml = `
                <div class="multi-chart-header">
                    <h3>${symbol}</h3>
                    <span class="chart-price">${data.currentPrice ? '$' + data.currentPrice.toFixed(2) : ''}</span>
                    <button class="remove-chart-btn" onclick="removeMultiChart('${symbol}')">&times;</button>
                </div>
                <div class="multi-chart-body">
                    <img src="data:image/png;base64,${data.chart}" alt="${symbol} Chart" />
                </div>
            `;
            chartContainer.innerHTML = chartHtml;
        } else {
            throw new Error('Failed to load chart');
        }
    } catch (error) {
        console.error('Error loading chart:', error);
        chartContainer.innerHTML = `
            <div class="multi-chart-header">
                <h3>${symbol}</h3>
                <button class="remove-chart-btn" onclick="removeMultiChart('${symbol}')">&times;</button>
            </div>
            <div class="multi-chart-error">Failed to load chart</div>
        `;
    }
}

function removeMultiChart(symbol) {
    const chartElement = document.getElementById(`multi-chart-${symbol}`);
    if (chartElement) {
        chartElement.remove();
    }
    multiChartSymbols = multiChartSymbols.filter(s => s !== symbol);
}

function clearMultiCharts() {
    const grid = document.getElementById('multiChartGrid');
    if (grid) {
        grid.innerHTML = '';
    }
    multiChartSymbols = [];
}

// =======================
// PORTFOLIO WIDGET
// =======================

function initializePortfolioWidget() {
    loadPortfolioWidget();
    
    // Auto-refresh every 60 seconds
    setInterval(loadPortfolioWidget, 60000);
}

async function loadPortfolioWidget() {
    const widget = document.getElementById('portfolioWidget');
    
    // Hide widget if not logged in or Phase 4 not enabled
    if (!widget) return;
    
    try {
        const response = await fetch('/api/portfolio');
        
        if (!response.ok) {
            // Hide widget if not authenticated or Phase 4 not available
            if (response.status === 401 || response.status === 503) {
                widget.style.display = 'none';
                return;
            }
            throw new Error('Failed to load portfolio');
        }
        
        const data = await response.json();
        
        // Show widget
        widget.style.display = 'block';
        
        // Update values
        const totalValue = data.total_value || 0;
        const totalPnl = data.total_pnl || 0;
        const dailyChange = data.daily_change?.value || 0;
        
        document.getElementById('dashboardPortfolioValue').textContent = 
            `$${totalValue.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        
        const pnlElement = document.getElementById('dashboardPortfolioPnL');
        pnlElement.textContent = 
            `${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        pnlElement.className = 'stat-value ' + (totalPnl >= 0 ? 'positive' : 'negative');
        
        const todayElement = document.getElementById('dashboardPortfolioToday');
        todayElement.textContent = 
            `${dailyChange >= 0 ? '+' : ''}$${Math.abs(dailyChange).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        todayElement.className = 'stat-value ' + (dailyChange >= 0 ? 'positive' : 'negative');
        
    } catch (error) {
        console.error('Error loading portfolio widget:', error);
        // Hide widget on error
        widget.style.display = 'none';
    }
}

// =======================
// TECHNICAL CHART MODAL
// =======================

function initializeTechnicalChart() {
    const openBtn = document.getElementById('openTechnicalChart');
    const generateBtn = document.getElementById('generateTechnicalChart');
    const modal = document.getElementById('technicalChartModal');
    const closeBtn = modal.querySelector('.modal-close');

    openBtn.addEventListener('click', () => {
        modal.style.display = 'flex';
    });

    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    generateBtn.addEventListener('click', async () => {
        await generateTechnicalChart();
    });

    // Enter key on symbol input
    document.getElementById('techChartSymbol').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            generateBtn.click();
        }
    });
}

async function generateTechnicalChart() {
    const symbol = document.getElementById('techChartSymbol').value.trim().toUpperCase();
    const period = document.getElementById('techChartPeriod').value;
    const displayDiv = document.getElementById('technicalChartDisplay');

    if (!symbol) {
        showToast('Please enter a symbol', 'error');
        return;
    }

    // Get selected indicators
    const indicators = [];
    if (document.getElementById('techIndicatorRSI').checked) indicators.push('rsi');
    if (document.getElementById('techIndicatorMACD').checked) indicators.push('macd');
    if (document.getElementById('techIndicatorBB').checked) indicators.push('bb');
    if (document.getElementById('techIndicatorMA').checked) indicators.push('ma');

    if (indicators.length === 0) {
        showToast('Please select at least one indicator', 'error');
        return;
    }

    displayDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Generating technical chart...</p></div>';

    try {
        const response = await fetch('/api/technical-chart', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': localStorage.getItem('apiKey') || ''
            },
            body: JSON.stringify({
                symbol: symbol,
                period: period,
                interval: '1d',
                indicators: indicators
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to generate chart');
        }

        const data = await response.json();

        // Display chart
        displayDiv.innerHTML = `
            <div class="technical-chart-result">
                <div class="chart-header">
                    <h3>${symbol} - Technical Analysis</h3>
                    <div class="price-info">
                        <span class="current-price">$${data.current_price}</span>
                        <span class="price-change ${data.price_change >= 0 ? 'positive' : 'negative'}">
                            ${data.price_change >= 0 ? '▲' : '▼'} ${data.price_change_pct}%
                        </span>
                    </div>
                </div>
                <img src="${data.chart}" alt="${symbol} Technical Chart" style="width: 100%; margin-top: 15px;" />
                <div class="indicator-legend">
                    ${indicators.map(ind => {
                        const labels = {
                            'rsi': 'RSI (14)',
                            'macd': 'MACD (12,26,9)',
                            'bb': 'Bollinger Bands (20,2)',
                            'ma': 'Moving Averages (20,50,200)'
                        };
                        return `<span class="legend-item">✓ ${labels[ind]}</span>`;
                    }).join('')}
                </div>
            </div>
        `;

        showToast(`Technical chart generated for ${symbol}`, 'success');
    } catch (error) {
        console.error('Error generating technical chart:', error);
        displayDiv.innerHTML = `
            <div class="error-message">
                <p>❌ ${error.message}</p>
                <p>Please check the symbol and try again.</p>
            </div>
        `;
        showToast(error.message, 'error');
    }
}
