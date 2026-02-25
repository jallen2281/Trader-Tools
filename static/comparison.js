/**
 * Multi-Symbol Comparison Tool
 * Allows comparing multiple stocks on one normalized chart
 */

class ComparisonTool {
    constructor() {
        this.symbols = [];
        this.maxSymbols = 10;
    }

    addSymbol(symbol) {
        symbol = symbol.toUpperCase().trim();
        if (!symbol) return false;
        
        if (this.symbols.length >= this.maxSymbols) {
            alert(`Maximum ${this.maxSymbols} symbols allowed`);
            return false;
        }

        if (!this.symbols.includes(symbol)) {
            this.symbols.push(symbol);
            this.notifyChange();
            return true;
        }
        return false;
    }

    removeSymbol(symbol) {
        symbol = symbol.toUpperCase().trim();
        const index = this.symbols.indexOf(symbol);
        if (index > -1) {
            this.symbols.splice(index, 1);
            this.notifyChange();
            return true;
        }
        return false;
    }

    clear() {
        this.symbols = [];
        this.notifyChange();
    }

    getSymbols() {
        return [...this.symbols];
    }

    notifyChange() {
        window.dispatchEvent(new CustomEvent('comparisonchange', {
            detail: { symbols: this.getSymbols() }
        }));
    }

    async generateChart(period = '6mo', normalize = true) {
        if (this.symbols.length === 0) {
            alert('Add at least one symbol to compare');
            return null;
        }

        try {
            const response = await fetch('/api/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols: this.symbols,
                    period: period,
                    normalize: normalize,
                    include_chart: true
                })
            });

            if (response.ok) {
                const data = await response.json();
                return data;
            } else {
                const error = await response.json();
                throw new Error(error.error || 'Failed to generate comparison chart');
            }
        } catch (e) {
            console.error('Error generating comparison chart:', e);
            throw e;
        }
    }
}

// Create global instance
window.comparisonTool = new ComparisonTool();
