/**
 * AI Alert Suggestions & Notification Center
 * Phase 5: Proactive alert recommendations with one-click actions
 */

class NotificationCenter {
    constructor() {
        this.suggestions = [];
        this.isOpen = false;
        this.refreshInterval = null;
        this.init();
    }

    init() {
        // Create notification center UI
        this.createUI();
        
        // Load initial suggestions
        this.loadSuggestions();
        
        // Auto-refresh every 2 minutes
        this.refreshInterval = setInterval(() => this.loadSuggestions(), 120000);
        
        // Listen for custom events
        window.addEventListener('watchlistchange', () => {
            this.generateSuggestions();
        });
    }

    createUI() {
        // Add notification bell to header
        const headerActions = document.querySelector('.header-actions');
        if (!headerActions) return;

        const bellButton = document.createElement('button');
        bellButton.id = 'notificationBell';
        bellButton.className = 'btn btn-icon';
        bellButton.style.position = 'relative';
        bellButton.innerHTML = '🔔 <span id="notificationBadge" class="notification-badge" style="display: none;">0</span>';
        bellButton.title = 'AI Alert Suggestions';
        bellButton.onclick = () => this.toggle();
        
        headerActions.insertBefore(bellButton, headerActions.firstChild);

        // Create notification panel
        const panel = document.createElement('div');
        panel.id = 'notificationPanel';
        panel.className = 'notification-panel';
        panel.style.cssText = 'display: none;';
        
        panel.innerHTML = `
            <div class="notification-header">
                <h3>🤖 AI Alert Suggestions</h3>
                <div style="display: flex; gap: 10px;">
                    <button onclick="notificationCenter.generateSuggestions()" class="btn-icon" title="Refresh">🔄</button>
                    <button onclick="notificationCenter.close()" class="btn-icon">×</button>
                </div>
            </div>
            <div class="notification-body" id="notificationBody">
                <div class="loading-small">Loading suggestions...</div>
            </div>
        `;
        
        document.body.appendChild(panel);

        // Click outside to close
        document.addEventListener('click', (e) => {
            const panel = document.getElementById('notificationPanel');
            const bell = document.getElementById('notificationBell');
            if (this.isOpen && !panel.contains(e.target) && !bell.contains(e.target)) {
                this.close();
            }
        });
    }

    async loadSuggestions() {
        try {
            const response = await fetch('/api/alert-suggestions', {
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });
            if (response.ok) {
                const data = await response.json();
                this.suggestions = data.suggestions || [];
                this.updateBadge();
                if (this.isOpen) {
                    this.renderSuggestions();
                }
            }
        } catch (e) {
            console.error('Error loading suggestions:', e);
        }
    }

    async generateSuggestions() {
        try {
            // Get current watchlist symbols
            let symbols = [];
            
            // Try to get from window.watchlistManager if available
            if (window.watchlistManager && typeof window.watchlistManager.getAll === 'function') {
                symbols = window.watchlistManager.getAll();
            } else {
                // Fallback: Read directly from localStorage
                try {
                    const watchlistData = localStorage.getItem('financial_watchlist');
                    if (watchlistData) {
                        symbols = JSON.parse(watchlistData);
                    }
                } catch (e) {
                    console.warn('Could not load watchlist from localStorage:', e);
                }
            }
            
            const response = await fetch('/api/alert-suggestions/generate', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                },
                body: JSON.stringify({ symbols })
            });
            
