"""
Politician Trading Data Fetcher
Tracks Congressional and Senate stock trades for copy trading analysis
"""

import yfinance as yf
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Free, no-key congressional trades feed (House Clerk + Senate eFD, normalized daily).
KADOA_TRADES_URL = "https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/trades.json"


class PoliticianTradeTracker:
    """Track and analyze politician stock trades."""
    
    def __init__(self):
        self.trades_cache = None
        self.last_update = None
        self.cache_ttl = timedelta(hours=6)  # Kadoa feed refreshes ~daily

    def get_recent_trades(self, days=30):
        """Recent congressional trades, filtered to the last `days` by filing date.

        Uses real data from the free Kadoa feed (House Clerk + Senate eFD), cached
        for cache_ttl. Falls back to sample data only if the feed is unreachable.
        """
        try:
            all_trades = self._get_all_trades()
            cutoff = datetime.now() - timedelta(days=days)
            recent = []
            for t in all_trades:
                ds = t.get('filed_date') or t.get('date') or ''
                try:
                    td = datetime.strptime(ds[:10], '%Y-%m-%d')
                except Exception:
                    td = None
                if td is None or td >= cutoff:
                    recent.append(t)
            return recent
        except Exception as e:
            logger.error(f"Error fetching politician trades: {e}")
            return self._get_sample_trades()

    def _get_all_trades(self):
        """Full normalized trade list, cached for cache_ttl (real data or fallback)."""
        if (self.trades_cache is not None and self.last_update
                and (datetime.now() - self.last_update) < self.cache_ttl):
            return self.trades_cache
        trades = self._fetch_kadoa_trades()
        if not trades:
            logger.warning("Kadoa feed empty/unreachable — using sample-data fallback")
            trades = self._get_sample_trades()
        self.trades_cache = trades
        self.last_update = datetime.now()
        return trades

    def _fetch_kadoa_trades(self):
        """Fetch + normalize real congressional trades from the free Kadoa JSON feed.

        Returns [] on any failure so the caller falls back to sample data.
        Keeps only common-stock/ETF purchases and sales (drops options, bonds, etc.).
        """
        try:
            resp = requests.get(KADOA_TRADES_URL, timeout=15,
                                headers={'User-Agent': 'trader-tools'})
            if resp.status_code != 200:
                logger.warning(f"Kadoa feed HTTP {resp.status_code}")
                return []
            raw = resp.json()
            rows = raw if isinstance(raw, list) else (raw.get('trades') or [])
            party_map = {'R': 'Republican', 'D': 'Democrat', 'I': 'Independent'}
            out = []
            for i, r in enumerate(rows):
                ticker = (r.get('ticker') or '').upper().strip()
                if not ticker:
                    continue
                asset_type = (r.get('asset_type') or '').strip()
                if asset_type and asset_type not in ('Stock', 'ST', 'Common Stock', 'ETF', 'Equity'):
                    continue
                ttype = (r.get('transaction_type') or '').lower()
                if ttype.startswith('purchase') or ttype == 'buy':
                    transaction = 'Purchase'
                elif 'sale' in ttype or ttype == 'sell':
                    transaction = 'Sale'
                else:
                    continue
                out.append({
                    'id': f"{r.get('filer_id', '')}-{ticker}-{i}",
                    'politician': r.get('filer_name') or 'Unknown',
                    'party': party_map.get((r.get('party') or '').upper(), r.get('party') or 'Unknown'),
                    'chamber': (r.get('chamber') or '').capitalize(),
                    'state': r.get('state') or '',
                    'symbol': ticker,
                    'company': r.get('asset_name') or ticker,
                    'transaction': transaction,
                    'amount_range': r.get('amount_range_label') or '',
                    'amount_min': r.get('amount_range_low') or 0,
                    'amount_max': r.get('amount_range_high') or 0,
                    'date': (r.get('transaction_date') or '')[:10],
                    'filed_date': (r.get('filing_date') or '')[:10],
                    'disclosure_date': (r.get('filing_date') or '')[:10],
                    'asset_type': asset_type or 'Stock',
                    'owner': r.get('owner') or '',
                    'excess_since': r.get('excess_since'),
                    'is_late': r.get('is_late'),
                    'current_price': None,
                    'return_pct': 0,
                    'purchase_price': None,
                })
            logger.info(f"Kadoa feed: normalized {len(out)} congressional stock trades")
            return out
        except Exception as e:
            logger.warning(f"Kadoa feed fetch failed ({e}); falling back to sample data")
            return []
    
    def _get_current_price(self, symbol):
        """Get current price and return for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='5d')
            
            if hist.empty:
                return {'current_price': None, 'return_pct': 0}
            
            current_price = hist['Close'].iloc[-1]
            return {
                'current_price': round(float(current_price), 2),
                'return_pct': 0  # Calculate based on purchase price
            }
        except:
            return {'current_price': None, 'return_pct': 0}
    
    def _get_sample_trades(self):
        """
        Sample politician trades based on real patterns.
        Replace with actual API data in production.
        """
        base_date = datetime.now()
        
        return [
            {
                'id': 1,
                'politician': 'Nancy Pelosi',
                'party': 'Democrat',
                'chamber': 'House',
                'state': 'CA',
                'symbol': 'NVDA',
                'company': 'NVIDIA Corporation',
                'transaction': 'Purchase',
                'amount_range': '$1M - $5M',
                'amount_min': 1000000,
                'amount_max': 5000000,
                'date': (base_date - timedelta(days=5)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Spouse',
                'purchase_price': 875.50,
            },
            {
                'id': 2,
                'politician': 'Dan Crenshaw',
                'party': 'Republican',
                'chamber': 'House',
                'state': 'TX',
                'symbol': 'PLTR',
                'company': 'Palantir Technologies',
                'transaction': 'Purchase',
                'amount_range': '$250K - $500K',
                'amount_min': 250000,
                'amount_max': 500000,
                'date': (base_date - timedelta(days=8)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Self',
                'purchase_price': 58.25,
            },
            {
                'id': 3,
                'politician': 'Tommy Tuberville',
                'party': 'Republican',
                'chamber': 'Senate',
                'state': 'AL',
                'symbol': 'MSFT',
                'company': 'Microsoft Corporation',
                'transaction': 'Purchase',
                'amount_range': '$500K - $1M',
                'amount_min': 500000,
                'amount_max': 1000000,
                'date': (base_date - timedelta(days=12)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=6)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=5)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Self',
                'purchase_price': 415.75,
            },
            {
                'id': 4,
                'politician': 'Josh Gottheimer',
                'party': 'Democrat',
                'chamber': 'House',
                'state': 'NJ',
                'symbol': 'GOOGL',
                'company': 'Alphabet Inc.',
                'transaction': 'Purchase',
                'amount_range': '$100K - $250K',
                'amount_min': 100000,
                'amount_max': 250000,
                'date': (base_date - timedelta(days=7)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Joint',
                'purchase_price': 175.30,
            },
            {
                'id': 5,
                'politician': 'Michael McCaul',
                'party': 'Republican',
                'chamber': 'House',
                'state': 'TX',
                'symbol': 'AAPL',
                'company': 'Apple Inc.',
                'transaction': 'Sale',
                'amount_range': '$500K - $1M',
                'amount_min': 500000,
                'amount_max': 1000000,
                'date': (base_date - timedelta(days=10)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=5)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Spouse',
                'purchase_price': 225.50,
            },
            {
                'id': 6,
                'politician': 'Mark Green',
                'party': 'Republican',
                'chamber': 'House',
                'state': 'TN',
                'symbol': 'BA',
                'company': 'Boeing Company',
                'transaction': 'Purchase',
                'amount_range': '$50K - $100K',
                'amount_min': 50000,
                'amount_max': 100000,
                'date': (base_date - timedelta(days=15)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=8)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=7)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Self',
                'purchase_price': 178.25,
            },
            {
                'id': 7,
                'politician': 'Debbie Stabenow',
                'party': 'Democrat',
                'chamber': 'Senate',
                'state': 'MI',
                'symbol': 'F',
                'company': 'Ford Motor Company',
                'transaction': 'Purchase',
                'amount_range': '$15K - $50K',
                'amount_min': 15000,
                'amount_max': 50000,
                'date': (base_date - timedelta(days=20)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=12)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=11)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Joint',
                'purchase_price': 12.85,
            },
            {
                'id': 8,
                'politician': 'Ro Khanna',
                'party': 'Democrat',
                'chamber': 'House',
                'state': 'CA',
                'symbol': 'TSLA',
                'company': 'Tesla Inc.',
                'transaction': 'Sale',
                'amount_range': '$250K - $500K',
                'amount_min': 250000,
                'amount_max': 500000,
                'date': (base_date - timedelta(days=18)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=10)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=9)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Spouse',
                'purchase_price': 385.60,
            },
            {
                'id': 9,
                'politician': 'Pat Fallon',
                'party': 'Republican',
                'chamber': 'House',
                'state': 'TX',
                'symbol': 'AMD',
                'company': 'Advanced Micro Devices',
                'transaction': 'Purchase',
                'amount_range': '$100K - $250K',
                'amount_min': 100000,
                'amount_max': 250000,
                'date': (base_date - timedelta(days=6)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Self',
                'purchase_price': 165.40,
            },
            {
                'id': 10,
                'politician': 'Marjorie Taylor Greene',
                'party': 'Republican',
                'chamber': 'House',
                'state': 'GA',
                'symbol': 'DJT',
                'company': 'Trump Media & Technology',
                'transaction': 'Purchase',
                'amount_range': '$50K - $100K',
                'amount_min': 50000,
                'amount_max': 100000,
                'date': (base_date - timedelta(days=14)).strftime('%Y-%m-%d'),
                'filed_date': (base_date - timedelta(days=7)).strftime('%Y-%m-%d'),
                'disclosure_date': (base_date - timedelta(days=6)).strftime('%Y-%m-%d'),
                'asset_type': 'Stock',
                'owner': 'Self',
                'purchase_price': 45.20,
            },
        ]
    
    def get_politician_performance(self, politician_name=None):
        """
        Calculate performance metrics for politicians.
        Returns aggregated stats by politician.
        """
        trades = self.get_recent_trades(days=90)
        
        if politician_name:
            trades = [t for t in trades if t['politician'] == politician_name]
        
        # Group by politician and calculate metrics
        politician_stats = {}
        
        for trade in trades:
            pol = trade['politician']
            if pol not in politician_stats:
                politician_stats[pol] = {
                    'politician': pol,
                    'party': trade['party'],
                    'chamber': trade['chamber'],
                    'state': trade['state'],
                    'total_trades': 0,
                    'purchases': 0,
                    'sales': 0,
                    'total_volume': 0,
                    'top_symbols': [],
                    'recent_trades': []
                }
            
            stats = politician_stats[pol]
            stats['total_trades'] += 1
            
            if trade['transaction'] == 'Purchase':
                stats['purchases'] += 1
            else:
                stats['sales'] += 1
            
            stats['total_volume'] += (trade['amount_min'] + trade['amount_max']) / 2
            stats['recent_trades'].append(trade)
        
        return list(politician_stats.values())
    
    def search_by_symbol(self, symbol):
        """Find all politician trades for a specific symbol."""
        trades = self.get_recent_trades(days=90)
        return [t for t in trades if t['symbol'].upper() == symbol.upper()]
    
    def get_trending_symbols(self):
        """Get most traded symbols by politicians."""
        trades = self.get_recent_trades(days=30)
        
        symbol_counts = {}
        for trade in trades:
            if trade['transaction'] == 'Purchase':  # Only purchases
                symbol = trade['symbol']
                if symbol not in symbol_counts:
                    symbol_counts[symbol] = {
                        'symbol': symbol,
                        'company': trade['company'],
                        'trade_count': 0,
                        'politicians': set(),
                        'total_volume': 0
                    }
                symbol_counts[symbol]['trade_count'] += 1
                symbol_counts[symbol]['politicians'].add(trade['politician'])
                symbol_counts[symbol]['total_volume'] += (trade['amount_min'] + trade['amount_max']) / 2
        
        # Convert sets to lists for JSON serialization
        for symbol in symbol_counts.values():
            symbol['politicians'] = list(symbol['politicians'])
            symbol['politician_count'] = len(symbol['politicians'])
        
        # Sort by trade count
        trending = sorted(symbol_counts.values(), key=lambda x: x['trade_count'], reverse=True)
        
        return trending[:10]
