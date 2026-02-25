"""
Politician Trading Data Fetcher
Tracks Congressional and Senate stock trades for copy trading analysis
"""

import yfinance as yf
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class PoliticianTradeTracker:
    """Track and analyze politician stock trades."""
    
    def __init__(self):
        self.trades_cache = []
        self.last_update = None
        
    def get_recent_trades(self, days=30):
        """
        Get recent politician trades.
        In production, this would fetch from APIs like:
        - Capitol Trades API
        - Quiver Quantitative API
        - Senate/House disclosure reports
        
        For now, returns sample data based on real politician trading patterns.
        """
        try:
            # Sample data based on real patterns
            # In production, replace with actual API calls
            trades = self._get_sample_trades()
            
            # Enrich with current prices
            enriched_trades = []
            for trade in trades:
                try:
                    current_data = self._get_current_price(trade['symbol'])
                    trade.update(current_data)
                    enriched_trades.append(trade)
                except Exception as e:
                    logger.warning(f"Could not enrich {trade['symbol']}: {e}")
                    enriched_trades.append(trade)
            
            return enriched_trades
            
        except Exception as e:
            logger.error(f"Error fetching politician trades: {e}")
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