            if (response.ok) {
                await this.loadSuggestions();
                this.showToast('✓ Generated new AI suggestions', 'success');
            }
        } catch (e) {
            console.error('Error generating suggestions:', e);
            this.showToast('Failed to generate suggestions', 'error');
        }
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        this.isOpen = true;
        const panel = document.getElementById('notificationPanel');
        panel.style.display = 'block';
        this.renderSuggestions();
    }

    close() {
        this.isOpen = false;
        const panel = document.getElementById('notificationPanel');
        panel.style.display = 'none';
    }

    updateBadge() {
        const badge = document.getElementById('notificationBadge');
        if (!badge) return;

        const count = this.suggestions.length;
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    renderSuggestions() {
        const body = document.getElementById('notificationBody');
        if (!body) return;

        if (this.suggestions.length === 0) {
            body.innerHTML = `
                <div class="empty-state" style="padding: 40px 20px; text-align: center;">
                    <div style="font-size: 3em; margin-bottom: 15px;">🎯</div>
                    <div style="color: var(--text-secondary); margin-bottom: 15px;">No AI suggestions yet</div>
                    <button onclick="notificationCenter.generateSuggestions()" class="btn btn-primary">
                        Generate Suggestions
                    </button>
                </div>
            `;
            return;
        }

        const groupedByPriority = {
            3: [],  // High priority
            2: [],  // Medium priority
            1: []   // Low priority
        };

        this.suggestions.forEach(sugg => {
            groupedByPriority[sugg.priority]?.push(sugg);
        });

        let html = '';

        // High priority first
        [3, 2, 1].forEach(priority => {
            const items = groupedByPriority[priority];
            if (items.length === 0) return;

            const priorityLabel = priority === 3 ? 'High Priority' : priority === 2 ? 'Medium Priority' : 'Low Priority';
            const priorityColor = priority === 3 ? 'var(--danger)' : priority === 2 ? 'var(--warning)' : 'var(--info)';

            html += `
                <div class="suggestion-group">
                    <div class="suggestion-group-header" style="color: ${priorityColor};">
                        ${priorityLabel}
                    </div>
            `;

            items.forEach(sugg => {
                html += this.renderSuggestion(sugg);
            });

            html += '</div>';
        });

        body.innerHTML = html;
    }

    renderSuggestion(sugg) {
        const priorityClass = sugg.priority === 3 ? 'high' : sugg.priority === 2 ? 'medium' : 'low';
        
        return `
            <div class="suggestion-item priority-${priorityClass}">
                <div class="suggestion-icon">${sugg.icon}</div>
                <div class="suggestion-content">
                    <div class="suggestion-message">${sugg.message}</div>
                    ${sugg.reason ? `<div class="suggestion-reason">${sugg.reason}</div>` : ''}
                    ${sugg.trigger_price ? `
                        <div class="suggestion-price">
                            Alert when ${sugg.direction} $${sugg.trigger_price.toFixed(2)}
                        </div>
                    ` : ''}
                </div>
                <div class="suggestion-actions">
                    <button onclick="notificationCenter.accept(${sugg.id})" class="btn-accept" title="Accept & Create Alert">
                        ✓ Add
                    </button>
                    <button onclick="notificationCenter.dismiss(${sugg.id})" class="btn-dismiss" title="Dismiss">
                        ×
                    </button>
                </div>
            </div>
        `;
    }

    async accept(suggestionId) {
        try {
            const response = await fetch(`/api/alert-suggestions/${suggestionId}/accept`, {
                method: 'POST',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (response.ok) {
                // Remove from local list
                this.suggestions = this.suggestions.filter(s => s.id !== suggestionId);
                this.updateBadge();
                this.renderSuggestions();
                
                this.showToast('✓ Alert created successfully!', 'success');
                
                // Refresh alerts if on portfolio page
                if (typeof loadActiveAlerts === 'function') {
                    loadActiveAlerts();
                }
            } else {
                this.showToast('Failed to create alert', 'error');
            }
        } catch (e) {
            console.error('Error accepting suggestion:', e);
            this.showToast('Error creating alert', 'error');
        }
    }

    async dismiss(suggestionId) {
        try {
            const response = await fetch(`/api/alert-suggestions/${suggestionId}/dismiss`, {
                method: 'POST',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (response.ok) {
                // Remove from local list
                this.suggestions = this.suggestions.filter(s => s.id !== suggestionId);
                this.updateBadge();
                this.renderSuggestions();
                
                this.showToast('Suggestion dismissed', 'info');
            } else {
                this.showToast('Failed to dismiss suggestion', 'error');
            }
        } catch (e) {
            console.error('Error dismissing suggestion:', e);
        }
    }

    showToast(message, type = 'info') {
        const colors = {
            success: '#4CAF50',
            error: '#ef4444',
            info: '#3b82f6',
            warning: '#f59e0b'
        };

        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${colors[type] || colors.info};
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            z-index: 10001;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideInRight 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Create global instance once
let notificationCenter;

// Initialize when DOM is ready (single initialization)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (!window.notificationCenter) {
            notificationCenter = new NotificationCenter();
            window.notificationCenter = notificationCenter;
        }
    });
} else {
    if (!window.notificationCenter) {
        notificationCenter = new NotificationCenter();
        window.notificationCenter = notificationCenter;
    }
}
