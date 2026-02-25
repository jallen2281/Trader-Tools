"""
Volatility Index Monitor - Phase 4
Tracks VIX and other volatility indices for market context
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
from pathlib import Path
import time

logger = logging.getLogger(__name__)

class VolatilityMonitor:
    """
    Monitor market volatility indices (VIX, VXN, RVX) for trading context
    """
    
    def __init__(self):
        self.volatility_indices = {
            'VIX': '^VIX',      # S&P 500 Volatility
            'VXN': '^VXN',      # Nasdaq 100 Volatility
            'RVX': '^RVX'       # Russell 2000 Volatility
        }
        
        self.major_indices = {
            'SPX': '^GSPC',     # S&P 500
            'NDX': '^IXIC',     # Nasdaq Composite
            'DJI': '^DJI'       # Dow Jones
        }
        
        # VIX thresholds for regime classification
        self.vix_thresholds = {
            'low': 15,
            'normal': 20,
            'elevated': 30,
            'high': 40
        }
        
        # Cache for volatile stocks (refresh every 15 minutes)
        self.volatile_stocks_cache = None
        self.cache_timestamp = None
        self.cache_duration = 900  # 15 minutes
        
        # Popular liquid stocks to scan for volatility
        self.stock_universe = [
            # FAANG + Tech Giants
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'NFLX',
            # Mega Cap
            'JPM', 'V', 'MA', 'WMT', 'JNJ', 'UNH', 'XOM', 'CVX', 'PG', 'HD',
            # Growth & Tech
            'CRM', 'ORCL', 'ADBE', 'CSCO', 'ACN', 'AVGO', 'QCOM', 'TXN', 'INTU', 'NOW',
            # High Beta
            'COIN', 'RIOT', 'MARA', 'PLTR', 'MRNA', 'BNTX', 'CRSP', 'EDIT', 'NTLA', 'BEAM',
            # Meme/Volatile
            'GME', 'AMC', 'BB', 'BBBY', 'BYND', 'SPCE', 'DKNG', 'PENN', 'LCID', 'RIVN',
            # Chinese ADRs
            'BABA', 'BIDU', 'JD', 'PDD', 'NIO', 'XPEV', 'LI', 'BILI', 'IQ', 'TME',
            # Finance
            'BAC', 'C', 'GS', 'MS', 'WFC', 'AXP', 'BLK', 'SCHW', 'SOFI', 'AFRM',
            # Energy
            'OXY', 'HAL', 'SLB', 'MPC', 'PSX', 'VLO', 'DVN', 'FANG', 'EOG', 'COP',
            # Healthcare/Biotech
            'ABBV', 'BMY', 'GILD', 'AMGN', 'REGN', 'VRTX', 'BIIB', 'ILMN', 'ALNY', 'SGEN',
            # Consumer
            'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'TGT', 'LOW', 'F', 'GM', 'UBER',
            # Semiconductors
            'MU', 'AMAT', 'LRCX', 'KLAC', 'ASML', 'TSM', 'MRVL', 'ON', 'MPWR', 'WOLF',
            # ETFs
            'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'GLD', 'SLV', 'USO', 'TLT', 'HYG',
            # Additional Volatile
            'SNAP', 'PINS', 'ZM', 'SHOP', 'SQ', 'DASH', 'LYFT', 'HOOD', 'RBLX', 'U',
            # Cryptocurrencies (Major)
            'BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 'SOL-USD', 'DOGE-USD', 'DOT-USD',
            # Cryptocurrencies (Mid-Cap)
            'MATIC-USD', 'AVAX-USD', 'LINK-USD', 'UNI-USD', 'ATOM-USD', 'LTC-USD', 'ALGO-USD', 'XLM-USD',
            # Cryptocurrencies (High Volatility)
            'SHIB-USD', 'APE-USD', 'SAND-USD', 'MANA-USD', 'AXS-USD', 'GALA-USD', 'ENJ-USD', 'CRV-USD'
        ]
    
    def get_vix_data(self):
        """
        Fetch current VIX data with interpretation
        
        Returns:
            dict: VIX level, change, percentile, and interpretation
        """
        try:
            vix = yf.Ticker('^VIX')
            
            # Get current data
            current_data = vix.history(period='1d')
            if current_data.empty:
                logger.warning("No current VIX data available")
                return None
            
            current_vix = current_data['Close'].iloc[-1]
            
            # Get historical data for percentile calculation
            hist_data = vix.history(period='1y')
            if len(hist_data) > 0:
                vix_percentile = (hist_data['Close'] < current_vix).sum() / len(hist_data) * 100
            else:
                vix_percentile = 50  # Default to middle if no history
            
            # Calculate daily change
            if len(current_data) > 0:
                open_vix = current_data['Open'].iloc[-1]
                vix_change = current_vix - open_vix
                vix_change_pct = (vix_change / open_vix * 100) if open_vix > 0 else 0
            else:
                vix_change = 0
                vix_change_pct = 0
            
            # Classify volatility regime
            regime = self.classify_volatility_regime(current_vix)
            
            # Generate interpretation
            interpretation = self._interpret_vix(current_vix, vix_change, vix_percentile)
            
            return {
                'current': round(current_vix, 2),
                'change': round(vix_change, 2),
                'change_pct': round(vix_change_pct, 2),
                'percentile': round(vix_percentile, 1),
                'regime': regime,
                'interpretation': interpretation,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error fetching VIX data: {str(e)}")
            return None
    
    def get_all_volatility_indices(self):
        """
        Fetch all major volatility indices
        
        Returns:
            dict: Data for VIX, VXN, RVX
        """
        results = {}
        
        for name, symbol in self.volatility_indices.items():
            try:
                ticker = yf.Ticker(symbol)
                current_data = ticker.history(period='1d')
                
                if not current_data.empty:
                    current = current_data['Close'].iloc[-1]
                    open_price = current_data['Open'].iloc[-1]
                    change = current - open_price
                    change_pct = (change / open_price * 100) if open_price > 0 else 0
                    
                    results[name] = {
                        'symbol': symbol,
                        'current': round(current, 2),
                        'change': round(change, 2),
                        'change_pct': round(change_pct, 2)
                    }
                else:
                    logger.warning(f"No data for {name} ({symbol})")
                    
            except Exception as e:
                logger.error(f"Error fetching {name}: {str(e)}")
        
        return results
    
    def classify_volatility_regime(self, vix_level):
        """
        Classify current volatility regime
        
        Args:
            vix_level: Current VIX level
            
        Returns:
            str: Regime classification
        """
        if vix_level < self.vix_thresholds['low']:
            return 'low'
        elif vix_level < self.vix_thresholds['normal']:
            return 'normal'
        elif vix_level < self.vix_thresholds['elevated']:
            return 'elevated'
        elif vix_level < self.vix_thresholds['high']:
            return 'high'
        else:
            return 'extreme'
    
    def get_market_snapshot(self):
        """
        Quick snapshot of market conditions
        
        Returns:
            dict: Market indices, VIX, and overall sentiment
        """
        try:
            results = {
                'indices': {},
                'volatility': {},
                'timestamp': datetime.now()
            }
            
            # Get major indices
            for name, symbol in self.major_indices.items():
                try:
                    ticker = yf.Ticker(symbol)
                    data = ticker.history(period='1d')
                    
                    if not data.empty:
                        current = data['Close'].iloc[-1]
                        open_price = data['Open'].iloc[-1]
                        change = current - open_price
                        change_pct = (change / open_price * 100) if open_price > 0 else 0
                        
                        results['indices'][name] = {
                            'symbol': symbol,
                            'price': round(current, 2),
                            'change': round(change, 2),
                            'change_pct': round(change_pct, 2)
                        }
                except Exception as e:
                    logger.error(f"Error fetching {name}: {str(e)}")
            
            # Get VIX data
            vix_data = self.get_vix_data()
            if vix_data:
                results['volatility']['VIX'] = vix_data
            
            # Determine overall market sentiment
            results['sentiment'] = self._determine_market_sentiment(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting market snapshot: {str(e)}")
            return None
    
    def calculate_vix_percentile(self, lookback_days=252):
        """
        Calculate current VIX percentile vs. historical data
        
        Args:
            lookback_days: Number of days to look back
            
        Returns:
            float: Percentile (0-100)
        """
        try:
            vix = yf.Ticker('^VIX')
            hist_data = vix.history(period=f'{lookback_days}d')
            
            if hist_data.empty or len(hist_data) < 2:
                return 50.0  # Default to middle
            
            current_vix = hist_data['Close'].iloc[-1]
            percentile = (hist_data['Close'] < current_vix).sum() / len(hist_data) * 100
            
            return round(percentile, 1)
            
        except Exception as e:
            logger.error(f"Error calculating VIX percentile: {str(e)}")
            return 50.0
    
    def check_volatility_spike(self, threshold_pct=15):
        """
        Check if VIX has spiked significantly today
        
        Args:
            threshold_pct: Percentage change to consider a spike
            
        Returns:
            dict: Spike status and details
        """
        try:
            vix_data = self.get_vix_data()
            
            if not vix_data:
                return {'spike_detected': False}
            
            spike_detected = abs(vix_data['change_pct']) >= threshold_pct
            
            return {
                'spike_detected': spike_detected,
                'vix_level': vix_data['current'],
                'change_pct': vix_data['change_pct'],
                'regime': vix_data['regime'],
                'recommendation': self._spike_recommendation(spike_detected, vix_data)
            }
            
        except Exception as e:
            logger.error(f"Error checking volatility spike: {str(e)}")
            return {'spike_detected': False}
    
    def correlation_to_symbol(self, symbol, period='3mo'):
        """
        Calculate correlation between symbol and VIX
        
        Args:
            symbol: Stock symbol
            period: Time period for correlation
            
        Returns:
            dict: Correlation coefficient and interpretation
        """
        try:
            # Fetch symbol and VIX data
            stock = yf.Ticker(symbol)
            vix = yf.Ticker('^VIX')
            
            stock_data = stock.history(period=period)
            vix_data = vix.history(period=period)
            
            if stock_data.empty or vix_data.empty:
                return None
            
            # Align data by date
            combined = pd.DataFrame({
                'stock': stock_data['Close'],
                'vix': vix_data['Close']
            }).dropna()
            
            if len(combined) < 20:  # Need enough data points
                return None
            
            # Calculate correlation
            correlation = combined['stock'].corr(combined['vix'])
            
            # Interpret correlation
            interpretation = self._interpret_correlation(correlation)
            
            return {
                'correlation': round(correlation, 3),
                'interpretation': interpretation,
                'data_points': len(combined)
            }
            
        except Exception as e:
            logger.error(f"Error calculating correlation for {symbol}: {str(e)}")
            return None
    
    def get_fear_greed_index(self):
        """
        Calculate simplified Fear & Greed Index based on VIX and market momentum
        
        Returns:
            dict: Fear & Greed score (0-100) and label
        """
        try:
            vix_data = self.get_vix_data()
            
            if not vix_data:
                return {'score': 50, 'label': 'Neutral'}
            
            # VIX component (inverted - high VIX = fear = low score)
            # VIX 10 = 100 score (extreme greed)
            # VIX 50 = 0 score (extreme fear)
            vix_score = max(0, min(100, (50 - vix_data['current']) / 40 * 100))
            
            # Get market momentum
            try:
                spx = yf.Ticker('^GSPC')
                spx_data = spx.history(period='5d')
                
                if len(spx_data) >= 2:
                    momentum = (spx_data['Close'].iloc[-1] / spx_data['Close'].iloc[0] - 1) * 100
                    # Convert to 0-100 scale
                    momentum_score = max(0, min(100, 50 + momentum * 10))
                else:
                    momentum_score = 50
            except:
                momentum_score = 50
            
            # Weighted average (VIX 70%, Momentum 30%)
            fear_greed_score = int(vix_score * 0.7 + momentum_score * 0.3)
            
            # Label the score
            if fear_greed_score >= 75:
                label = 'Extreme Greed'
            elif fear_greed_score >= 60:
                label = 'Greed'
            elif fear_greed_score >= 45:
                label = 'Neutral'
            elif fear_greed_score >= 25:
                label = 'Fear'
            else:
                label = 'Extreme Fear'
            
            return {
                'score': fear_greed_score,
                'label': label,
                'vix_component': round(vix_score, 1),
                'momentum_component': round(momentum_score, 1),
                'vix_level': vix_data['current']
            }
            
        except Exception as e:
            logger.error(f"Error calculating Fear & Greed Index: {str(e)}")
            return {'score': 50, 'label': 'Neutral'}
    
    def _interpret_vix(self, vix_level, vix_change, percentile):
        """Generate human-readable VIX interpretation"""
        regime = self.classify_volatility_regime(vix_level)
        
        interpretations = {
            'low': f"VIX at {vix_level:.1f} indicates calm market conditions. Low volatility environment suitable for most strategies.",
            'normal': f"VIX at {vix_level:.1f} shows typical market volatility. Normal trading conditions.",
            'elevated': f"VIX at {vix_level:.1f} signals elevated uncertainty. Exercise caution and use tighter stops.",
            'high': f"VIX at {vix_level:.1f} indicates high fear levels. Consider defensive positions and hedging.",
            'extreme': f"VIX at {vix_level:.1f} shows extreme panic. Market crash conditions - protect capital."
        }
        
        base_interpretation = interpretations.get(regime, "Unknown volatility regime")
        
        # Add change context
        if abs(vix_change) > 2:
            direction = "spiking" if vix_change > 0 else "declining"
            base_interpretation += f" VIX {direction} {abs(vix_change):.1f} points today."
        
        # Add percentile context
        if percentile > 90:
            base_interpretation += f" VIX in top 10% of historical range."
        elif percentile < 10:
            base_interpretation += f" VIX in bottom 10% of historical range."
        
        return base_interpretation
    
    def _interpret_correlation(self, correlation):
        """Interpret correlation coefficient"""
        if correlation > 0.5:
            return "Strong positive correlation - moves with VIX (defensive/hedge behavior)"
        elif correlation > 0.2:
            return "Moderate positive correlation - somewhat defensive"
        elif correlation > -0.2:
            return "Low correlation - independent of market volatility"
        elif correlation > -0.5:
            return "Moderate negative correlation - vulnerable to volatility spikes"
        else:
            return "Strong negative correlation - highly vulnerable to volatility"
    
    def _spike_recommendation(self, spike_detected, vix_data):
        """Generate recommendation for volatility spike"""
        if not spike_detected:
            return "No significant volatility spike detected. Continue normal trading."
        
        if vix_data['change_pct'] > 0:
            # VIX spiking up (fear increasing)
            if vix_data['regime'] in ['high', 'extreme']:
                return "⚠️ CAUTION: Extreme volatility spike. Consider reducing risk exposure and protecting profits. Avoid new long positions."
            else:
                return "⚡ Volatility increasing. Tighten stop losses and monitor positions closely. May present buying opportunities if fundamentals strong."
        else:
            # VIX dropping (fear decreasing)
            return "✓ Volatility declining. Market calming down. May be good time to add positions if on watchlist."
    
    def _determine_market_sentiment(self, market_data):
        """Determine overall market sentiment from indices and VIX"""
        try:
            # Check market direction
            indices = market_data.get('indices', {})
            if not indices:
                return 'Neutral'
            
            # Average market performance
            changes = [idx['change_pct'] for idx in indices.values()]
            avg_change = sum(changes) / len(changes) if changes else 0
            
            # Get VIX regime
            vix_data = market_data.get('volatility', {}).get('VIX', {})
            vix_regime = vix_data.get('regime', 'normal')
            
            # Determine sentiment
            if vix_regime in ['high', 'extreme']:
                return 'Fear'
            elif vix_regime == 'elevated' and avg_change < -0.5:
                return 'Caution'
            elif avg_change > 1:
                return 'Greed'
            elif avg_change > 0.3:
                return 'Optimistic'
            elif avg_change < -1:
                return 'Pessimistic'
            else:
                return 'Neutral'
                
        except Exception as e:
            logger.error(f"Error determining sentiment: {str(e)}")
            return 'Neutral'
    
    def get_top_volatile_stocks(self, limit=50, min_price=5.0, use_cache=True):
        """
        Get top N most volatile stocks based on:
        - ATR (Average True Range) as % of price
        - Daily price change %
        - Volume surge vs 20-day average
        
        Args:
            limit: Number of stocks to return
            min_price: Minimum stock price to filter penny stocks
            use_cache: Use cached results if available
            
        Returns:
            list: Top volatile stocks with metrics
        """
        # Check cache first
        if use_cache and self._is_cache_valid():
            logger.info("Returning cached volatile stocks data")
            return self.volatile_stocks_cache[:limit]
        
        logger.info(f"Scanning {len(self.stock_universe)} stocks for volatility...")
        volatile_stocks = []
        
        for symbol in self.stock_universe:
            try:
                stock_data = self._calculate_stock_volatility(symbol, min_price)
                if stock_data:
                    volatile_stocks.append(stock_data)
                    
            except Exception as e:
                logger.debug(f"Error processing {symbol}: {str(e)}")
                continue
        
        # Sort by volatility score (descending)
        volatile_stocks.sort(key=lambda x: x['volatility_score'], reverse=True)
        
        # Update cache
        self.volatile_stocks_cache = volatile_stocks
        self.cache_timestamp = time.time()
        
        logger.info(f"Found {len(volatile_stocks)} volatile stocks")
        return volatile_stocks[:limit]
    
    def _calculate_stock_volatility(self, symbol, min_price=5.0):
        """
        Calculate comprehensive volatility metrics for a stock
        
        Args:
            symbol: Stock ticker symbol
            min_price: Minimum price filter
            
        Returns:
            dict: Volatility metrics or None if insufficient data
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get 30 days of data for volatility calculation
            hist = ticker.history(period='30d')
            
            if hist.empty or len(hist) < 20:
                return None
            
            current_price = hist['Close'].iloc[-1]
            
            # Filter penny stocks (but allow crypto regardless of price)
            is_crypto = symbol.endswith('-USD') or symbol.endswith('-USDT')
            if not is_crypto and current_price < min_price:
                return None
            
            # Calculate metrics
            daily_change_pct = ((hist['Close'].iloc[-1] - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
            
            # ATR (Average True Range) as % of price
            atr_pct = self._calculate_atr_percent(hist)
            
            # Historical volatility (20-day)
            hist_volatility = hist['Close'].pct_change().tail(20).std() * 100 * (252 ** 0.5)  # Annualized
            
            # Volume surge
            avg_volume = hist['Volume'].tail(20).mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Price range today
            today_range_pct = ((hist['High'].iloc[-1] - hist['Low'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
            
            # 5-day momentum
            if len(hist) >= 5:
                momentum_5d = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-5]) / hist['Close'].iloc[-5]) * 100
            else:
                momentum_5d = 0
            
            # Volatility score (weighted combination)
            volatility_score = (
                (atr_pct * 0.3) +                    # ATR weight
                (abs(daily_change_pct) * 0.25) +     # Daily movement
                (today_range_pct * 0.2) +            # Intraday range
                (min(volume_ratio, 5) * 5) +         # Volume surge (capped at 5x)
                (hist_volatility * 0.1)              # Historical volatility
            )
            
            # Get company info
            try:
                info = ticker.info
                company_name = info.get('longName', symbol)
                sector = info.get('sector', 'Unknown')
                market_cap = info.get('marketCap', 0)
            except:
                company_name = symbol
                sector = 'Unknown'
                market_cap = 0
            
            # Detect and label cryptocurrencies
            if symbol.endswith('-USD') or symbol.endswith('-USDT'):
                sector = 'Cryptocurrency'
                if company_name == symbol:
                    # Format crypto name nicely
                    crypto_name = symbol.replace('-USD', '').replace('-USDT', '')
                    company_name = f"{crypto_name} (Crypto)"
            
            return {
                'symbol': symbol,
                'name': company_name,
                'sector': sector,
                'price': round(current_price, 2),
                'daily_change_pct': round(daily_change_pct, 2),
                'atr_percent': round(atr_pct, 2),
                'hist_volatility': round(hist_volatility, 1),
                'volume_ratio': round(volume_ratio, 2),
                'today_range_pct': round(today_range_pct, 2),
                'momentum_5d': round(momentum_5d, 2),
                'volatility_score': round(volatility_score, 2),
                'market_cap': market_cap,
                'volume': int(current_volume),
                'avg_volume': int(avg_volume)
            }
            
        except Exception as e:
            logger.debug(f"Error calculating volatility for {symbol}: {str(e)}")
            return None
    
    def _calculate_atr_percent(self, hist_data, period=14):
        """
        Calculate Average True Range as percentage of price
        
        Args:
            hist_data: Historical price data
            period: ATR period (default 14)
            
        Returns:
            float: ATR as percentage of current price
        """
        try:
            high = hist_data['High']
            low = hist_data['Low']
            close = hist_data['Close']
            
            # True Range calculation
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = true_range.tail(period).mean()
            
            current_price = close.iloc[-1]
            atr_percent = (atr / current_price) * 100 if current_price > 0 else 0
            
            return atr_percent
            
        except Exception as e:
            logger.debug(f"Error calculating ATR: {str(e)}")
            return 0.0
    
    def _is_cache_valid(self):
        """Check if cached data is still valid"""
        if self.volatile_stocks_cache is None or self.cache_timestamp is None:
            return False
        
        age = time.time() - self.cache_timestamp
        return age < self.cache_duration
    
    def get_fastest_movers(self, limit=25):
        """
        Get fastest moving stocks (highest % change today)
        
        Args:
            limit: Number of stocks to return
            
        Returns:
            list: Fastest movers sorted by absolute % change
        """
        volatile_stocks = self.get_top_volatile_stocks(limit=100, use_cache=True)
        
        # Sort by absolute daily change
        fastest = sorted(volatile_stocks, key=lambda x: abs(x['daily_change_pct']), reverse=True)
        
        return fastest[:limit]
    
    def get_volume_leaders(self, limit=25):
        """
        Get stocks with highest volume surges
        
        Args:
            limit: Number of stocks to return
            
        Returns:
            list: Volume leaders sorted by volume ratio
        """
        volatile_stocks = self.get_top_volatile_stocks(limit=100, use_cache=True)
        
        # Sort by volume ratio
        volume_leaders = sorted(volatile_stocks, key=lambda x: x['volume_ratio'], reverse=True)
        
        return volume_leaders[:limit]
    
    def get_high_momentum_stocks(self, limit=25):
        """
        Get stocks with strongest 5-day momentum
        
        Args:
            limit: Number of stocks to return
            
        Returns:
            list: High momentum stocks
        """
        volatile_stocks = self.get_top_volatile_stocks(limit=100, use_cache=True)
        
        # Sort by 5-day momentum
        momentum_stocks = sorted(volatile_stocks, key=lambda x: abs(x['momentum_5d']), reverse=True)
        
        return momentum_stocks[:limit]


# Standalone testing
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    vm = VolatilityMonitor()
    
    print("\n=== VIX Data ===")
    vix_data = vm.get_vix_data()
    if vix_data:
        print(f"VIX Level: {vix_data['current']}")
        print(f"Change: {vix_data['change']} ({vix_data['change_pct']}%)")
        print(f"Percentile: {vix_data['percentile']}%")
        print(f"Regime: {vix_data['regime']}")
        print(f"Interpretation: {vix_data['interpretation']}")
    
    print("\n=== All Volatility Indices ===")
    all_vol = vm.get_all_volatility_indices()
    for name, data in all_vol.items():
        print(f"{name}: {data['current']} ({data['change_pct']:+.2f}%)")
    
    print("\n=== Market Snapshot ===")
    snapshot = vm.get_market_snapshot()
    if snapshot:
        print(f"Market Sentiment: {snapshot['sentiment']}")
        for name, data in snapshot['indices'].items():
            print(f"{name}: {data['price']} ({data['change_pct']:+.2f}%)")
    
    print("\n=== Fear & Greed Index ===")
    fear_greed = vm.get_fear_greed_index()
    print(f"Score: {fear_greed['score']}/100 - {fear_greed['label']}")
    
    print("\n=== Volatility Spike Check ===")
    spike = vm.check_volatility_spike()
    print(f"Spike Detected: {spike['spike_detected']}")
    if spike.get('recommendation'):
        print(f"Recommendation: {spike['recommendation']}")
