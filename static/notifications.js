/**
 * AI Alert Suggestions & Notification Center
 * Phase 5: Proactive alert recommendations with one-click actions
 */

class NotificationCenter {
    constructor() {
        this.suggestions = [];
        this.notifications = [];   // durable feed of fired alerts
        this.unreadCount = 0;
        this.isOpen = false;
        this.refreshInterval = null;
        this.init();
    }

    init() {
        // Create notification center UI
        this.createUI();

        // Load initial suggestions + fired-alert notifications
        this.loadSuggestions();
        this.loadNotifications();
        this.loadInterval();

        // Auto-refresh every 2 minutes
        this.refreshInterval = setInterval(() => {
            this.loadSuggestions();
            this.loadNotifications();
        }, 120000);

        // Listen for custom events
        window.addEventListener('watchlistchange', () => {
            this.generateSuggestions();
        });
    }

    async loadNotifications() {
        try {
            const response = await fetch('/api/notifications?limit=20', {
                headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
            });
            if (response.ok) {
                const data = await response.json();
                this.notifications = data.notifications || [];
                this.unreadCount = data.unread_count || 0;
                this.updateBadge();
                if (this.isOpen) this.render();
            }
        } catch (e) {
            console.error('Error loading notifications:', e);
        }
    }

    async markRead(id) {
        try {
            await fetch(`/api/notifications/${id}/read`, {
                method: 'PUT',
                headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
            });
            const n = this.notifications.find(x => x.id === id);
            if (n && !n.read) { n.read = true; this.unreadCount = Math.max(0, this.unreadCount - 1); }
            this.updateBadge();
            this.render();
        } catch (e) {
            console.error('Error marking notification read:', e);
        }
    }

    async loadInterval() {
        try {
            const response = await fetch('/api/monitoring/interval', {
                headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
            });
            if (!response.ok) return;
            const data = await response.json();
            const sel = document.getElementById('alertIntervalSelect');
            if (!sel) return;
            sel.innerHTML = (data.options || []).map(o => {
                const locked = o.locked ? ' 🔒' : '';
                const sel2 = o.seconds === data.interval ? ' selected' : '';
                const dis = o.locked ? ' disabled' : '';
                return `<option value="${o.seconds}"${sel2}${dis}>${o.label}${locked}</option>`;
            }).join('');
            this._intervalMeta = data;
        } catch (e) {
            console.error('Error loading interval:', e);
        }
    }

