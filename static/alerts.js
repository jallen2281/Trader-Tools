/**
 * Price Alerts Manager - Local Storage Implementation (Phase 1)
 * Will be upgraded to database + real-time monitoring in Phase 2
 */

class AlertsManager {
    constructor() {
        this.storageKey = 'financial_alerts';
        this.alerts = this.load();
        this.checkInterval = null;
        this.notificationPermission = false;
        this.requestNotificationPermission();
    }

    async requestNotificationPermission() {
        if ('Notification' in window) {
            const permission = await Notification.requestPermission();
            this.notificationPermission = (permission === 'granted');
        }
    }

    load() {
        try {
            const data = localStorage.getItem(this.storageKey);
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Error loading alerts:', e);
            return [];
        }
    }

    save() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.alerts));
            this.notifyChange();
        } catch (e) {
            console.error('Error saving alerts:', e);
        }
    }

    add(symbol, type, price, notes = '') {
        symbol = symbol.toUpperCase().trim();
        
        const alert = {
            id: Date.now() + Math.random(),
            symbol,
            type, // 'high' or 'low'
            price: parseFloat(price),
            notes,
            created: Date.now(),
            triggered: false
        };

        this.alerts.push(alert);
        this.save();
        return alert;
    }

    remove(alertId) {
        const index = this.alerts.findIndex(a => a.id === alertId);
        if (index > -1) {
            this.alerts.splice(index, 1);
            this.save();
            return true;
        }
        return false;
    }

    getAll() {
        return [...this.alerts];
    }

    getActive() {
        return this.alerts.filter(a => !a.triggered);
    }

    getTriggered() {
        return this.alerts.filter(a => a.triggered);
    }

    clearTriggered() {
        this.alerts = this.alerts.filter(a => !a.triggered);
        this.save();
    }

    clear() {
        this.alerts = [];
        this.save();
    }

    notifyChange() {
        window.dispatchEvent(new CustomEvent('alertschange', {
            detail: { alerts: this.getAll() }
        }));
    }

    async checkAlerts() {
        const activeAlerts = this.getActive();
        if (activeAlerts.length === 0) return;

        // Get unique symbols
        const symbols = [...new Set(activeAlerts.map(a => a.symbol))];

        try {
            const response = await fetch('/api/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols: symbols,
                    period: '1d'
                })
            });

            if (response.ok) {
                const data = await response.json();
                const prices = data.symbols || {};

                for (const alert of activeAlerts) {
                    const symbolData = prices[alert.symbol];
                    if (!symbolData) continue;

                    const currentPrice = symbolData.current_price;
                    let triggered = false;

                    if (alert.type === 'high' && currentPrice >= alert.price) {
                        triggered = true;
                    } else if (alert.type === 'low' && currentPrice <= alert.price) {
                        triggered = true;
                    }

                    if (triggered) {
                        alert.triggered = true;
                        alert.triggeredAt = Date.now();
                        alert.triggeredPrice = currentPrice;
                        this.showNotification(alert, currentPrice);
                    }
                }

                this.save();
            }
        } catch (e) {
            console.error('Error checking alerts:', e);
        }
    }

    showNotification(alert, currentPrice) {
        const message = `${alert.symbol} ${alert.type === 'high' ? 'above' : 'below'} $${alert.price} - Current: $${currentPrice}`;
        
        // Browser notification
        if (this.notificationPermission) {
            new Notification('Price Alert Triggered!', {
                body: message,
                icon: '/static/icon.png',
                tag: alert.id
            });
        }

        // Visual notification
        this.showVisualNotification(message, alert.type);
    }

    showVisualNotification(message, type) {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `alert-toast ${type}`;
        toast.innerHTML = `
            <div class="toast-icon">${type === 'high' ? '📈' : '📉'}</div>
            <div class="toast-message">${message}</div>
        `;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'high' ? '#10b981' : '#ef4444'};
            color: white;
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10000;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 0.3s ease;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    startMonitoring(intervalMinutes = 1) {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
        }

        // Initial check
        this.checkAlerts();

        // Set up interval
        this.checkInterval = setInterval(() => {
            this.checkAlerts();
        }, intervalMinutes * 60 * 1000);

        console.log(`Alert monitoring started (checking every ${intervalMinutes} min)`);
    }

    stopMonitoring() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
            console.log('Alert monitoring stopped');
        }
    }
}

// Create global instance
window.alertsManager = new AlertsManager();

// Auto-start monitoring if alerts exist
if (window.alertsManager.getActive().length > 0) {
    window.alertsManager.startMonitoring(1); // Check every 1 minute
}
