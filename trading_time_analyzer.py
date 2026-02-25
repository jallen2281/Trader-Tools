"""
Trading Time Intelligence Module
Phase 3: Optimal entry/exit timing, volume analysis, and market timing
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TradingTimeAnalyzer:
    """Analyzes optimal timing for trades based on technical signals and volume"""
    
    def __init__(self):
        """Initialize trading time analyzer"""
        pass
    
    def analyze_entry_points(self, stock_data, symbol):
        """
        Identify optimal entry points based on multiple indicators
        
        Args:
            stock_data: DataFrame with OHLCV and indicators
            symbol: Stock symbol
            
        Returns:
            dict: Entry point analysis with signals and timing
        """
        try:
            if len(stock_data) < 50:
                return {'error': 'Insufficient data for entry analysis'}
            
            latest = stock_data.iloc[-1]
            current_price = float(latest['Close'])
            
            entry_signals = []
            score = 0
            max_score = 0
            
            # Signal 1: RSI Oversold (Strong Buy)
            max_score += 20
            if pd.notna(latest.get('RSI')) and latest['RSI'] < 30:
                entry_signals.append({
                    'signal': 'RSI Oversold',
                    'strength': 'Strong',
                    'value': round(float(latest['RSI']), 2),
                    'description': 'RSI below 30 indicates oversold conditions',
                    'points': 20
                })
                score += 20
            elif pd.notna(latest.get('RSI')) and latest['RSI'] < 40:
                entry_signals.append({
                    'signal': 'RSI Near Oversold',
                    'strength': 'Moderate',
                    'value': round(float(latest['RSI']), 2),
                    'description': 'RSI approaching oversold territory',
                    'points': 10
                })
                score += 10
            
            # Signal 2: MACD Bullish Crossover
            max_score += 20
            if pd.notna(latest.get('MACD')) and pd.notna(latest.get('MACD_Signal')):
                macd = float(latest['MACD'])
                signal = float(latest['MACD_Signal'])
                
                if len(stock_data) > 1:
                    prev = stock_data.iloc[-2]
                    prev_macd = float(prev.get('MACD', 0))
                    prev_signal = float(prev.get('MACD_Signal', 0))
                    
                    # Bullish crossover
                    if prev_macd <= prev_signal and macd > signal:
                        entry_signals.append({
                            'signal': 'MACD Bullish Crossover',
                            'strength': 'Strong',
                            'value': f'{macd:.4f} > {signal:.4f}',
                            'description': 'MACD crossed above signal line',
                            'points': 20
                        })
                        score += 20
                    elif macd > signal:
                        entry_signals.append({
                            'signal': 'MACD Above Signal',
                            'strength': 'Moderate',
                            'value': f'{macd:.4f} > {signal:.4f}',
                            'description': 'MACD in bullish territory',
                            'points': 10
                        })
                        score += 10
            
            # Signal 3: Price Near Support
            max_score += 15
            support_levels = self._find_support_levels(stock_data)
            if support_levels:
                nearest_support = min(support_levels, key=lambda x: abs(x - current_price))
                distance_pct = abs(current_price - nearest_support) / current_price * 100
                
                if distance_pct < 2:  # Within 2% of support
                    entry_signals.append({
                        'signal': 'Near Support Level',
                        'strength': 'Strong',
                        'value': f'${nearest_support:.2f} ({distance_pct:.1f}% away)',
                        'description': 'Price bouncing off support',
                        'points': 15
                    })
                    score += 15
                elif distance_pct < 5:
                    entry_signals.append({
                        'signal': 'Approaching Support',
                        'strength': 'Moderate',
                        'value': f'${nearest_support:.2f} ({distance_pct:.1f}% away)',
                        'description': 'Price moving toward support',
                        'points': 8
                    })
                    score += 8
            
            # Signal 4: Bollinger Band Analysis
            max_score += 15
            if pd.notna(latest.get('BB_Low')) and pd.notna(latest.get('BB_High')):
                bb_low = float(latest['BB_Low'])
                bb_high = float(latest['BB_High'])
                bb_mid = (bb_low + bb_high) / 2
                
                if current_price <= bb_low:
                    entry_signals.append({
                        'signal': 'Price At Lower Band',
                        'strength': 'Strong',
                        'value': f'${current_price:.2f} ≤ ${bb_low:.2f}',
                        'description': 'Price at lower Bollinger Band - potential bounce',
                        'points': 15
                    })
                    score += 15
                elif current_price < bb_mid:
                    entry_signals.append({
                        'signal': 'Price Below Middle Band',
                        'strength': 'Moderate',
                        'value': f'${current_price:.2f} < ${bb_mid:.2f}',
                        'description': 'Price in lower half of BB range',
                        'points': 7
                    })
                    score += 7
            
            # Signal 5: Moving Average Crossover
            max_score += 15
            if pd.notna(latest.get('SMA_20')) and pd.notna(latest.get('SMA_50')):
                sma20 = float(latest['SMA_20'])
                sma50 = float(latest['SMA_50'])
                
                if len(stock_data) > 1:
                    prev = stock_data.iloc[-2]
                    prev_sma20 = float(prev.get('SMA_20', 0))
                    prev_sma50 = float(prev.get('SMA_50', 0))
                    
                    # Golden cross
                    if prev_sma20 <= prev_sma50 and sma20 > sma50:
                        entry_signals.append({
                            'signal': 'Golden Cross',
                            'strength': 'Strong',
                            'value': f'SMA20 > SMA50',
                            'description': 'Bullish moving average crossover',
                            'points': 15
                        })
                        score += 15
                    elif sma20 > sma50:
                        entry_signals.append({
                            'signal': 'Bullish MA Alignment',
                            'strength': 'Moderate',
                            'value': f'SMA20 > SMA50',
                            'description': 'Short-term MA above long-term MA',
                            'points': 7
                        })
                        score += 7
            
            # Signal 6: Volume Surge
            max_score += 15
            recent_volume = stock_data.tail(20)['Volume'].mean()
            current_volume = float(latest['Volume'])
            volume_ratio = current_volume / recent_volume if recent_volume > 0 else 0
            
            if volume_ratio > 1.5:
                entry_signals.append({
                    'signal': 'High Volume',
                    'strength': 'Strong',
                    'value': f'{volume_ratio:.1f}x average',
                    'description': 'Above-average volume confirms interest',
                    'points': 15
                })
                score += 15
            elif volume_ratio > 1.0:
                entry_signals.append({
                    'signal': 'Normal Volume',
                    'strength': 'Moderate',
                    'value': f'{volume_ratio:.1f}x average',
                    'description': 'Volume at or above average',
                    'points': 7
                })
                score += 7
            
            # Calculate overall entry score
            entry_score = (score / max_score * 100) if max_score > 0 else 0
            
            # Determine entry recommendation
            if entry_score >= 70:
                recommendation = 'Strong Buy Signal'
                timing = 'Excellent entry opportunity'
            elif entry_score >= 50:
                recommendation = 'Moderate Buy Signal'
                timing = 'Good entry opportunity with confirmation'
            elif entry_score >= 30:
                recommendation = 'Weak Buy Signal'
                timing = 'Wait for better setup'
            else:
                recommendation = 'No Buy Signal'
                timing = 'Avoid entry - unfavorable conditions'
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'entry_score': round(entry_score, 1),
                'recommendation': recommendation,
                'timing': timing,
                'signals': entry_signals,
                'total_signals': len(entry_signals),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error analyzing entry points for {symbol}: {e}")
            return {'error': str(e)}
    
    def analyze_exit_points(self, stock_data, symbol, entry_price=None):
        """
        Identify optimal exit points and take-profit/stop-loss levels
        
        Args:
            stock_data: DataFrame with OHLCV and indicators
            symbol: Stock symbol
            entry_price: Entry price if in position (optional)
            
        Returns:
            dict: Exit point analysis with targets and stops
        """
        try:
            if len(stock_data) < 50:
                return {'error': 'Insufficient data for exit analysis'}
            
            latest = stock_data.iloc[-1]
            current_price = float(latest['Close'])
            
            # Use entry price or current price
            reference_price = entry_price if entry_price else current_price
            
            exit_signals = []
            score = 0
            max_score = 0
            
            # Signal 1: RSI Overbought (Strong Sell)
            max_score += 20
            if pd.notna(latest.get('RSI')) and latest['RSI'] > 70:
                exit_signals.append({
                    'signal': 'RSI Overbought',
                    'strength': 'Strong',
                    'value': round(float(latest['RSI']), 2),
                    'description': 'RSI above 70 indicates overbought conditions',
                    'points': 20
                })
                score += 20
            elif pd.notna(latest.get('RSI')) and latest['RSI'] > 60:
                exit_signals.append({
                    'signal': 'RSI Near Overbought',
                    'strength': 'Moderate',
                    'value': round(float(latest['RSI']), 2),
                    'description': 'RSI approaching overbought territory',
                    'points': 10
                })
                score += 10
            
            # Signal 2: MACD Bearish Crossover
            max_score += 20
            if pd.notna(latest.get('MACD')) and pd.notna(latest.get('MACD_Signal')):
                macd = float(latest['MACD'])
                signal = float(latest['MACD_Signal'])
                
                if len(stock_data) > 1:
                    prev = stock_data.iloc[-2]
                    prev_macd = float(prev.get('MACD', 0))
                    prev_signal = float(prev.get('MACD_Signal', 0))
                    
                    # Bearish crossover
                    if prev_macd >= prev_signal and macd < signal:
                        exit_signals.append({
                            'signal': 'MACD Bearish Crossover',
                            'strength': 'Strong',
                            'value': f'{macd:.4f} < {signal:.4f}',
                            'description': 'MACD crossed below signal line',
                            'points': 20
                        })
                        score += 20
                    elif macd < signal:
                        exit_signals.append({
                            'signal': 'MACD Below Signal',
                            'strength': 'Moderate',
                            'value': f'{macd:.4f} < {signal:.4f}',
                            'description': 'MACD in bearish territory',
                            'points': 10
                        })
                        score += 10
            
            # Signal 3: Price Near Resistance
            max_score += 15
            resistance_levels = self._find_resistance_levels(stock_data)
            if resistance_levels:
                nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price))
                distance_pct = abs(current_price - nearest_resistance) / current_price * 100
                
                if distance_pct < 2:
                    exit_signals.append({
                        'signal': 'Near Resistance Level',
                        'strength': 'Strong',
                        'value': f'${nearest_resistance:.2f} ({distance_pct:.1f}% away)',
                        'description': 'Price hitting resistance',
                        'points': 15
                    })
                    score += 15
                elif distance_pct < 5:
                    exit_signals.append({
                        'signal': 'Approaching Resistance',
                        'strength': 'Moderate',
                        'value': f'${nearest_resistance:.2f} ({distance_pct:.1f}% away)',
                        'description': 'Price moving toward resistance',
                        'points': 8
                    })
                    score += 8
            
            # Calculate profit/loss targets
            # ATR for stop loss
            atr = self._calculate_atr(stock_data)
            
            # Stop loss: 2x ATR below entry
            stop_loss = reference_price - (2 * atr)
            stop_loss_pct = ((stop_loss - reference_price) / reference_price) * 100
            
            # Take profit levels
            take_profit_1 = reference_price + (1.5 * atr)  # 1.5:1 reward
            take_profit_2 = reference_price + (3 * atr)    # 3:1 reward
            take_profit_3 = reference_price + (5 * atr)    # 5:1 reward
            
            tp1_pct = ((take_profit_1 - reference_price) / reference_price) * 100
            tp2_pct = ((take_profit_2 - reference_price) / reference_price) * 100
            tp3_pct = ((take_profit_3 - reference_price) / reference_price) * 100
            
            # Calculate current P&L if entry price provided
            current_pnl = None
            current_pnl_pct = None
            if entry_price:
                current_pnl = current_price - entry_price
                current_pnl_pct = (current_pnl / entry_price) * 100
            
            # Exit recommendation
            exit_score = (score / max_score * 100) if max_score > 0 else 0
            
            if exit_score >= 70:
                recommendation = 'Strong Sell Signal'
                timing = 'Consider taking profits'
            elif exit_score >= 50:
                recommendation = 'Moderate Sell Signal'
                timing = 'Partial profit taking recommended'
            elif exit_score >= 30:
                recommendation = 'Weak Sell Signal'
                timing = 'Monitor position closely'
            else:
                recommendation = 'Hold Position'
                timing = 'No immediate exit needed'
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'entry_price': reference_price,
                'current_pnl': round(current_pnl, 2) if current_pnl else None,
                'current_pnl_pct': round(current_pnl_pct, 2) if current_pnl_pct else None,
                'exit_score': round(exit_score, 1),
                'recommendation': recommendation,
                'timing': timing,
                'signals': exit_signals,
                'price_targets': {
                    'stop_loss': {
                        'price': round(stop_loss, 2),
                        'distance_pct': round(stop_loss_pct, 2)
                    },
                    'take_profit_1': {
                        'price': round(take_profit_1, 2),
                        'distance_pct': round(tp1_pct, 2),
                        'risk_reward': '1.5:1'
                    },
                    'take_profit_2': {
                        'price': round(take_profit_2, 2),
                        'distance_pct': round(tp2_pct, 2),
                        'risk_reward': '3:1'
                    },
                    'take_profit_3': {
                        'price': round(take_profit_3, 2),
                        'distance_pct': round(tp3_pct, 2),
                        'risk_reward': '5:1'
                    }
                },
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error analyzing exit points for {symbol}: {e}")
            return {'error': str(e)}
    
    def analyze_volume_profile(self, stock_data, symbol):
        """
        Analyze volume patterns and profile
        
        Args:
            stock_data: DataFrame with OHLCV data
            symbol: Stock symbol
            
        Returns:
            dict: Volume analysis
        """
        try:
            if len(stock_data) < 20:
                return {'error': 'Insufficient data for volume analysis'}
            
            latest = stock_data.iloc[-1]
            recent = stock_data.tail(20)
            
            current_volume = float(latest['Volume'])
            avg_volume_20 = float(recent['Volume'].mean())
            volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0
            
            # Volume trend
            volume_trend = 'increasing' if current_volume > avg_volume_20 else 'decreasing'
            
            # Unusual volume detection
            unusual_volume = []
            for i in range(-5, 0):
                if i + len(stock_data) >= 0:
                    day = stock_data.iloc[i]
                    day_volume = float(day['Volume'])
                    if day_volume > avg_volume_20 * 1.5:
                        unusual_volume.append({
                            'date': str(day.name.date()) if hasattr(day.name, 'date') else 'Unknown',
                            'volume': int(day_volume),
                            'ratio': round(day_volume / avg_volume_20, 2),
                            'price_change': round(float(day['Close'] - day['Open']) / float(day['Open']) * 100, 2)
                        })
            
            # Volume-price correlation
            price_changes = recent['Close'].pct_change()
            volume_changes = recent['Volume'].pct_change()
            correlation = price_changes.corr(volume_changes)
            
            # Accumulation/Distribution
            recent_with_ad = recent.copy()
            recent_with_ad['AD'] = ((recent['Close'] - recent['Low']) - (recent['High'] - recent['Close'])) / (recent['High'] - recent['Low']) * recent['Volume']
            ad_line = recent_with_ad['AD'].cumsum()
            ad_trend = 'accumulation' if ad_line.iloc[-1] > ad_line.iloc[-10] else 'distribution'
            
            return {
                'symbol': symbol,
                'current_volume': int(current_volume),
                'average_volume_20d': int(avg_volume_20),
                'volume_ratio': round(volume_ratio, 2),
                'volume_trend': volume_trend,
                'unusual_volume_days': unusual_volume,
                'volume_price_correlation': round(float(correlation), 3) if pd.notna(correlation) else None,
                'accumulation_distribution': ad_trend,
                'analysis': self._interpret_volume(volume_ratio, ad_trend, correlation),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error analyzing volume for {symbol}: {e}")
            return {'error': str(e)}
    
    def _find_support_levels(self, stock_data, num_levels=3):
        """Find support levels from price data"""
        try:
            lows = stock_data.tail(60)['Low']
            support_levels = []
            
            # Find local minima
            for i in range(5, len(lows) - 5):
                if lows.iloc[i] == lows.iloc[i-5:i+5].min():
                    support_levels.append(float(lows.iloc[i]))
            
            # Return unique levels
            return sorted(set(support_levels))[-num_levels:]
        except:
            return []
    
    def _find_resistance_levels(self, stock_data, num_levels=3):
        """Find resistance levels from price data"""
        try:
            highs = stock_data.tail(60)['High']
            resistance_levels = []
            
            # Find local maxima
            for i in range(5, len(highs) - 5):
                if highs.iloc[i] == highs.iloc[i-5:i+5].max():
                    resistance_levels.append(float(highs.iloc[i]))
            
            # Return unique levels
            return sorted(set(resistance_levels))[-num_levels:]
        except:
            return []
    
    def _calculate_atr(self, stock_data, period=14):
        """Calculate Average True Range"""
        try:
            df = stock_data.copy()
            df['H-L'] = df['High'] - df['Low']
            df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
            df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
            df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            atr = df['TR'].rolling(window=period).mean().iloc[-1]
            return float(atr) if pd.notna(atr) else 1.0
        except:
            return 1.0
    
    def _interpret_volume(self, volume_ratio, ad_trend, correlation):
        """Interpret volume analysis"""
        interpretations = []
        
        if volume_ratio > 2.0:
            interpretations.append("⚡ Exceptional volume surge - significant market interest")
        elif volume_ratio > 1.5:
            interpretations.append("📈 High volume - increased trading activity")
        elif volume_ratio < 0.7:
            interpretations.append("📉 Low volume - reduced market interest")
        
        if ad_trend == 'accumulation':
            interpretations.append("✅ Accumulation pattern - buying pressure")
        else:
            interpretations.append("⚠️ Distribution pattern - selling pressure")
        
        if pd.notna(correlation):
            if correlation > 0.5:
                interpretations.append("🔗 Strong positive volume-price correlation")
            elif correlation < -0.5:
                interpretations.append("🔄 Negative volume-price divergence")
        
        return " | ".join(interpretations) if interpretations else "Normal volume activity"
