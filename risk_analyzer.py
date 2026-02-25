"""
Advanced Risk Analysis Module
Phase 3: Comprehensive risk assessment with VaR, volatility, and risk scoring
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import logging

logger = logging.getLogger(__name__)


class RiskAnalyzer:
    """Advanced risk analysis and scoring system"""
    
    def __init__(self):
        """Initialize risk analyzer"""
        self.confidence_level = 0.95  # 95% confidence for VaR
        
    def comprehensive_risk_analysis(self, stock_data, symbol, position_size=None, portfolio_value=None):
        """
        Comprehensive risk assessment
        
        Args:
            stock_data: DataFrame with OHLCV data
            symbol: Stock symbol
            position_size: Number of shares (optional)
            portfolio_value: Total portfolio value (optional)
            
        Returns:
            dict: Complete risk analysis
        """
        try:
            if len(stock_data) < 30:
                return {'error': 'Insufficient data for risk analysis'}
            
            latest = stock_data.iloc[-1]
            current_price = float(latest['Close'])
            
            # Calculate various risk metrics
            volatility_metrics = self._calculate_volatility(stock_data)
            var_metrics = self._calculate_var(stock_data)
            risk_scores = self._calculate_risk_scores(stock_data, volatility_metrics)
            liquidity_risk = self._assess_liquidity_risk(stock_data)
            beta = self._calculate_beta(stock_data)
            
            # Position-specific risk (if position provided)
            position_risk = None
            if position_size and portfolio_value:
                position_risk = self._calculate_position_risk(
                    current_price, position_size, portfolio_value, 
                    var_metrics, volatility_metrics
                )
            
            # Overall risk grade
            overall_score = risk_scores['overall_score']
            risk_grade = self._assign_risk_grade(overall_score)
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'overall_risk_score': round(overall_score, 1),
                'risk_grade': risk_grade,
                'volatility': volatility_metrics,
                'value_at_risk': var_metrics,
                'risk_breakdown': risk_scores,
                'liquidity_risk': liquidity_risk,
                'beta': beta,
                'position_risk': position_risk,
                'recommendations': self._generate_risk_recommendations(risk_grade, risk_scores),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error in risk analysis for {symbol}: {e}")
            return {'error': str(e)}
    
    def _calculate_volatility(self, stock_data):
        """Calculate comprehensive volatility metrics"""
        try:
            returns = stock_data['Close'].pct_change().dropna()
            
            # Historical volatility (annualized)
            daily_vol = returns.std()
            annual_vol = daily_vol * np.sqrt(252)
            
            # Recent volatility (last 20 days)
            recent_returns = returns.tail(20)
            recent_vol = recent_returns.std() * np.sqrt(252)
            
            # Volatility trend
            vol_20 = returns.tail(20).std()
            vol_60 = returns.tail(60).std()
            vol_trend = 'increasing' if vol_20 > vol_60 else 'decreasing'
            
            # Parkinson's volatility (using high-low range)
            recent = stock_data.tail(20)
            parkinson_vol = np.sqrt(
                (1 / (4 * len(recent) * np.log(2))) * 
                ((np.log(recent['High'] / recent['Low']) ** 2).sum())
            ) * np.sqrt(252)
            
            return {
                'annual_volatility': round(float(annual_vol * 100), 2),
                'recent_volatility_20d': round(float(recent_vol * 100), 2),
                'volatility_trend': vol_trend,
                'parkinson_volatility': round(float(parkinson_vol * 100), 2),
                'percentile': self._volatility_percentile(annual_vol)
            }
        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return {}
    
    def _calculate_var(self, stock_data, confidence=0.95):
        """Calculate Value at Risk (VaR) using multiple methods"""
        try:
            returns = stock_data['Close'].pct_change().dropna()
            current_price = float(stock_data.iloc[-1]['Close'])
            
            # Historical VaR
            var_historical = np.percentile(returns, (1 - confidence) * 100)
            
            # Parametric VaR (assuming normal distribution)
            mean_return = returns.mean()
            std_return = returns.std()
            var_parametric = mean_return - (stats.norm.ppf(1 - confidence) * std_return)
            
            # 1-day VaR in dollars
            var_1day_dollar = current_price * abs(var_historical)
            
            # 10-day VaR (sqrt of time rule)
            var_10day_pct = var_historical * np.sqrt(10)
            var_10day_dollar = current_price * abs(var_10day_pct)
            
            # Maximum drawdown
            cumulative_returns = (1 + returns).cumprod()
            running_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - running_max) / running_max
            max_drawdown = drawdown.min()
            
            return {
                'var_1day_pct': round(float(var_historical * 100), 2),
                'var_1day_dollar': round(float(var_1day_dollar), 2),
                'var_10day_pct': round(float(var_10day_pct * 100), 2),
                'var_10day_dollar': round(float(var_10day_dollar), 2),
                'confidence_level': int(confidence * 100),
                'max_drawdown_pct': round(float(max_drawdown * 100), 2),
                'interpretation': f'95% confidence: Maximum 1-day loss of ${var_1day_dollar:.2f} per share'
            }
        except Exception as e:
            logger.error(f"Error calculating VaR: {e}")
            return {}
    
    def _calculate_risk_scores(self, stock_data, volatility_metrics):
        """Calculate individual risk component scores"""
        try:
            scores = {}
            
            # 1. Volatility Risk (0-100, higher = more risk)
            annual_vol = volatility_metrics.get('annual_volatility', 30)
            if annual_vol > 50:
                vol_score = 90
            elif annual_vol > 35:
                vol_score = 70
            elif annual_vol > 25:
                vol_score = 50
            elif annual_vol > 15:
                vol_score = 30
            else:
                vol_score = 10
            
            scores['volatility_risk'] = {
                'score': vol_score,
                'level': self._risk_level(vol_score),
                'description': f'{annual_vol}% annual volatility'
            }
            
            # 2. Price Stability Risk
            returns = stock_data['Close'].pct_change().tail(60)
            price_swings = (returns.abs() > 0.05).sum()  # Days with >5% moves
            swing_pct = (price_swings / len(returns)) * 100
            
            if swing_pct > 30:
                stability_score = 85
            elif swing_pct > 20:
                stability_score = 65
            elif swing_pct > 10:
                stability_score = 45
            else:
                stability_score = 25
            
            scores['price_stability_risk'] = {
                'score': stability_score,
                'level': self._risk_level(stability_score),
                'description': f'{swing_pct:.1f}% of days had >5% moves'
            }
            
            # 3. Trend Risk
            recent = stock_data.tail(50)
            sma_20 = recent['Close'].rolling(20).mean().iloc[-1]
            sma_50 = recent['Close'].rolling(50).mean().iloc[-1]
            current_price = float(stock_data.iloc[-1]['Close'])
            
            if current_price < sma_20 < sma_50:  # Downtrend
                trend_score = 75
            elif current_price > sma_20 > sma_50:  # Uptrend
                trend_score = 30
            else:  # Unclear trend
                trend_score = 55
            
            scores['trend_risk'] = {
                'score': trend_score,
                'level': self._risk_level(trend_score),
                'description': 'Based on moving average alignment'
            }
            
            # 4. Technical Indicator Risk
            latest = stock_data.iloc[-1]
            tech_risk_score = 50
            
            if pd.notna(latest.get('RSI')):
                rsi = float(latest['RSI'])
                if rsi > 70 or rsi < 30:
                    tech_risk_score += 15  # Extreme conditions = higher risk
            
            if pd.notna(latest.get('BB_High')) and pd.notna(latest.get('BB_Low')):
                bb_high = float(latest['BB_High'])
                bb_low = float(latest['BB_Low'])
                if current_price >= bb_high or current_price <= bb_low:
                    tech_risk_score += 10  # Outside bands = higher risk
            
            tech_risk_score = min(100, tech_risk_score)
            
            scores['technical_risk'] = {
                'score': tech_risk_score,
                'level': self._risk_level(tech_risk_score),
                'description': 'Based on RSI and Bollinger Bands'
            }
            
            # Calculate overall score (weighted average)
            overall = (
                scores['volatility_risk']['score'] * 0.35 +
                scores['price_stability_risk']['score'] * 0.25 +
                scores['trend_risk']['score'] * 0.25 +
                scores['technical_risk']['score'] * 0.15
            )
            
            scores['overall_score'] = round(overall, 1)
            
            return scores
            
        except Exception as e:
            logger.error(f"Error calculating risk scores: {e}")
            return {'overall_score': 50}
    
    def _assess_liquidity_risk(self, stock_data):
        """Assess liquidity risk based on volume and spread"""
        try:
            recent = stock_data.tail(20)
            
            # Average volume
            avg_volume = recent['Volume'].mean()
            
            # Volume consistency
            volume_std = recent['Volume'].std()
            volume_cv = (volume_std / avg_volume) if avg_volume > 0 else 0
            
            # Bid-ask spread proxy (High-Low range)
            avg_spread_pct = ((recent['High'] - recent['Low']) / recent['Close']).mean() * 100
            
            # Liquidity score (0-100, higher = better liquidity, lower risk)
            if avg_volume > 10_000_000:  # Very liquid
                volume_score = 90
            elif avg_volume > 1_000_000:
                volume_score = 70
            elif avg_volume > 100_000:
                volume_score = 50
            else:
                volume_score = 30
            
            # Spread score
            if avg_spread_pct < 1:
                spread_score = 90
            elif avg_spread_pct < 2:
                spread_score = 70
            elif avg_spread_pct < 3:
                spread_score = 50
            else:
                spread_score = 30
            
            liquidity_score = (volume_score * 0.6 + spread_score * 0.4)
            risk_score = 100 - liquidity_score  # Convert to risk
            
            return {
                'score': round(risk_score, 1),
                'level': self._risk_level(risk_score),
                'average_volume': int(avg_volume),
                'average_spread_pct': round(float(avg_spread_pct), 2),
                'description': f'{"Low" if risk_score < 40 else "Moderate" if risk_score < 70 else "High"} liquidity risk'
            }
        except Exception as e:
            logger.error(f"Error assessing liquidity risk: {e}")
            return {}
    
    def _calculate_beta(self, stock_data):
        """Calculate beta coefficient (market risk)"""
        try:
            # This is a simplified beta using 200-day rolling correlation
            # In production, would compare to actual market index (SPY)
            returns = stock_data['Close'].pct_change().dropna()
            
            if len(returns) < 100:
                return {'beta': None, 'description': 'Insufficient data'}
            
            # Rolling volatility as proxy for market comparison
            rolling_std = returns.rolling(60).std()
            overall_std = returns.std()
            
            # Simplified beta approximation
            beta_estimate = (overall_std / rolling_std.mean()) if rolling_std.mean() > 0 else 1.0
            
            # Clamp to reasonable range
            beta_estimate = max(0.5, min(2.0, float(beta_estimate)))
            
            if beta_estimate > 1.2:
                interpretation = 'High market sensitivity - amplifies market moves'
            elif beta_estimate > 0.8:
                interpretation = 'Average market sensitivity'
            else:
                interpretation = 'Low market sensitivity - defensive stock'
            
            return {
                'beta': round(beta_estimate, 2),
                'interpretation': interpretation,
                'note': 'Simplified calculation - compare to market index for accurate beta'
            }
        except Exception as e:
            logger.error(f"Error calculating beta: {e}")
            return {'beta': None, 'description': 'Unable to calculate'}
    
    def _calculate_position_risk(self, current_price, position_size, portfolio_value, 
                                 var_metrics, volatility_metrics):
        """Calculate position-specific risk metrics"""
        try:
            position_value = current_price * position_size
            portfolio_allocation = (position_value / portfolio_value) * 100
            
            # Recommended position size (using Kelly Criterion approximation)
            annual_vol = volatility_metrics.get('annual_volatility', 30) / 100
            recommended_allocation = min(25, max(5, (1 / (annual_vol * 4)) * 100))
            
            # Position risk score
            if portfolio_allocation > 25:
                position_risk_score = 90
                risk_level = 'Excessive'
            elif portfolio_allocation > 15:
                position_risk_score = 70
                risk_level = 'High'
            elif portfolio_allocation > 10:
                position_risk_score = 50
                risk_level = 'Moderate'
            else:
                position_risk_score = 30
                risk_level = 'Low'
            
            # Calculate potential loss
            var_1day = var_metrics.get('var_1day_dollar', 0)
            potential_loss_1day = abs(var_1day) * position_size
            potential_loss_pct_portfolio = (potential_loss_1day / portfolio_value) * 100
            
            return {
                'position_value': round(position_value, 2),
                'portfolio_allocation_pct': round(portfolio_allocation, 2),
                'recommended_allocation_pct': round(recommended_allocation, 1),
                'allocation_status': 'Overweight' if portfolio_allocation > recommended_allocation else 'Appropriate',
                'position_risk_score': position_risk_score,
                'position_risk_level': risk_level,
                'potential_1day_loss': round(potential_loss_1day, 2),
                'potential_loss_pct_portfolio': round(potential_loss_pct_portfolio, 2),
                'recommendation': self._position_recommendation(portfolio_allocation, recommended_allocation)
            }
        except Exception as e:
            logger.error(f"Error calculating position risk: {e}")
            return {}
    
    def _volatility_percentile(self, annual_vol):
        """Determine volatility percentile"""
        if annual_vol < 0.15:
            return 'Very Low (<15th percentile)'
        elif annual_vol < 0.25:
            return 'Low (15-40th percentile)'
        elif annual_vol < 0.35:
            return 'Average (40-60th percentile)'
        elif annual_vol < 0.50:
            return 'High (60-85th percentile)'
        else:
            return 'Very High (>85th percentile)'
    
    def _risk_level(self, score):
        """Convert risk score to level"""
        if score >= 75:
            return 'Very High'
        elif score >= 60:
            return 'High'
        elif score >= 40:
            return 'Moderate'
        elif score >= 25:
            return 'Low'
        else:
            return 'Very Low'
    
    def _assign_risk_grade(self, score):
        """Assign letter grade based on risk score"""
        if score >= 80:
            return {'grade': 'F', 'description': 'Extreme Risk', 'color': 'red'}
        elif score >= 70:
            return {'grade': 'D', 'description': 'High Risk', 'color': 'orange'}
        elif score >= 55:
            return {'grade': 'C', 'description': 'Moderate Risk', 'color': 'yellow'}
        elif score >= 40:
            return {'grade': 'B', 'description': 'Low-Moderate Risk', 'color': 'lightgreen'}
        else:
            return {'grade': 'A', 'description': 'Low Risk', 'color': 'green'}
    
    def _generate_risk_recommendations(self, risk_grade, risk_scores):
        """Generate risk management recommendations"""
        recommendations = []
        
        grade = risk_grade['grade']
        
        if grade in ['D', 'F']:
            recommendations.append('⚠️ High risk asset - consider reducing position size')
            recommendations.append('📊 Use tight stop-losses (3-5%)')
            recommendations.append('⏰ Monitor position daily')
        elif grade == 'C':
            recommendations.append('⚡ Moderate risk - appropriate for growth portfolios')
            recommendations.append('📊 Use standard stop-losses (7-10%)')
            recommendations.append('⏰ Monitor position weekly')
        else:
            recommendations.append('✅ Lower risk - suitable for conservative portfolios')
            recommendations.append('📊 Use wider stop-losses (10-15%)')
            recommendations.append('⏰ Monitor position monthly')
        
        # Volatility-specific recommendations
        vol_score = risk_scores.get('volatility_risk', {}).get('score', 50)
        if vol_score > 70:
            recommendations.append('🎢 High volatility - consider options for hedging')
        
        return recommendations
    
    def _position_recommendation(self, current_allocation, recommended_allocation):
        """Generate position sizing recommendation"""
        if current_allocation > recommended_allocation * 1.5:
            return f'🔴 Consider reducing position - currently {current_allocation:.1f}% vs recommended {recommended_allocation:.1f}%'
        elif current_allocation > recommended_allocation * 1.2:
            return f'🟡 Position slightly large - monitor closely'
        elif current_allocation < recommended_allocation * 0.5:
            return f'🟢 Could increase position size if desired'
        else:
            return f'✅ Position size appropriate'
    
    def calculate_position_sizing(self, account_value, risk_per_trade_pct, 
                                  entry_price, stop_loss_price):
        """
        Calculate optimal position size using risk management rules
        
        Args:
            account_value: Total account value
            risk_per_trade_pct: Max risk per trade (e.g., 2 for 2%)
            entry_price: Planned entry price
            stop_loss_price: Planned stop loss price
            
        Returns:
            dict: Position sizing recommendation
        """
        try:
            # Calculate risk per share
            risk_per_share = abs(entry_price - stop_loss_price)
            
            # Calculate max dollar risk
            max_risk_dollars = account_value * (risk_per_trade_pct / 100)
            
            # Calculate number of shares
            shares = int(max_risk_dollars / risk_per_share)
            
            # Calculate actual position value
            position_value = shares * entry_price
            
            # Calculate portfolio allocation
            portfolio_allocation = (position_value / account_value) * 100
            
            return {
                'recommended_shares': shares,
                'position_value': round(position_value, 2),
                'portfolio_allocation_pct': round(portfolio_allocation, 2),
                'risk_per_share': round(risk_per_share, 2),
                'max_loss_dollars': round(max_risk_dollars, 2),
                'max_loss_pct': risk_per_trade_pct,
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price,
                'recommendation': f'Buy {shares} shares at ${entry_price:.2f} with stop at ${stop_loss_price:.2f}'
            }
        except Exception as e:
            logger.error(f"Error calculating position sizing: {e}")
            return {'error': str(e)}
