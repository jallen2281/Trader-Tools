/**
 * Multi-Watchlist Manager - Local Storage Implementation
 * Supports multiple named watchlists with portfolio auto-sync
 */

class WatchlistManager {
    constructor() {
        this.storageKey = 'financial_watchlists';
        this.currentWatchlistKey = 'current_watchlist';
        this.watchlists = this.load();
        this.currentWatchlist = localStorage.getItem(this.currentWatchlistKey) || 'default';
        
        // Ensure default watchlist exists
        if (!this.watchlists['default']) {
            this.watchlists['default'] = [];
            this.save();
        }
    }

    load() {
        try {
            const data = localStorage.getItem(this.storageKey);
            if (data) {
                return JSON.parse(data);
            } else {
                // Migrate old single watchlist if exists
                const oldWatchlist = localStorage.getItem('financial_watchlist');
                if (oldWatchlist) {
                    return { 'default': JSON.parse(oldWatchlist) };
                }
            }
            return { 'default': [] };
        } catch (e) {
            console.error('Error loading watchlists:', e);
            return { 'default': [] };
        }
    }

    save() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.watchlists));
            this.notifyChange();
        } catch (e) {
            console.error('Error saving watchlists:', e);
        }
    }

    // Watchlist management
    createWatchlist(name) {
        name = name.trim();
        if (!name || this.watchlists[name]) return false;
        this.watchlists[name] = [];
        this.save();
        return true;
    }

    deleteWatchlist(name) {
        if (name === 'default' || name === 'portfolio') return false;
        if (this.watchlists[name]) {
            delete this.watchlists[name];
            if (this.currentWatchlist === name) {
                this.setCurrentWatchlist('default');
            }
            this.save();
            return true;
        }
        return false;
    }

    renameWatchlist(oldName, newName) {
        newName = newName.trim();
        if (oldName === 'portfolio' || oldName === 'default') return false;
        if (!newName || newName === oldName || this.watchlists[newName]) return false;
        if (this.watchlists[oldName]) {
            this.watchlists[newName] = this.watchlists[oldName];
            delete this.watchlists[oldName];
            if (this.currentWatchlist === oldName) {
                this.setCurrentWatchlist(newName);
            }
            this.save();
            return true;
        }
        return false;
    }

    setCurrentWatchlist(name) {
        if (this.watchlists[name] || name === 'portfolio') {
            this.currentWatchlist = name;
            localStorage.setItem(this.currentWatchlistKey, name);
            this.notifyChange();
            return true;
        }
        return false;
    }

    getCurrentWatchlist() {
        return this.currentWatchlist;
    }

    getAllWatchlistNames() {
        return Object.keys(this.watchlists).filter(name => name !== 'portfolio');
    }

    // Symbol management for current watchlist
    add(symbol) {
        if (this.currentWatchlist === 'portfolio') return false; // Can't edit portfolio
        symbol = symbol.toUpperCase().trim();
        if (!symbol) return false;
        
        const list = this.watchlists[this.currentWatchlist] || [];
        if (!list.includes(symbol)) {
            list.push(symbol);
            this.watchlists[this.currentWatchlist] = list;
            this.save();
            return true;
        }
        return false;
    }

    remove(symbol) {
        if (this.currentWatchlist === 'portfolio') return false; // Can't edit portfolio
        symbol = symbol.toUpperCase().trim();
        const list = this.watchlists[this.currentWatchlist] || [];
        const index = list.indexOf(symbol);
        if (index > -1) {
            list.splice(index, 1);
            this.watchlists[this.currentWatchlist] = list;
            this.save();
            return true;
        }
        return false;
    }

    getAll() {
        if (this.currentWatchlist === 'portfolio') {
            return []; // Will be populated from API
        }
        return [...(this.watchlists[this.currentWatchlist] || [])];
    }

    has(symbol) {
        const list = this.watchlists[this.currentWatchlist] || [];
        return list.includes(symbol.toUpperCase());
    }

    clear() {
        if (this.currentWatchlist === 'portfolio') return false;
        this.watchlists[this.currentWatchlist] = [];
        this.save();
    }

    notifyChange() {
        // Dispatch custom event for UI updates
        window.dispatchEvent(new CustomEvent('watchlistchange', {
            detail: { 
                watchlist: this.getAll(),
                currentName: this.currentWatchlist,
                allNames: this.getAllWatchlistNames()
            }
        }));
    }

    // Fetch current prices for all symbols in current watchlist
    async fetchPrices(symbolsArray = null) {
        const symbols = symbolsArray || this.getAll();
        if (symbols.length === 0) return {};
        
        try {
            const response = await fetch('/api/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols: symbols,
                    period: '5d'  // Use 5d to get proper change percentage
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                return data.symbols || {};
            }
        } catch (e) {
            console.error('Error fetching watchlist prices:', e);
        }
        return {};
    }

    // Fetch portfolio holdings
    async fetchPortfolioHoldings() {
        try {
            const response = await fetch('/api/portfolio/list');
            if (response.ok) {
                const data = await response.json();
                return data.holdings || [];
            }
        } catch (e) {
            console.error('Error fetching portfolio holdings:', e);
        }
        return [];
    }
}

// Create global instance
window.watchlistManager = new WatchlistManager();

