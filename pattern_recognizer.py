"""Module for detecting trading patterns in financial data."""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands


class PatternRecognizer:
    """Identifies trading patterns and technical indicators."""
    
    def __init__(self):
        """Initialize the pattern recognizer."""
        self.patterns = []
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators.
        
        Args:
            data: DataFrame with OHLCV data
        
        Returns:
            DataFrame with added indicator columns
        """
        df = data.copy()
        
        # Moving Averages
        df['SMA_20'] = SMAIndicator(close=df['Close'], window=20).sma_indicator()
        df['SMA_50'] = SMAIndicator(close=df['Close'], window=50).sma_indicator()
        df['EMA_12'] = EMAIndicator(close=df['Close'], window=12).ema_indicator()
        df['EMA_26'] = EMAIndicator(close=df['Close'], window=26).ema_indicator()
        
        # MACD
        macd = MACD(close=df['Close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Diff'] = macd.macd_diff()
        
        # RSI
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # Bollinger Bands
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_High'] = bb.bollinger_hband()
        df['BB_Low'] = bb.bollinger_lband()
        df['BB_Mid'] = bb.bollinger_mavg()
        
        # Stochastic Oscillator
        stoch = StochasticOscillator(
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'],
            window=14,
            smooth_window=3
        )
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()
        
        return df
    
    def detect_support_resistance(
        self, 
        data: pd.DataFrame,
        window: int = 20
    ) -> Dict[str, List[float]]:
        """
        Detect support and resistance levels.
        
        Args:
            data: DataFrame with OHLCV data
            window: Window size for detection
        
        Returns:
            Dictionary with support and resistance levels
        """
        highs = data['High'].values
        lows = data['Low'].values
        
        resistance_levels = []
        support_levels = []
        
        # Find local maxima (resistance)
        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i-window:i+window+1]):
                resistance_levels.append(highs[i])
        
        # Find local minima (support)
        for i in range(window, len(lows) - window):
            if lows[i] == min(lows[i-window:i+window+1]):
                support_levels.append(lows[i])
        
        # Cluster similar levels
        resistance_levels = self._cluster_levels(resistance_levels)
        support_levels = self._cluster_levels(support_levels)
        
        return {
            'resistance': resistance_levels,
            'support': support_levels
        }
    
    def _cluster_levels(self, levels: List[float], threshold: float = 0.02) -> List[float]:
        """
        Cluster similar price levels.
        
        Args:
            levels: List of price levels
            threshold: Percentage threshold for clustering
        
        Returns:
            List of clustered levels
        """
        if not levels:
            return []
        
        levels = sorted(levels)
        clustered = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            if abs(level - current_cluster[-1]) / current_cluster[-1] < threshold:
                current_cluster.append(level)
            else:
                clustered.append(np.mean(current_cluster))
                current_cluster = [level]
        
        clustered.append(np.mean(current_cluster))
        return clustered
    
    def detect_trend(self, data: pd.DataFrame, window: int = 20) -> str:
        """
        Detect current trend direction.
        
        Args:
            data: DataFrame with OHLCV data
            window: Window size for trend calculation
        
        Returns:
            Trend direction: 'uptrend', 'downtrend', or 'sideways'
        """
        if len(data) < window:
            return 'insufficient_data'
        
        recent_data = data.tail(window)
        
        # Calculate linear regression slope
        x = np.arange(len(recent_data))
        y = recent_data['Close'].values
        slope = np.polyfit(x, y, 1)[0]
        
        # Determine trend based on slope and price position relative to MA
        avg_price = recent_data['Close'].mean()
        slope_pct = (slope / avg_price) * 100
        
        if slope_pct > 0.1:
            return 'uptrend'
        elif slope_pct < -0.1:
            return 'downtrend'
        else:
            return 'sideways'
    
    def detect_candlestick_patterns(self, data: pd.DataFrame) -> List[Dict]:
        """
        Detect common candlestick patterns.
        
        Args:
            data: DataFrame with OHLCV data
        
        Returns:
            List of detected patterns
        """
        patterns = []
        
        if len(data) < 3:
            return patterns
        
        # Get last 3 candles
        last_3 = data.tail(3)
        
        # Doji
        if self._is_doji(last_3.iloc[-1]):
            patterns.append({
                'pattern': 'Doji',
                'date': last_3.index[-1],
                'sentiment': 'neutral',
                'description': 'Indecision in the market'
            })
        
        # Hammer / Hanging Man
        if self._is_hammer(last_3.iloc[-1]):
            patterns.append({
                'pattern': 'Hammer',
                'date': last_3.index[-1],
                'sentiment': 'bullish',
                'description': 'Potential reversal signal'
            })
        
        # Engulfing patterns
        if len(last_3) >= 2:
            if self._is_bullish_engulfing(last_3.iloc[-2], last_3.iloc[-1]):
                patterns.append({
                    'pattern': 'Bullish Engulfing',
                    'date': last_3.index[-1],
                    'sentiment': 'bullish',
                    'description': 'Strong bullish reversal signal'
                })
            elif self._is_bearish_engulfing(last_3.iloc[-2], last_3.iloc[-1]):
                patterns.append({
                    'pattern': 'Bearish Engulfing',
                    'date': last_3.index[-1],
                    'sentiment': 'bearish',
                    'description': 'Strong bearish reversal signal'
                })
        
        return patterns
    
    def _is_doji(self, candle: pd.Series) -> bool:
        """Check if candle is a doji."""
        body = abs(candle['Close'] - candle['Open'])
        range_size = candle['High'] - candle['Low']
        return body / range_size < 0.1 if range_size > 0 else False
    
    def _is_hammer(self, candle: pd.Series) -> bool:
        """Check if candle is a hammer."""
        body = abs(candle['Close'] - candle['Open'])
        lower_shadow = min(candle['Open'], candle['Close']) - candle['Low']
        upper_shadow = candle['High'] - max(candle['Open'], candle['Close'])
        
        return (lower_shadow > 2 * body and 
                upper_shadow < body and 
                body > 0)
    
    def _is_bullish_engulfing(self, prev: pd.Series, curr: pd.Series) -> bool:
        """Check if pattern is bullish engulfing."""
        prev_bearish = prev['Close'] < prev['Open']
        curr_bullish = curr['Close'] > curr['Open']
        curr_engulfs = (curr['Open'] < prev['Close'] and 
                       curr['Close'] > prev['Open'])
        
        return prev_bearish and curr_bullish and curr_engulfs
    
    def _is_bearish_engulfing(self, prev: pd.Series, curr: pd.Series) -> bool:
        """Check if pattern is bearish engulfing."""
        prev_bullish = prev['Close'] > prev['Open']
        curr_bearish = curr['Close'] < curr['Open']
        curr_engulfs = (curr['Open'] > prev['Close'] and 
                       curr['Close'] < prev['Open'])
        
        return prev_bullish and curr_bearish and curr_engulfs
    
    def generate_signals(self, data: pd.DataFrame) -> Dict[str, str]:
        """
        Generate trading signals based on indicators.
        
        Args:
            data: DataFrame with indicators
        
        Returns:
            Dictionary of signals
        """
        signals = {}
        
        if len(data) < 2:
            return signals
        
        latest = data.iloc[-1]
        prev = data.iloc[-2]
        
        # RSI signals
        if 'RSI' in latest:
            if latest['RSI'] < 30:
                signals['RSI'] = 'Oversold - Potential Buy'
            elif latest['RSI'] > 70:
                signals['RSI'] = 'Overbought - Potential Sell'
            else:
                signals['RSI'] = 'Neutral'
        
        # MACD signals
        if 'MACD' in latest and 'MACD_Signal' in latest:
            if prev['MACD'] <= prev['MACD_Signal'] and latest['MACD'] > latest['MACD_Signal']:
                signals['MACD'] = 'Bullish Crossover - Buy Signal'
            elif prev['MACD'] >= prev['MACD_Signal'] and latest['MACD'] < latest['MACD_Signal']:
                signals['MACD'] = 'Bearish Crossover - Sell Signal'
            else:
                signals['MACD'] = 'No Crossover'
        
        # Moving Average signals
        if 'SMA_20' in latest and 'SMA_50' in latest:
            if latest['SMA_20'] > latest['SMA_50']:
                signals['MA_Cross'] = 'Bullish - Short MA above Long MA'
            else:
                signals['MA_Cross'] = 'Bearish - Short MA below Long MA'
        
        # Bollinger Bands signals
        if 'BB_Low' in latest and 'BB_High' in latest:
            if latest['Close'] < latest['BB_Low']:
                signals['Bollinger'] = 'Price below lower band - Potential Buy'
            elif latest['Close'] > latest['BB_High']:
                signals['Bollinger'] = 'Price above upper band - Potential Sell'
            else:
                signals['Bollinger'] = 'Price within bands'
        
        return signals
