/**
 * Trade Journal & AI Analytics
 * Feature #5: Interactive trading history with AI-powered insights
 */

class TradeJournal {
    constructor() {
        this.container = null;
        this.currentDays = 90;
        this.cache = {
            history: null,
            performance: null,
            insights: null,
            timestamp: null
        };
        this.CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
    }

    async init() {
        this.createUI();
        await this.loadAllData();
        
        // Auto-refresh every 5 minutes
        setInterval(() => {
            this.loadAllData();
        }, 5 * 60 * 1000);
    }

    createUI() {
        this.container = document.createElement('div');
        this.container.className = 'journal-panel';
        this.container.innerHTML = `
            <div class="panel-header">
                <h2>📖 AI Trade Journal & Analytics</h2>
                <div class="journal-controls">
                    <select class="time-selector" id="journal-time-range">
                        <option value="30">Last 30 Days</option>
                        <option value="90" selected>Last 90 Days</option>
                        <option value="180">Last 6 Months</option>
                        <option value="365">Last Year</option>
                    </select>
                    <button class="btn-refresh" id="journal-refresh">
                        <span class="icon">🔄</span> Refresh
                    </button>
                </div>
            </div>
            
            <div class="journal-content">
                <!-- Performance Summary -->
                <div class="performance-section" id="performance-summary">
                    <div class="loading-spinner">Loading performance data...</div>
                </div>
                
                <!-- AI Insights -->
                <div class="insights-section" id="ai-insights">
                    <div class="loading-spinner">Loading AI insights...</div>
                </div>
                
                <!-- Trade History -->
                <div class="history-section" id="trade-history">
                    <div class="loading-spinner">Loading trade history...</div>
                </div>
            </div>
        `;

        // Add to dashboard
        const dashboardContainer = document.querySelector('.dashboard-container');
        if (dashboardContainer) {
            dashboardContainer.appendChild(this.container);
        }

        // Event listeners
        document.getElementById('journal-time-range')?.addEventListener('change', (e) => {
            this.currentDays = parseInt(e.target.value);
            this.clearCache();
            this.loadAllData();
        });

        document.getElementById('journal-refresh')?.addEventListener('click', () => {
            this.clearCache();
            this.loadAllData();
        });
    }

    async loadAllData() {
        await Promise.all([
            this.loadPerformance(),
            this.loadInsights(),
            this.loadHistory()
        ]);
    }

    clearCache() {
        this.cache = {
            history: null,
            performance: null,
            insights: null,
            timestamp: null
        };
    }

    isCacheValid() {
        return this.cache.timestamp && 
               (Date.now() - this.cache.timestamp) < this.CACHE_DURATION;
    }

    async loadPerformance() {
        try {
            const container = document.getElementById('performance-summary');
            this.showLoading(container);

            const response = await fetch(`/api/journal/performance?days=${this.currentDays}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                this.showError(container, data.error);
                return;
            }

            this.cache.performance = data;
            this.cache.timestamp = Date.now();
            this.renderPerformance(data);
            console.log('Trade Journal: Performance data loaded', data);

        } catch (error) {
            console.error('Error loading performance:', error);
            this.showError(document.getElementById('performance-summary'), 
                          'Failed to load performance data');
        }
    }

    async loadInsights() {
        try {
            const container = document.getElementById('ai-insights');
            this.showLoading(container);

            const response = await fetch(`/api/journal/insights?days=${this.currentDays}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                this.showError(container, data.error);
                return;
            }

            this.cache.insights = data;
            this.renderInsights(data);
            console.log('Trade Journal: AI insights loaded', data);

        } catch (error) {
            console.error('Error loading insights:', error);
            this.showError(document.getElementById('ai-insights'), 
                          'Failed to load AI insights');
        }
    }

