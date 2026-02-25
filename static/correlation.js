/**
 * Correlation Matrix & Heat Map Visualization (Feature #4)
 * Interactive heat map showing portfolio correlations
 */

class CorrelationHeatMap {
    constructor() {
        this.currentPeriod = '3mo';
        this.heatmapContainer = null;
        this.diversificationContainer = null;
        this.refreshInterval = null;
    }

    async init() {
        console.log('Correlation Heat Map: Initializing...');
        this.createUI();
        await this.loadData();
        this.startAutoRefresh();
    }

    createUI() {
        // Find or create container in dashboard
        let container = document.querySelector('.correlation-panel');
        
        if (!container) {
            // Create panel if it doesn't exist
            const dashboardContainer = document.querySelector('.dashboard-container');
            if (!dashboardContainer) {
                console.error('Dashboard container not found');
                return;
            }

            container = document.createElement('div');
            container.className = 'correlation-panel dashboard-panel';
            dashboardContainer.appendChild(container);
        }

        container.innerHTML = `
            <div class="panel-header">
                <h2>📊 Correlation Matrix & Diversification</h2>
                <div class="panel-controls">
                    <select class="period-selector" id="correlationPeriod">
                        <option value="1mo">1 Month</option>
                        <option value="3mo" selected>3 Months</option>
                        <option value="6mo">6 Months</option>
                        <option value="1y">1 Year</option>
                        <option value="2y">2 Years</option>
                    </select>
                    <button class="btn-refresh" id="refreshCorrelation" title="Refresh">
                        ↻
                    </button>
                </div>
            </div>
            
            <div class="correlation-content">
                <!-- Diversification Metrics -->
                <div class="diversification-section">
                    <h3>Portfolio Diversification</h3>
                    <div id="diversificationMetrics" class="metrics-container">
                        <div class="loading">Loading diversification metrics...</div>
                    </div>
                </div>

                <!-- Correlation Heat Map -->
                <div class="heatmap-section">
                    <h3>Correlation Heat Map</h3>
                    <div class="heatmap-legend">
                        <span class="legend-label">Negative</span>
                        <div class="legend-gradient"></div>
                        <span class="legend-label">Positive</span>
                    </div>
                    <div id="correlationHeatmap" class="heatmap-container">
                        <div class="loading">Loading correlation matrix...</div>
                    </div>
                    <div class="heatmap-info">
                        <p>💡 <strong>Reading the heat map:</strong></p>
                        <ul>
                            <li>Green/Positive: Assets move in the same direction</li>
                            <li>Red/Negative: Assets move in opposite directions</li>
                            <li>Darker colors indicate stronger correlation</li>
                            <li>Hover over cells for detailed correlation values</li>
                        </ul>
                    </div>
                </div>
            </div>
        `;

        this.heatmapContainer = document.getElementById('correlationHeatmap');
        this.diversificationContainer = document.getElementById('diversificationMetrics');

        // Event listeners
        document.getElementById('correlationPeriod').addEventListener('change', (e) => {
            this.currentPeriod = e.target.value;
            this.loadData();
        });

        document.getElementById('refreshCorrelation').addEventListener('click', () => {
            this.loadData();
        });

        console.log('Correlation Heat Map: UI created');
    }

    async loadData() {
        await Promise.all([
            this.loadCorrelationMatrix(),
            this.loadDiversificationMetrics()
        ]);
    }

