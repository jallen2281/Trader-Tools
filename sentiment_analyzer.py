"""
Market Sentiment Analysis Module
Phase 3: Multi-source sentiment scoring and market breadth analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Analyzes market sentiment from multiple technical sources"""
    
    def __init__(self):
        """Initialize sentiment analyzer"""
        pass
    
    def analyze_sentiment(self, stock_data, symbol):
        """
        Comprehensive sentiment analysis from multiple indicators
        
        Args:
            stock_data: DataFrame with OHLCV and indicators
            symbol: Stock symbol
            
        Returns:
            dict: Sentiment analysis with overall score
        """
        try:
            if len(stock_data) < 50:
                return {'error': 'Insufficient data for sentiment analysis'}
            
            latest = stock_data.iloc[-1]
            
            # Collect sentiment from multiple sources
            sentiments = {}
            total_weight = 0
            weighted_score = 0
            
            # 1. RSI Sentiment (Weight: 15%)
            rsi_sentiment = self._rsi_sentiment(latest)
            if rsi_sentiment:
                sentiments['rsi'] = rsi_sentiment
                weighted_score += rsi_sentiment['score'] * 0.15
                total_weight += 0.15
            
            # 2. MACD Sentiment (Weight: 15%)
            macd_sentiment = self._macd_sentiment(stock_data)
            if macd_sentiment:
                sentiments['macd'] = macd_sentiment
                weighted_score += macd_sentiment['score'] * 0.15
                total_weight += 0.15
            
            # 3. Moving Average Sentiment (Weight: 20%)
            ma_sentiment = self._moving_average_sentiment(stock_data)
            if ma_sentiment:
                sentiments['moving_averages'] = ma_sentiment
                weighted_score += ma_sentiment['score'] * 0.20
                total_weight += 0.20
            
            # 4. Volume Sentiment (Weight: 15%)
            volume_sentiment = self._volume_sentiment(stock_data)
            if volume_sentiment:
                sentiments['volume'] = volume_sentiment
                weighted_score += volume_sentiment['score'] * 0.15
                total_weight += 0.15
            
            # 5. Price Action Sentiment (Weight: 20%)
            price_sentiment = self._price_action_sentiment(stock_data)
            if price_sentiment:
                sentiments['price_action'] = price_sentiment
                weighted_score += price_sentiment['score'] * 0.20
                total_weight += 0.20
            
            # 6. Bollinger Band Sentiment (Weight: 15%)
            bb_sentiment = self._bollinger_band_sentiment(latest)
            if bb_sentiment:
                sentiments['bollinger_bands'] = bb_sentiment
                weighted_score += bb_sentiment['score'] * 0.15
                total_weight += 0.15
            
            # Calculate overall sentiment score (0-100)
            overall_score = (weighted_score / total_weight * 100) if total_weight > 0 else 50
            
            # Determine sentiment label
            if overall_score >= 70:
                sentiment_label = 'Very Bullish'
                emoji = '🚀'
            elif overall_score >= 60:
                sentiment_label = 'Bullish'
                emoji = '📈'
            elif overall_score >= 45:
                sentiment_label = 'Slightly Bullish'
                emoji = '↗️'
            elif overall_score >= 40:
                sentiment_label = 'Neutral'
                emoji = '➡️'
            elif overall_score >= 30:
                sentiment_label = 'Slightly Bearish'
                emoji = '↘️'
            elif overall_score >= 20:
                sentiment_label = 'Bearish'
                emoji = '📉'
            else:
                sentiment_label = 'Very Bearish'
                emoji = '🔻'
            
           # Calculate Fear & Greed Index
            fear_greed = self._calculate_fear_greed(overall_score, sentiments)
            
            # Consensus strength
            bullish_indicators = sum(1 for s in sentiments.values() if s['score'] > 50)
            bearish_indicators = sum(1 for s in sentiments.values() if s['score'] < 50)
            consensus_strength = abs(bullish_indicators - bearish_indicators) / len(sentiments) * 100
            
            return {
                'symbol': symbol,
                'overall_score': round(overall_score, 1),
                'sentiment_label': sentiment_label,
                'emoji': emoji,
                'fear_greed_index': fear_greed,
                'consensus_strength': round(consensus_strength, 1),
                'bullish_indicators': bullish_indicators,
                'bearish_indicators': bearish_indicators,
                'neutral_indicators': len(sentiments) - bullish_indicators - bearish_indicators,
                'detailed_sentiments': sentiments,
                'recommendation': self._generate_recommendation(overall_score, consensus_strength),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment for {symbol}: {e}")
            return {'error': str(e)}
    
    def _rsi_sentiment(self, latest):
        """Analyze RSI sentiment"""
        try:
            if not pd.notna(latest.get('RSI')):
                return None
            
            rsi = float(latest['RSI'])
            
            if rsi > 70:
                score = 85
                signal = 'Overbought'
                description = 'RSI signals overbought conditions'
            elif rsi > 60:
                score = 70
                signal = 'Strong'
                description = 'RSI indicates strong momentum'
            elif rsi > 50:
                score = 60
                signal = 'Bullish'
                description = 'RSI suggests bullish conditions'
            elif rsi > 40:
                score = 40
                signal = 'Bearish'
                description = 'RSI suggests bearish conditions'
            elif rsi > 30:
                score = 30
                signal = 'Weak'
                description = 'RSI indicates weak momentum'
            else:
                score = 15
                signal = 'Oversold'
                description = 'RSI signals oversold conditions'
            
            return {
                'score': score,
                'value': round(rsi, 2),
                'signal': signal,
                'description': description
            }
        except:
            return None
    
    def _macd_sentiment(self, stock_data):
        """Analyze MACD sentiment"""
        try:
            latest = stock_data.iloc[-1]
            if not pd.notna(latest.get('MACD')) or not pd.notna(latest.get('MACD_Signal')):
                return None
            
            macd = float(latest['MACD'])
            signal = float(latest['MACD_Signal'])
            diff = macd - signal
            
            # Check for bullish/bearish crossover
            if len(stock_data) > 1:
                prev = stock_data.iloc[-2]
                prev_macd = float(prev.get('MACD', 0))
                prev_signal = float(prev.get('MACD_Signal', 0))
                
                if prev_macd <= prev_signal and macd > signal:
                    score = 75
                    signal_label = 'Bullish Crossover'
                    description = 'MACD just crossed above signal line'
                elif prev_macd >= prev_signal and macd < signal:
                    score = 25
                    signal_label = 'Bearish Crossover'
                    description = 'MACD just crossed below signal line'
                elif macd > signal and diff > 0:
                    score = 65
                    signal_label = 'Bullish'
                    description = 'MACD above signal line'
                elif macd < signal and diff < 0:
                    score = 35
                    signal_label = 'Bearish'
                    description = 'MACD below signal line'
                else:
                    score = 50
                    signal_label = 'Neutral'
                    description = 'MACD near signal line'
            else:
                score = 65 if macd > signal else 35
                signal_label = 'Bullish' if macd > signal else 'Bearish'
                description = f'MACD {"above" if macd > signal else "below"} signal'
            
            return {
                'score': score,
                'value': f'{macd:.4f} / {signal:.4f}',
                'signal': signal_label,
                'description': description
            }
        except:
            return None
    
    def _moving_average_sentiment(self, stock_data):
        """Analyze moving average sentiment"""
        try:
            latest = stock_data.iloc[-1]
            current_price = float(latest['Close'])
            
            score = 50  # Start neutral
            signals = []
            
            # Check SMA 20
            if pd.notna(latest.get('SMA_20')):
                sma20 = float(latest['SMA_20'])
                if current_price > sma20:
                    score += 10
                    signals.append('Above SMA20')
                else:
                    score -= 10
                    signals.append('Below SMA20')
            
            # Check SMA 50
            if pd.notna(latest.get('SMA_50')):
                sma50 = float(latest['SMA_50'])
                if current_price > sma50:
                    score += 10
                    signals.append('Above SMA50')
                else:
                    score -= 10
                    signals.append('Below SMA50')
            
            # Check MA alignment (SMA20 vs SMA50)
            if pd.notna(latest.get('SMA_20')) and pd.notna(latest.get('SMA_50')):
                sma20 = float(latest['SMA_20'])
                sma50 = float(latest['SMA_50'])
                
                if sma20 > sma50:
                    score += 10
                    signals.append('Bullish MA Alignment')
                else:
                    score -= 10
                    signals.append('Bearish MA Alignment')
            
            # Ensure score is between 0-100
            score = max(0, min(100, score))
            
            if score > 60:
                signal_label = 'Bullish'
            elif score < 40:
                signal_label = 'Bearish'
            else:
                signal_label = 'Neutral'
            
            return {
                'score': score,
                'value': ', '.join(signals),
                'signal': signal_label,
                'description': 'Moving average position and alignment'
            }
        except:
            return None
    
    def _volume_sentiment(self, stock_data):
        """Analyze volume sentiment"""
        try:
            recent = stock_data.tail(20)
            latest = stock_data.iloc[-1]
            
            avg_volume = recent['Volume'].mean()
            current_volume = float(latest['Volume'])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # Price direction
            price_change = float(latest['Close'] - latest['Open'])
            
            if volume_ratio > 1.5:
                if price_change > 0:
                    score = 75
                    signal = 'Strong Buying'
                    description = 'High volume with price increase'
                else:
                    score = 25
                    signal = 'Strong Selling'
                    description = 'High volume with price decrease'
            elif volume_ratio > 1.0:
                if price_change > 0:
                    score = 60
                    signal = 'Buying Pressure'
                    description = 'Above-average volume, bullish'
                else:
                    score = 40
                    signal = 'Selling Pressure'
                    description = 'Above-average volume, bearish'
            else:
                score = 50
                signal = 'Neutral'
                description = 'Normal volume activity'
            
            return {
                'score': score,
                'value': f'{volume_ratio:.2f}x avg',
                'signal': signal,
                'description': description
            }
        except:
            return None
    
    def _price_action_sentiment(self, stock_data):
        """Analyze price action sentiment"""
        try:
            recent = stock_data.tail(10)
            
            # Calculate price momentum
            returns = recent['Close'].pct_change()
            momentum = returns.sum() * 100
            
            # Count up vs down days
            up_days = (returns > 0).sum()
            down_days = (returns < 0).sum()
            
            # Recent trend
            if momentum > 5:
                score = 75
                signal = 'Strong Uptrend'
                description = f'{up_days} up days in last 10'
            elif momentum > 2:
                score = 65
                signal = 'Uptrend'
                description = f'Positive momentum, {up_days} up days'
            elif momentum > -2:
                score = 50
                signal = 'Sideways'
                description = 'Mixed price action'
            elif momentum > -5:
                score = 35
                signal = 'Downtrend'
                description = f'Negative momentum, {down_days} down days'
            else:
                score = 25
                signal = 'Strong Downtrend'
                description = f'{down_days} down days in last 10'
            
            return {
                'score': score,
                'value': f'{momentum:+.2f}%',
                'signal': signal,
                'description': description
            }
        except:
            return None
    
    def _bollinger_band_sentiment(self, latest):
        """Analyze Bollinger Band sentiment"""
        try:
            if not pd.notna(latest.get('BB_Low')) or not pd.notna(latest.get('BB_High')):
                return None
            
            price = float(latest['Close'])
            bb_low = float(latest['BB_Low'])
            bb_high = float(latest['BB_High'])
            bb_mid = (bb_low + bb_high) / 2
            
            # Calculate position within bands
            bb_range = bb_high - bb_low
            if bb_range > 0:
                bb_position = (price - bb_low) / bb_range
            else:
                bb_position = 0.5
            
            if price >= bb_high:
                score = 85
                signal = 'Upper Band'
                description = 'Price at upper Bollinger Band - overbought'
            elif bb_position > 0.75:
                score = 70
                signal = 'Strong'
                description = 'Price in upper quarter of BB range'
            elif bb_position > 0.5:
                score = 60
                signal = 'Bullish'
                description = 'Price above BB middle'
            elif bb_position > 0.25:
                score = 40
                signal = 'Bearish'
                description = 'Price below BB middle'
            elif price <= bb_low:
                score = 15
                signal = 'Lower Band'
                description = 'Price at lower Bollinger Band - oversold'
            else:
                score = 30
                signal = 'Weak'
                description = 'Price in lower quarter of BB range'
            
            return {
                'score': score,
                'value': f'{bb_position*100:.0f}% of range',
                'signal': signal,
                'description': description
            }
        except:
            return None
    
    def _calculate_fear_greed(self, overall_score, sentiments):
        """Calculate Fear & Greed Index (0-100)"""
        try:
            # Map sentiment score to fear/greed
            if overall_score >= 75:
                level = 'Extreme Greed'
                emoji = '🤑'
            elif overall_score >= 60:
                level = 'Greed'
                emoji = '😊'
            elif overall_score >= 45:
                level = 'Neutral'
                emoji = '😐'
            elif overall_score >= 30:
                level = 'Fear'
                emoji = '😰'
            else:
                level = 'Extreme Fear'
                emoji = '😱'
            
            return {
                'score': round(overall_score, 1),
                'level': level,
                'emoji': emoji
            }
        except:
            return {'score': 50, 'level': 'Neutral', 'emoji': '😐'}
    
    def _generate_recommendation(self, score, consensus):
        """Generate trading recommendation based on sentiment"""
        try:
            if score >= 70 and consensus >= 60:
                return '🟢 Strong Buy - High sentiment with strong consensus'
            elif score >= 60:
                return '🟢 Buy - Positive sentiment signals'
            elif score >= 50 and consensus < 40:
                return '🟡 Hold - Mixed signals, low consensus'
            elif score >= 40:
                return '🟡 Hold - Neutral conditions'
            elif score >= 30:
                return '🔴 Sell - Negative sentiment signals'
            else:
                return '🔴 Strong Sell - Very negative sentiment'
        except:
            return '🟡 Hold - Unable to determine'
