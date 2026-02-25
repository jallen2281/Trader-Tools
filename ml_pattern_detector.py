"""
ML Pattern Recognition
Phase 2: Advanced pattern detection and prediction
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

class MLPatternDetector:
    """Machine learning-based pattern detection and prediction"""
    
    def __init__(self):
        """Initialize ML pattern detector"""
        self.scaler = StandardScaler()
        
    def detect_patterns(self, stock_data, symbol):
        """
        Detect trading patterns in stock data
        
        Args:
            stock_data: DataFrame with OHLCV data
            symbol: Stock symbol
            
        Returns:
            list: Detected patterns with confidence scores
        """
        patterns = []
        
        try:
            # Double Top Pattern
            double_top = self._detect_double_top(stock_data)
            if double_top:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': 'double_top',
                    'confidence': double_top['confidence'],
                    'prediction': 'bearish',
                    'time_horizon': '1-2 weeks',
                    'pattern_data': double_top,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
            
            # Double Bottom Pattern
            double_bottom = self._detect_double_bottom(stock_data)
            if double_bottom:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': 'double_bottom',
                    'confidence': double_bottom['confidence'],
                    'prediction': 'bullish',
                    'time_horizon': '1-2 weeks',
                    'pattern_data': double_bottom,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
            
            # Head and Shoulders
            head_shoulders = self._detect_head_and_shoulders(stock_data)
            if head_shoulders:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': 'head_and_shoulders',
                    'confidence': head_shoulders['confidence'],
                    'prediction': 'bearish',
                    'time_horizon': '2-4 weeks',
                    'pattern_data': head_shoulders,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
            
            # Triangle Pattern
            triangle = self._detect_triangle(stock_data)
            if triangle:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': f"{triangle['type']}_triangle",
                    'confidence': triangle['confidence'],
                    'prediction': triangle['prediction'],
                    'time_horizon': '1-3 weeks',
                    'pattern_data': triangle,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
            
            # Breakout Detection
            breakout = self._detect_breakout(stock_data)
            if breakout:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': 'breakout',
                    'confidence': breakout['confidence'],
                    'prediction': breakout['direction'],
                    'time_horizon': '3-7 days',
                    'pattern_data': breakout,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
            
            # Volume Surge
            volume_surge = self._detect_volume_surge(stock_data)
            if volume_surge:
                patterns.append({
                    'symbol': symbol,
                    'pattern_type': 'volume_surge',
                    'confidence': volume_surge['confidence'],
                    'prediction': volume_surge['prediction'],
                    'time_horizon': '1-5 days',
                    'pattern_data': volume_surge,
                    'price_at_detection': float(stock_data.iloc[-1]['Close'])
                })
        
        except Exception as e:
            print(f"Error detecting patterns for {symbol}: {e}")
        
        return patterns
    
    def _detect_double_top(self, df):
        """Detect double top pattern"""
        if len(df) < 40:
            return None
        
        try:
            # Find peaks
            peaks = []
            window = 5
            
            for i in range(window, len(df) - window):
                if df.iloc[i]['High'] == df.iloc[i-window:i+window+1]['High'].max():
                    peaks.append((i, df.iloc[i]['High']))
            
            # Look for two similar peaks
            for i in range(len(peaks) - 1):
                for j in range(i + 1, len(peaks)):
                    idx1, price1 = peaks[i]
                    idx2, price2 = peaks[j]
                    
                    # Check if peaks are similar in price
                    price_diff = abs(price1 - price2) / price1
                    if price_diff < 0.03:  # Within 3%
                        # Check if there's a trough between
                        trough_section = df.iloc[idx1:idx2]
                        trough_price = trough_section['Low'].min()
                        
                        if trough_price < min(price1, price2) * 0.97:  # At least 3% below
                            confidence = 1.0 - price_diff
                            
                            return {
                                'peak1_idx': idx1,
                                'peak1_price': float(price1),
                                'peak2_idx': idx2,
                                'peak2_price': float(price2),
                                'trough_price': float(trough_price),
                                'confidence': round(confidence, 4)
                            }
        
        except Exception:
            pass
        
        return None
    
    def _detect_double_bottom(self, df):
        """Detect double bottom pattern"""
        if len(df) < 40:
            return None
        
        try:
            # Find troughs
            troughs = []
            window = 5
            
            for i in range(window, len(df) - window):
                if df.iloc[i]['Low'] == df.iloc[i-window:i+window+1]['Low'].min():
                    troughs.append((i, df.iloc[i]['Low']))
            
            # Look for two similar troughs
            for i in range(len(troughs) - 1):
                for j in range(i + 1, len(troughs)):
                    idx1, price1 = troughs[i]
                    idx2, price2 = troughs[j]
                    
                    price_diff = abs(price1 - price2) / price1
                    if price_diff < 0.03:
                        # Check if there's a peak between
                        peak_section = df.iloc[idx1:idx2]
                        peak_price = peak_section['High'].max()
                        
                        if peak_price > max(price1, price2) * 1.03:
                            confidence = 1.0 - price_diff
                            
                            return {
                                'trough1_idx': idx1,
                                'trough1_price': float(price1),
                                'trough2_idx': idx2,
                                'trough2_price': float(price2),
                                'peak_price': float(peak_price),
                                'confidence': round(confidence, 4)
                            }
        
        except Exception:
            pass
        
        return None
    
    def _detect_head_and_shoulders(self, df):
        """Detect head and shoulders pattern"""
        if len(df) < 60:
            return None
        
        try:
            # Find three consecutive peaks
            peaks = []
            window = 5
            
            for i in range(window, len(df) - window):
                if df.iloc[i]['High'] == df.iloc[i-window:i+window+1]['High'].max():
                    peaks.append((i, df.iloc[i]['High']))
            
            # Look for pattern: left shoulder, head, right shoulder
            for i in range(len(peaks) - 2):
                left = peaks[i]
                head = peaks[i + 1]
                right = peaks[i + 2]
                
                # Head should be higher than shoulders
                if (head[1] > left[1] * 1.03 and 
                    head[1] > right[1] * 1.03 and
                    abs(left[1] - right[1]) / left[1] < 0.05):
                    
                    # Calculate neckline
                    left_trough = df.iloc[left[0]:head[0]]['Low'].min()
                    right_trough = df.iloc[head[0]:right[0]]['Low'].min()
                    neckline = (left_trough + right_trough) / 2
                    
                    confidence = 0.7  # Base confidence
                    
                    return {
                        'left_shoulder': float(left[1]),
                        'head': float(head[1]),
                        'right_shoulder': float(right[1]),
                        'neckline': float(neckline),
                        'confidence': confidence
                    }
        
        except Exception:
            pass
        
        return None
    
    def _detect_triangle(self, df):
        """Detect triangle patterns (ascending, descending, symmetrical)"""
        if len(df) < 30:
            return None
        
        try:
            recent = df.tail(30)
            
            # Calculate trendlines for highs and lows
            highs = recent['High'].values
            lows = recent['Low'].values
            x = np.arange(len(recent)).reshape(-1, 1)
            
            # Fit linear regression to highs and lows
            high_model = LinearRegression().fit(x, highs)
            low_model = LinearRegression().fit(x, lows)
            
            high_slope = high_model.coef_[0]
            low_slope = low_model.coef_[0]
            
            # Determine triangle type
            if abs(high_slope) < 0.01 and low_slope > 0.01:
                # Ascending triangle - bullish
                return {
                    'type': 'ascending',
                    'prediction': 'bullish',
                    'confidence': 0.65,
                    'resistance': float(highs.max()),
                    'support_slope': float(low_slope)
                }
            
            elif high_slope < -0.01 and abs(low_slope) < 0.01:
                # Descending triangle - bearish
                return {
                    'type': 'descending',
                    'prediction': 'bearish',
                    'confidence': 0.65,
                    'resistance_slope': float(high_slope),
                    'support': float(lows.min())
                }
            
            elif high_slope < -0.01 and low_slope > 0.01:
                # Symmetrical triangle - neutral/breakout
                return {
                    'type': 'symmetrical',
                    'prediction': 'neutral',
                    'confidence': 0.60,
                    'high_slope': float(high_slope),
                    'low_slope': float(low_slope)
                }
        
        except Exception:
            pass
        
        return None
    
    def _detect_breakout(self, df):
        """Detect breakout from consolidation"""
        if len(df) < 20:
            return None
        
        try:
            recent = df.tail(20)
            latest = df.iloc[-1]
            
            # Calculate volatility
            price_range = recent['High'].max() - recent['Low'].min()
            avg_price = recent['Close'].mean()
            volatility = price_range / avg_price
            
            # Low volatility followed by sharp move = breakout
            if volatility < 0.05:  # Low volatility
                prev_close = df.iloc[-2]['Close']
                price_change_pct = abs(latest['Close'] - prev_close) / prev_close
                
                if price_change_pct > 0.02:  # 2% move
                    direction = 'bullish' if latest['Close'] > prev_close else 'bearish'
                    
                    # Higher volume confirms breakout
                    avg_volume = recent['Volume'].mean()
                    volume_ratio = latest['Volume'] / avg_volume
                    
                    confidence = min(0.5 + (volume_ratio - 1) * 0.2, 0.9)
                    
                    return {
                        'direction': direction,
                        'breakout_price': float(latest['Close']),
                        'volume_ratio': float(volume_ratio),
                        'confidence': round(confidence, 4)
                    }
        
        except Exception:
            pass
        
        return None
    
    def _detect_volume_surge(self, df):
        """Detect unusual volume surge"""
        if len(df) < 20:
            return None
        
        try:
            recent = df.tail(20)
            latest = df.iloc[-1]
            
            avg_volume = recent.iloc[:-1]['Volume'].mean()
            volume_ratio = latest['Volume'] / avg_volume
            
            # Significant volume surge (2x or more)
            if volume_ratio >= 2.0:
                # Determine if bullish or bearish based on price action
                prev_close = df.iloc[-2]['Close']
                price_change_pct = (latest['Close'] - prev_close) / prev_close
                
                if abs(price_change_pct) > 0.01:  # At least 1% move
                    prediction = 'bullish' if price_change_pct > 0 else 'bearish'
                    confidence = min(0.5 + (volume_ratio - 2) * 0.1, 0.85)
                    
                    return {
                        'prediction': prediction,
                        'volume_ratio': float(volume_ratio),
                        'price_change_pct': float(price_change_pct * 100),
                        'confidence': round(confidence, 4)
                    }
        
        except Exception:
            pass
        
        return None
    
    def make_prediction(self, stock_data, symbol, horizon_days=5):
        """
        Make price prediction using linear regression
        
        Args:
            stock_data: DataFrame with historical data
            symbol: Stock symbol
            horizon_days: Number of days to predict ahead
            
        Returns:
            dict: Prediction details
        """
        if len(stock_data) < 30:
            return None
        
        try:
            # Prepare data
            recent = stock_data.tail(30).copy()
            recent['Days'] = range(len(recent))
            
            X = recent[['Days']].values
            y = recent['Close'].values
            
            # Fit model
            model = LinearRegression()
            model.fit(X, y)
            
            # Make prediction
            future_day = len(recent) + horizon_days - 1
            predicted_price = model.predict([[future_day]])[0]
            
            current_price = float(stock_data.iloc[-1]['Close'])
            price_change = predicted_price - current_price
            price_change_pct = (price_change / current_price) * 100
            
            # Determine direction
            if price_change_pct > 1:
                direction = 'up'
            elif price_change_pct < -1:
                direction = 'down'
            else:
                direction = 'sideways'
            
            # Calculate confidence based on R² score
            from sklearn.metrics import r2_score
            r2 = r2_score(y, model.predict(X))
            confidence = max(0.3, min(0.8, r2))
            
            target_date = datetime.now() + timedelta(days=horizon_days)
            
            return {
                'symbol': symbol,
                'prediction_type': 'linear_regression',
                'predicted_direction': direction,
                'predicted_price': round(float(predicted_price), 2),
                'current_price': round(current_price, 2),
                'price_change_pct': round(price_change_pct, 2),
                'confidence': round(confidence, 4),
                'time_horizon': f'{horizon_days} days',
                'target_date': target_date.isoformat(),
                'model_version': '1.0'
            }
        
        except Exception as e:
            print(f"Error making prediction for {symbol}: {e}")
            return None