    async changeInterval(seconds) {
        try {
            const response = await fetch('/api/monitoring/interval', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                },
                body: JSON.stringify({ interval: parseInt(seconds, 10) })
            });
            const data = await response.json().catch(() => ({}));
            if (response.ok) {
                const label = (this._intervalMeta?.options || []).find(o => o.seconds == seconds)?.label || `${seconds}s`;
                this.showToast(`✓ Alerts now checked every ${label}`, 'success');
            } else {
                this.showToast(data.error || 'Could not update interval', 'error');
                this.loadInterval();  // reset selection to server truth
            }
        } catch (e) {
            console.error('Error changing interval:', e);
            this.showToast('Could not update interval', 'error');
        }
    }

    async markAllRead() {
        try {
            await fetch('/api/notifications/read-all', {
                method: 'PUT',
                headers: { 'X-API-Key': localStorage.getItem('apiKey') || '' }
            });
            this.notifications.forEach(n => n.read = true);
            this.unreadCount = 0;
            this.updateBadge();
            this.render();
        } catch (e) {
            console.error('Error marking all read:', e);
        }
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
        bellButton.title = 'Notifications & AI Alert Suggestions';
        bellButton.onclick = () => this.toggle();
        
        headerActions.insertBefore(bellButton, headerActions.firstChild);

        // Create notification panel
        const panel = document.createElement('div');
        panel.id = 'notificationPanel';
        panel.className = 'notification-panel';
        panel.style.cssText = 'display: none;';
        
        panel.innerHTML = `
            <div class="notification-header">
                <h3>🔔 Notifications</h3>
                <div style="display: flex; gap: 10px;">
                    <button onclick="notificationCenter.generateSuggestions()" class="btn-icon" title="Refresh">🔄</button>
                    <button onclick="notificationCenter.close()" class="btn-icon">×</button>
                </div>
            </div>
            <div class="notification-body" id="notificationBody">
                <div class="loading-small">Loading suggestions...</div>
            </div>
            <div class="notification-footer" style="padding:10px 14px;border-top:1px solid var(--border,rgba(255,255,255,0.1));display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:.85em;">
                <span style="color:var(--text-secondary);white-space:nowrap;">⏱️ Check alerts every</span>
                <select id="alertIntervalSelect" onchange="notificationCenter.changeInterval(this.value)"
                        style="flex:1;max-width:160px;padding:4px 6px;border-radius:6px;background:var(--bg-secondary,#1e2230);color:inherit;border:1px solid var(--border,rgba(255,255,255,0.15));">
                    <option>Loading…</option>
                </select>
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
                    this.render();
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
        this.render();
    }

    // Compose the panel: fired-alert notifications on top, AI suggestions below.
    render() {
        const body = document.getElementById('notificationBody');
        if (!body) return;
        const notifHtml = this._notificationsHtml();
        const suggHtml = this._suggestionsHtml();
        if (!notifHtml && !suggHtml) {
            body.innerHTML = `
                <div class="empty-state" style="padding: 40px 20px; text-align: center;">
                    <div style="font-size: 3em; margin-bottom: 15px;">🔕</div>
                    <div style="color: var(--text-secondary); margin-bottom: 15px;">No notifications yet</div>
                    <button onclick="notificationCenter.generateSuggestions()" class="btn btn-primary">
                        Generate Suggestions
                    </button>
                </div>
            `;
            return;
        }
        body.innerHTML = notifHtml + suggHtml;
    }

    _notificationsHtml() {
        if (!this.notifications || this.notifications.length === 0) return '';
        const rows = this.notifications.map(n => {
            const when = n.created_at ? new Date(n.created_at).toLocaleString() : '';
            const pr = (n.priority || 'medium');
            const prColor = pr === 'critical' || pr === 'high' ? 'var(--danger)'
                : pr === 'low' ? 'var(--info)' : 'var(--warning)';
            const unreadDot = n.read ? '' :
                `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${prColor};margin-right:6px;"></span>`;
            const bg = n.read ? 'transparent' : 'rgba(245,158,11,0.08)';
            return `
                <div class="suggestion-item" style="background:${bg};" onclick="notificationCenter.markRead(${n.id})">
                    <div class="suggestion-icon">🔔</div>
                    <div class="suggestion-content">
                        <div class="suggestion-message">${unreadDot}${n.title || (n.symbol + ' alert')}</div>
                        ${n.message ? `<div class="suggestion-reason">${n.message}</div>` : ''}
                        <div class="suggestion-reason" style="opacity:.6;">${when}</div>
                    </div>
                </div>`;
        }).join('');
        const unread = this.unreadCount > 0
            ? `<button onclick="event.stopPropagation(); notificationCenter.markAllRead()" class="btn-icon" title="Mark all read" style="font-size:.8em;">Mark all read</button>`
            : '';
        return `
            <div class="suggestion-group">
                <div class="suggestion-group-header" style="display:flex;justify-content:space-between;align-items:center;color:var(--warning);">
                    <span>🔔 Recent Alerts${this.unreadCount ? ` (${this.unreadCount} new)` : ''}</span>
                    ${unread}
                </div>
                ${rows}
            </div>`;
    }

    close() {
        this.isOpen = false;
        const panel = document.getElementById('notificationPanel');
        panel.style.display = 'none';
    }

    updateBadge() {
        const badge = document.getElementById('notificationBadge');
        if (!badge) return;

        const count = this.unreadCount + this.suggestions.length;
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    // Returns the AI-suggestions section as an HTML string (empty string if none).
    _suggestionsHtml() {
        if (!this.suggestions || this.suggestions.length === 0) return '';

        const groupedByPriority = { 3: [], 2: [], 1: [] };
        this.suggestions.forEach(sugg => {
            groupedByPriority[sugg.priority]?.push(sugg);
        });

        let html = '';
        [3, 2, 1].forEach(priority => {
            const items = groupedByPriority[priority];
            if (items.length === 0) return;

            const priorityLabel = priority === 3 ? 'High Priority' : priority === 2 ? 'Medium Priority' : 'Low Priority';
            const priorityColor = priority === 3 ? 'var(--danger)' : priority === 2 ? 'var(--warning)' : 'var(--info)';

            html += `
                <div class="suggestion-group">
                    <div class="suggestion-group-header" style="color: ${priorityColor};">
                        🤖 AI Suggestions · ${priorityLabel}
                    </div>
            `;

            items.forEach(sugg => {
                html += this.renderSuggestion(sugg);
            });

            html += '</div>';
        });

        return html;
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
                this.render();
                
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
                this.render();
                
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