    async loadCorrelationMatrix() {
        try {
            this.showLoading(this.heatmapContainer);

            const response = await fetch(`/api/correlation/matrix?period=${this.currentPeriod}`, {
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
                this.showError(this.heatmapContainer, data.error);
                return;
            }

            this.renderHeatMap(data);
            console.log('Correlation Heat Map: Matrix loaded', data);

        } catch (error) {
            console.error('Error loading correlation matrix:', error);
            this.showError(this.heatmapContainer, 'Failed to load correlation matrix');
        }
    }

    async loadDiversificationMetrics() {
        try {
            this.showLoading(this.diversificationContainer);

            const response = await fetch('/api/correlation/diversification', {
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
                this.showError(this.diversificationContainer, data.error);
                return;
            }

            this.renderDiversificationMetrics(data);
            console.log('Correlation Heat Map: Diversification metrics loaded', data);

        } catch (error) {
            console.error('Error loading diversification metrics:', error);
            this.showError(this.diversificationContainer, 'Failed to load diversification metrics');
        }
    }

    renderHeatMap(data) {
        const { matrix, symbols, avg_correlations } = data;

        if (!matrix || matrix.length === 0) {
            this.heatmapContainer.innerHTML = '<div class="empty-state">No correlation data available</div>';
            return;
        }

        // Build heat map table
        let html = '<table class="correlation-table">';
        
        // Header row with symbol names
        html += '<thead><tr><th></th>';
        symbols.forEach(symbol => {
            html += `<th class="symbol-header">${symbol}</th>`;
        });
        html += '</tr></thead>';

        // Data rows
        html += '<tbody>';
        matrix.forEach((row, i) => {
            html += '<tr>';
            html += `<th class="symbol-header">${symbols[i]}</th>`;
            
            row.forEach(cell => {
                const corr = cell.correlation;
                const color = this.getCorrelationColor(corr);
                const isDiagonal = cell.symbol1 === cell.symbol2;
                
                html += `<td class="correlation-cell ${isDiagonal ? 'diagonal' : ''}" 
                            style="background-color: ${color};" 
                            data-symbol1="${cell.symbol1}"
                            data-symbol2="${cell.symbol2}"
                            data-correlation="${corr}"
                            title="${cell.symbol1} vs ${cell.symbol2}: ${corr}">
                    <span class="correlation-value">${corr.toFixed(2)}</span>
                </td>`;
            });
            
            html += '</tr>';
        });
        html += '</tbody></table>';

        // Add average correlations summary
        html += '<div class="correlation-summary">';
        html += '<h4>Average Correlations by Symbol</h4>';
        html += '<div class="avg-correlations">';
        
        const sortedAvgs = Object.entries(avg_correlations)
            .sort((a, b) => b[1] - a[1]);
        
        sortedAvgs.forEach(([symbol, avgCorr]) => {
            const color = this.getCorrelationColor(avgCorr);
            html += `
                <div class="avg-correlation-item">
                    <span class="symbol-badge">${symbol}</span>
                    <div class="correlation-bar-container">
                        <div class="correlation-bar" style="width: ${Math.abs(avgCorr) * 100}%; background-color: ${color};"></div>
                    </div>
                    <span class="correlation-label">${avgCorr.toFixed(3)}</span>
                </div>
            `;
        });
        
        html += '</div></div>';

        this.heatmapContainer.innerHTML = html;

        // Add hover effects
        this.addHeatMapInteractivity();
    }

    renderDiversificationMetrics(data) {
        const {
            diversification_score,
            weighted_avg_correlation,
            concentration_score,
            risk_level,
            position_count,
            sector_exposure,
            recommendations
        } = data;

        let html = '<div class="metrics-grid">';

        // Diversification Score (large metric)
        const scoreColor = this.getDiversificationScoreColor(diversification_score);
        html += `
            <div class="metric-card large-metric">
                <div class="metric-label">Diversification Score</div>
                <div class="metric-value" style="color: ${scoreColor};">
                    ${diversification_score}
                    <span class="metric-unit">/100</span>
                </div>
                <div class="metric-description">
                    ${diversification_score >= 70 ? '✓ Well diversified' : 
                      diversification_score >= 40 ? '⚠ Moderate diversification' : 
                      '⚠ Poor diversification'}
                </div>
            </div>
        `;

        // Risk Level
        const riskColor = risk_level === 'Low' ? '#10b981' : 
                         risk_level === 'Medium' ? '#f59e0b' : '#ef4444';
        html += `
            <div class="metric-card">
                <div class="metric-label">Risk Level</div>
                <div class="metric-value" style="color: ${riskColor};">
                    ${risk_level}
                </div>
                <div class="metric-sub">Avg Correlation: ${weighted_avg_correlation.toFixed(3)}</div>
            </div>
        `;

        // Concentration Score
        const concColor = concentration_score > 50 ? '#ef4444' : 
                         concentration_score > 30 ? '#f59e0b' : '#10b981';
        html += `
            <div class="metric-card">
                <div class="metric-label">Concentration</div>
                <div class="metric-value" style="color: ${concColor};">
                    ${concentration_score}%
                </div>
                <div class="metric-sub">${position_count} positions</div>
            </div>
        `;

        // Top Sector Exposure
        if (sector_exposure && sector_exposure.top_sector) {
            html += `
                <div class="metric-card">
                    <div class="metric-label">Top Sector</div>
                    <div class="metric-value">
                        ${sector_exposure.top_sector_exposure.toFixed(1)}%
                    </div>
                    <div class="metric-sub">${sector_exposure.top_sector}</div>
                </div>
            `;
        }

        html += '</div>';

        // Sector Exposure Breakdown
        if (sector_exposure && sector_exposure.sectors) {
            html += '<div class="sector-exposure-section">';
            html += '<h4>Sector Exposure</h4>';
            html += '<div class="sector-bars">';
            
            Object.entries(sector_exposure.sectors).forEach(([sector, percentage]) => {
                const barColor = percentage > 40 ? '#ef4444' : 
                               percentage > 25 ? '#f59e0b' : '#3b82f6';
                html += `
                    <div class="sector-bar-item">
                        <div class="sector-label">${sector}</div>
                        <div class="sector-bar-container">
                            <div class="sector-bar" style="width: ${percentage}%; background-color: ${barColor};"></div>
                        </div>
                        <div class="sector-percentage">${percentage.toFixed(1)}%</div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }

        // Recommendations
        if (recommendations && recommendations.length > 0) {
            html += '<div class="recommendations-section">';
            html += '<h4>Recommendations</h4>';
            
            recommendations.forEach(rec => {
                const cardClass = rec.type === 'warning' ? 'warning' : 
                                rec.type === 'success' ? 'success' : 'info';
                html += `
                    <div class="recommendation-card ${cardClass}">
                        <div class="rec-icon">${rec.icon}</div>
                        <div class="rec-content">
                            <div class="rec-message">${rec.message}</div>
                            <div class="rec-action">${rec.action}</div>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
        }

        this.diversificationContainer.innerHTML = html;
    }

    getCorrelationColor(correlation) {
        // Color scale: red (negative) -> white (0) -> green (positive)
        const absCorr = Math.abs(correlation);
        
        if (correlation >= 0) {
            // Positive correlation: white to green
            const intensity = Math.floor(absCorr * 155) + 100; // 100-255
            return `rgb(${255 - intensity}, ${intensity}, ${255 - intensity})`;
        } else {
            // Negative correlation: white to red
            const intensity = Math.floor(absCorr * 155) + 100; // 100-255
            return `rgb(${intensity}, ${255 - intensity}, ${255 - intensity})`;
        }
    }

    getDiversificationScoreColor(score) {
        if (score >= 70) return '#10b981'; // Green
        if (score >= 40) return '#f59e0b'; // Orange
        return '#ef4444'; // Red
    }

    addHeatMapInteractivity() {
        const cells = this.heatmapContainer.querySelectorAll('.correlation-cell:not(.diagonal)');
        
        cells.forEach(cell => {
            cell.addEventListener('mouseenter', (e) => {
                const symbol1 = e.target.dataset.symbol1;
                const symbol2 = e.target.dataset.symbol2;
                const corr = e.target.dataset.correlation;
                
                // Highlight related cells
                const relatedCells = this.heatmapContainer.querySelectorAll(
                    `.correlation-cell[data-symbol1="${symbol1}"], ` +
                    `.correlation-cell[data-symbol2="${symbol1}"], ` +
                    `.correlation-cell[data-symbol1="${symbol2}"], ` +
                    `.correlation-cell[data-symbol2="${symbol2}"]`
                );
                
                relatedCells.forEach(c => c.classList.add('highlighted'));
                
                // Show tooltip
                this.showTooltip(e, symbol1, symbol2, parseFloat(corr));
            });

            cell.addEventListener('mouseleave', () => {
                const highlightedCells = this.heatmapContainer.querySelectorAll('.correlation-cell.highlighted');
                highlightedCells.forEach(c => c.classList.remove('highlighted'));
                this.hideTooltip();
            });
        });
    }

    showTooltip(event, symbol1, symbol2, correlation) {
        let tooltip = document.getElementById('correlationTooltip');
        
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'correlationTooltip';
            tooltip.className = 'correlation-tooltip';
            document.body.appendChild(tooltip);
        }

        const interpretation = this.getCorrelationInterpretation(correlation);
        
        tooltip.innerHTML = `
            <div class="tooltip-header">${symbol1} vs ${symbol2}</div>
            <div class="tooltip-value">Correlation: ${correlation.toFixed(3)}</div>
            <div class="tooltip-interpretation">${interpretation}</div>
        `;

        tooltip.style.display = 'block';
        tooltip.style.left = `${event.pageX + 10}px`;
        tooltip.style.top = `${event.pageY + 10}px`;
    }

    hideTooltip() {
        const tooltip = document.getElementById('correlationTooltip');
        if (tooltip) {
            tooltip.style.display = 'none';
        }
    }

    getCorrelationInterpretation(corr) {
        const absCorr = Math.abs(corr);
        
        if (absCorr >= 0.8) {
            return corr > 0 ? 
                '🔴 Very strong positive correlation - move together' : 
                '🔴 Very strong negative correlation - move opposite';
        } else if (absCorr >= 0.6) {
            return corr > 0 ? 
                '🟠 Strong positive correlation' : 
                '🟠 Strong negative correlation';
        } else if (absCorr >= 0.4) {
            return corr > 0 ? 
                '🟡 Moderate positive correlation' : 
                '🟡 Moderate negative correlation';
        } else if (absCorr >= 0.2) {
            return '🟢 Weak correlation - somewhat independent';
        } else {
            return '🟢 Very weak correlation - largely independent';
        }
    }

    showLoading(container) {
        container.innerHTML = '<div class="loading">Loading...</div>';
    }

    showError(container, message) {
        container.innerHTML = `<div class="error-state">❌ ${message}</div>`;
    }

    startAutoRefresh() {
        // Refresh every 5 minutes
        this.refreshInterval = setInterval(() => {
            console.log('Correlation Heat Map: Auto-refreshing...');
            this.loadData();
        }, 5 * 60 * 1000);
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Auto-initialize when dashboard loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.querySelector('.dashboard-container')) {
            window.correlationHeatMap = new CorrelationHeatMap();
            window.correlationHeatMap.init();
        }
    });
} else {
    if (document.querySelector('.dashboard-container')) {
        window.correlationHeatMap = new CorrelationHeatMap();
        window.correlationHeatMap.init();
    }
}