    async loadHistory() {
        try {
            const container = document.getElementById('trade-history');
            this.showLoading(container);

            const response = await fetch(`/api/journal/history?days=${this.currentDays}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                this.showError(container, data.error);
                return;
            }

            this.cache.history = data;
            this.renderHistory(data);
            console.log('Trade Journal: Trade history loaded', data);

        } catch (error) {
            console.error('Error loading history:', error);
            this.showError(document.getElementById('trade-history'), 
                          'Failed to load trade history');
        }
    }

    renderPerformance(data) {
        const container = document.getElementById('performance-summary');
        const metrics = data.metrics;

        const totalClass = metrics.total_realized >= 0 ? 'positive' : 'negative';
        const winRateClass = metrics.win_rate >= 60 ? 'good' : metrics.win_rate >= 40 ? 'moderate' : 'poor';

        container.innerHTML = `
            <h3>📊 Performance Summary</h3>
            <div class="metrics-grid">
                <div class="metric-card large ${totalClass}">
                    <div class="metric-label">Total Realized P&L</div>
                    <div class="metric-value">$${metrics.total_realized.toFixed(2)}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value ${winRateClass}">${metrics.win_rate}%</div>
                    <div class="metric-detail">${metrics.winners}W / ${metrics.losers}L</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Avg Winner</div>
                    <div class="metric-value positive">$${metrics.avg_gain.toFixed(2)}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Avg Loser</div>
                    <div class="metric-value negative">$${metrics.avg_loss.toFixed(2)}</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Avg Hold Time</div>
                    <div class="metric-value">${metrics.avg_hold_time.toFixed(0)} days</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">${metrics.total_trades}</div>
                </div>
            </div>
            
            ${metrics.best_trade ? `
                <div class="best-worst-section">
                    <div class="trade-highlight best">
                        <span class="icon">🏆</span>
                        <div>
                            <strong>Best Trade:</strong> ${metrics.best_trade.symbol} 
                            <span class="gain">+$${metrics.best_trade.gain.toFixed(2)} 
                            (${metrics.best_trade.gain_pct.toFixed(1)}%)</span>
                        </div>
                    </div>
                    <div class="trade-highlight worst">
                        <span class="icon">📉</span>
                        <div>
                            <strong>Worst Trade:</strong> ${metrics.worst_trade.symbol} 
                            <span class="loss">$${metrics.worst_trade.gain.toFixed(2)} 
                            (${metrics.worst_trade.gain_pct.toFixed(1)}%)</span>
                        </div>
                    </div>
                </div>
            ` : ''}
        `;
    }

    renderInsights(data) {
        const container = document.getElementById('ai-insights');

        if (!data.insights || data.insights.length === 0) {
            container.innerHTML = `
                <h3>🤖 AI Insights</h3>
                <div class="empty-state">
                    <p>Start trading to receive AI-powered insights!</p>
                </div>
            `;
            return;
        }

        const insightsHTML = data.insights.map(insight => `
            <div class="insight-card">
                <span class="icon">💡</span>
                <p>${insight}</p>
            </div>
        `).join('');

        const recommendationsHTML = data.recommendations.map(rec => `
            <div class="recommendation-card">
                <span class="icon">🎯</span>
                <p>${rec}</p>
            </div>
        `).join('');

        container.innerHTML = `
            <h3>🤖 AI-Powered Insights</h3>
            
            <div class="insights-grid">
                <div class="insights-column">
                    <h4>Key Patterns</h4>
                    ${insightsHTML}
                </div>
                
                <div class="recommendations-column">
                    <h4>Recommendations</h4>
                    ${recommendationsHTML}
                </div>
            </div>
        `;
    }

    renderHistory(data) {
        const container = document.getElementById('trade-history');

        if (!data.trades || data.trades.length === 0) {
            container.innerHTML = `
                <h3>📜 Trade History</h3>
                <div class="empty-state">
                    <p>No trades found in this time period.</p>
                </div>
            `;
            return;
        }

        const summary = data.summary;
        const tradesHTML = data.trades.slice(0, 20).map(trade => {
            const typeClass = trade.type === 'buy' ? 'buy' : 'sell';
            const typeIcon = trade.type === 'buy' ? '📈' : '📉';
            const date = new Date(trade.date).toLocaleDateString();

            return `
                <tr class="trade-row ${typeClass}">
                    <td>${typeIcon} ${trade.type.toUpperCase()}</td>
                    <td><strong>${trade.symbol}</strong></td>
                    <td>${trade.quantity}</td>
                    <td>$${trade.price.toFixed(2)}</td>
                    <td>$${trade.total.toFixed(2)}</td>
                    <td>${date}</td>
                    <td>${trade.notes || ''}</td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <h3>📜 Trade History</h3>
            
            <div class="history-summary">
                <div class="summary-stat">
                    <span class="label">Total Trades:</span>
                    <span class="value">${summary.total_trades}</span>
                </div>
                <div class="summary-stat">
                    <span class="label">Buys:</span>
                    <span class="value buy">${summary.buy_count}</span>
                </div>
                <div class="summary-stat">
                    <span class="label">Sells:</span>
                    <span class="value sell">${summary.sell_count}</span>
                </div>
                <div class="summary-stat">
                    <span class="label">Net Flow:</span>
                    <span class="value ${summary.net_flow >= 0 ? 'positive' : 'negative'}">
                        $${summary.net_flow.toFixed(2)}
                    </span>
                </div>
            </div>
            
            <div class="trades-table-container">
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Total</th>
                            <th>Date</th>
                            <th>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tradesHTML}
                    </tbody>
                </table>
            </div>
            
            ${data.trades.length > 20 ? `
                <div class="trades-footer">
                    Showing 20 of ${data.trades.length} trades
                </div>
            ` : ''}
        `;
    }

    showLoading(container) {
        container.innerHTML = '<div class="loading-spinner">Loading...</div>';
    }

    showError(container, message) {
        container.innerHTML = `
            <div class="error-state">
                <span class="icon">⚠️</span>
                <p>${message}</p>
            </div>
        `;
    }
}

// Auto-initialize when dashboard loads
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.dashboard-container')) {
        const journal = new TradeJournal();
        journal.init();
        console.log('Trade Journal initialized');
    }
});
