"""
Portfolio Analyzer - Phase 4
Comprehensive portfolio analysis with P&L, risk metrics, and recommendations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import logging
import traceback
from models import db, Portfolio, OptionsPosition, Transaction, PortfolioSnapshot
from sqlalchemy import func

logger = logging.getLogger(__name__)

class PortfolioAnalyzer:
    """
    Analyze portfolio holdings with real-time P&L, risk metrics, and recommendations
    """
    
    def __init__(self):
        self.risk_free_rate = 0.045  # 4.5% for T-Bills
    
    def analyze_portfolio(self, user_id):
        """
        Complete portfolio analysis
        
        Args:
            user_id: User ID
            
        Returns:
            dict: Portfolio summary with P&L, allocation, risk metrics
        """
        try:
            # Get all holdings
            stock_holdings = Portfolio.query.filter_by(user_id=user_id).all()
            options_holdings = OptionsPosition.query.filter_by(
                user_id=user_id,
                status='open'
            ).all()
            
            if not stock_holdings and not options_holdings:
                return {
                    'total_value': 0,
                    'total_cost_basis': 0,
                    'total_pnl': 0,
                    'total_pnl_pct': 0,
                    'holdings_count': 0,
                    'message': 'No holdings in portfolio'
                }
            
            # Update current prices
            self._update_portfolio_prices(stock_holdings, options_holdings)
            
            # Calculate totals
            stock_value = sum(float(h.quantity * h.current_price) for h in stock_holdings)
            stock_cost = sum(float(h.quantity * h.average_cost) for h in stock_holdings)
            
            options_value = 0
            options_cost = 0
            for opt in options_holdings:
                premium = float(opt.current_premium if opt.current_premium else opt.premium_paid)
                options_value += opt.quantity * premium * 100
                options_cost += opt.quantity * float(opt.premium_paid) * 100
            
            total_value = stock_value + options_value
            total_cost = stock_cost + options_cost
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            
            # Calculate daily change
            daily_change = self._calculate_daily_change(user_id, total_value)
            
            # Asset allocation
            allocation = {
                'stocks': round(stock_value / total_value * 100, 1) if total_value > 0 else 0,
                'options': round(options_value / total_value * 100, 1) if total_value > 0 else 0
            }
            
            # Risk metrics
            risk_metrics = self._calculate_portfolio_risk(stock_holdings, options_holdings)
            
            # Top positions
            top_gainers = self._get_top_positions(stock_holdings, 'gainers', 3)
            top_losers = self._get_top_positions(stock_holdings, 'losers', 3)
            
            return {
                'total_value': round(total_value, 2),
                'total_cost_basis': round(total_cost, 2),
                'total_pnl': round(total_pnl, 2),
                'total_pnl_pct': round(total_pnl_pct, 2),
                'daily_change': daily_change,
                'stock_value': round(stock_value, 2),
                'options_value': round(options_value, 2),
                'allocation': allocation,
                'holdings_count': len(stock_holdings) + len(options_holdings),
                'stock_count': len(stock_holdings),
                'options_count': len(options_holdings),
                'risk_metrics': risk_metrics,
                'top_gainers': top_gainers,
                'top_losers': top_losers,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing portfolio: {str(e)}")
            return None
    
    def analyze_holding(self, holding_id, holding_type='stock'):
        """
        Deep analysis of single holding with recommendations
        
        Args:
            holding_id: Holding ID
            holding_type: 'stock' or 'option'
            
        Returns:
            dict: Detailed holding analysis with Phase 3 integration
        """
        try:
            if holding_type == 'stock':
                holding = Portfolio.query.get(holding_id)
            else:
                holding = OptionsPosition.query.get(holding_id)
            
            if not holding:
                return None
            
            # Get current price
            symbol = holding.symbol if holding_type == 'stock' else holding.underlying_symbol
            current_price = self._fetch_current_price(symbol)
            
            # Calculate P&L
            if holding_type == 'stock':
                quantity = float(holding.quantity)
                cost_basis = float(holding.average_cost)
                market_value = quantity * current_price
                total_cost = quantity * cost_basis
            else:
                quantity = holding.quantity
                cost_basis = float(holding.premium_paid)
                # Update current_premium
                current_premium = self._fetch_option_price(holding)
                holding.current_premium = current_premium
                market_value = quantity * current_premium * 100
                total_cost = quantity * cost_basis * 100
            
            pnl = market_value - total_cost
            pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
            
            # Get Phase 3 analysis
            phase3_analysis = self._get_phase3_analysis(symbol)
            
            # Generate recommendation
            recommendation = self._generate_recommendation(
                holding, pnl_pct, phase3_analysis, holding_type
            )
            
            # Risk contribution
            risk_contrib = self._calculate_risk_contribution(holding, holding_type)
            
            result = {
                'id': holding_id,
                'symbol': symbol,
                'type': holding_type,
                'quantity': quantity,
                'cost_basis': round(cost_basis, 4),
                'current_price': round(current_price, 2),
                'market_value': round(market_value, 2),
                'total_cost': round(total_cost, 2),
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'risk_contribution': risk_contrib,
                'recommendation': recommendation,
                'phase3': phase3_analysis
            }
            
            # Add option-specific data
            if holding_type == 'option':
                result['option_details'] = {
                    'type': holding.option_type,
                    'strike': float(holding.strike_price),
                    'expiration': holding.expiration_date.isoformat(),
                    'days_to_expiry': (holding.expiration_date - datetime.now().date()).days,
                    'premium_paid': float(holding.premium_paid),
                    'current_premium': round(current_premium, 4)
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing holding {holding_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def calculate_position_size_recommendation(self, symbol, portfolio_value, risk_tolerance='moderate'):
        """
        Recommend position size using Kelly Criterion and risk tolerance
        
        Args:
            symbol: Stock symbol
            portfolio_value: Total portfolio value
            risk_tolerance: 'conservative', 'moderate', 'aggressive'
            
        Returns:
            dict: Recommended position size and reasoning
        """
        try:
            # Get volatility data
            ticker = yf.Ticker(symbol)
            hist_data = ticker.history(period='3mo')
            
            if hist_data.empty:
                return None
            
            # Calculate volatility
            returns = hist_data['Close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)  # Annualized
            
            # Risk tolerance factors
            risk_factors = {
                'conservative': 0.02,  # 2% of portfolio per position
                'moderate': 0.05,      # 5% of portfolio
                'aggressive': 0.10     # 10% of portfolio
            }
            
            base_allocation = risk_factors.get(risk_tolerance, 0.05)
            
            # Adjust for volatility (reduce size for volatile stocks)
            if volatility > 0.50:  # >50% annual volatility
                adj_factor = 0.5
            elif volatility > 0.35:  # >35% annual volatility
                adj_factor = 0.75
            else:
                adj_factor = 1.0
            
            recommended_pct = base_allocation * adj_factor
            recommended_dollars = portfolio_value * recommended_pct
            
            # Calculate shares
            current_price = hist_data['Close'].iloc[-1]
            recommended_shares = int(recommended_dollars / current_price)
            actual_dollars = recommended_shares * current_price
            
            return {
                'symbol': symbol,
                'recommended_pct': round(recommended_pct * 100, 2),
                'recommended_dollars': round(recommended_dollars, 2),
                'recommended_shares': recommended_shares,
                'actual_cost': round(actual_dollars, 2),
                'current_price': round(current_price, 2),
                'volatility': round(volatility, 3),
                'risk_tolerance': risk_tolerance,
                'reasoning': f"Based on {risk_tolerance} risk tolerance and {volatility:.1%} volatility"
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {str(e)}")
            return None
    
    def get_rebalancing_suggestions(self, user_id):
        """
        Suggest portfolio rebalancing based on risk and allocation
        
        Args:
            user_id: User ID
            
        Returns:
            list: Rebalancing suggestions
        """
        try:
            portfolio_analysis = self.analyze_portfolio(user_id)
            
            if not portfolio_analysis or portfolio_analysis.get('holdings_count', 0) == 0:
                return []
            
            suggestions = []
            
            # Check if portfolio is too concentrated
            holdings = Portfolio.query.filter_by(user_id=user_id).all()
            self._update_portfolio_prices(holdings, [])
            
            total_value = portfolio_analysis['stock_value']
            
            for holding in holdings:
                position_value = float(holding.quantity * holding.current_price)
                position_pct = (position_value / total_value * 100) if total_value > 0 else 0
                
                # Flag positions >25% of portfolio
                if position_pct > 25:
                    suggestions.append({
                        'symbol': holding.symbol,
                        'action': 'TRIM',
                        'current_pct': round(position_pct, 1),
                        'reason': f'{holding.symbol} is {position_pct:.1f}% of portfolio (too concentrated)',
                        'recommendation': f'Consider reducing to 15-20% of portfolio'
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating rebalancing suggestions: {str(e)}")
            return []
    
    def save_portfolio_snapshot(self, user_id):
        """
        Save current portfolio state for historical tracking
        
        Args:
            user_id: User ID
        """
        try:
            analysis = self.analyze_portfolio(user_id)
            
            if not analysis:
                return
            
            snapshot = PortfolioSnapshot(
                user_id=user_id,
                total_value=analysis['total_value'],
                total_cost_basis=analysis['total_cost_basis'],
                total_pnl=analysis['total_pnl'],
                total_pnl_pct=analysis['total_pnl_pct'],
                daily_change=analysis.get('daily_change', {}).get('value', 0),
                daily_change_pct=analysis.get('daily_change', {}).get('pct', 0),
                stock_value=analysis['stock_value'],
                options_value=analysis['options_value']
            )
            
            db.session.add(snapshot)
            db.session.commit()
            
            logger.info(f"Saved portfolio snapshot for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error saving portfolio snapshot: {str(e)}")
            db.session.rollback()
    
    def _update_portfolio_prices(self, stock_holdings, options_holdings):
        """Update current prices for all holdings"""
        try:
            # Update stock prices
            symbols = [h.symbol for h in stock_holdings]
            if symbols:
                prices = self._fetch_batch_prices(symbols)
                for holding in stock_holdings:
                    if holding.symbol in prices:
                        holding.current_price = prices[holding.symbol]
                        holding.last_updated = datetime.now()
            
            # Update options prices
            for opt in options_holdings:
                current_premium = self._fetch_option_price(opt)
                opt.current_premium = current_premium
            
            if stock_holdings or options_holdings:
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Error updating portfolio prices: {str(e)}")
            db.session.rollback()
    
    def _fetch_current_price(self, symbol):
        """Fetch current price for symbol"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if not data.empty:
                return data['Close'].iloc[-1]
            return 0
        except:
            return 0
    
    def _fetch_batch_prices(self, symbols):
        """Fetch prices for multiple symbols"""
        prices = {}
        try:
            tickers = yf.Tickers(' '.join(symbols))
            for symbol in symbols:
                try:
                    data = tickers.tickers[symbol].history(period='1d')
                    if not data.empty:
                        prices[symbol] = data['Close'].iloc[-1]
                except:
                    pass
        except:
            # Fallback to individual fetches
            for symbol in symbols:
                prices[symbol] = self._fetch_current_price(symbol)
        
        return prices
    
    def _fetch_option_price(self, option_holding):
        """Estimate current option price (simplified)"""
        try:
            # For real implementation, would use options chain data
            # For now, use intrinsic value as approximation
            ticker = yf.Ticker(option_holding.underlying_symbol)
            data = ticker.history(period='1d')
            
            if data.empty:
                return float(option_holding.premium_paid)
            
            current_stock_price = data['Close'].iloc[-1]
            strike = float(option_holding.strike_price)
            
            if option_holding.option_type == 'call':
                intrinsic = max(0, current_stock_price - strike)
            else:
                intrinsic = max(0, strike - current_stock_price)
            
            # Add time value estimate (simplified)
            days_to_expiry = (option_holding.expiration_date - datetime.now().date()).days
            time_value = intrinsic * 0.1 * (days_to_expiry / 30) if days_to_expiry > 0 else 0
            
            estimated_premium = intrinsic + time_value
            return max(0.01, estimated_premium)  # Minimum 1 cent
            
        except Exception as e:
            logger.error(f"Error fetching option price: {str(e)}")
            return float(option_holding.premium_paid)
    
    def _calculate_daily_change(self, user_id, current_value):
        """Calculate daily portfolio change"""
        try:
            yesterday = datetime.now() - timedelta(days=1)
            
            last_snapshot = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.timestamp >= yesterday
            ).order_by(PortfolioSnapshot.timestamp.desc()).first()
            
            if last_snapshot:
                previous_value = float(last_snapshot.total_value)
                change = current_value - previous_value
                change_pct = (change / previous_value * 100) if previous_value > 0 else 0
                
                return {
                    'value': round(change, 2),
                    'pct': round(change_pct, 2)
                }
            
            return {'value': 0, 'pct': 0}
            
        except:
            return {'value': 0, 'pct': 0}
    
    def _calculate_portfolio_risk(self, stock_holdings, options_holdings):
        """Calculate portfolio-level risk metrics"""
        try:
            if not stock_holdings:
                return {}
            
            # Simplified portfolio volatility
            total_volatility_weighted = 0
            total_weight = 0
            
            for holding in stock_holdings:
                try:
                    ticker = yf.Ticker(holding.symbol)
                    hist = ticker.history(period='1mo')
                    if len(hist) > 5:
                        returns = hist['Close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)
                        
                        weight = float(holding.quantity * holding.current_price)
                        total_volatility_weighted += vol * weight
                        total_weight += weight
                except:
                    pass
            
            if total_weight > 0:
                portfolio_volatility = total_volatility_weighted / total_weight
            else:
                portfolio_volatility = 0
            
            # Risk grade
            if portfolio_volatility < 0.15:
                risk_grade = 'Low'
            elif portfolio_volatility < 0.25:
                risk_grade = 'Moderate'
            elif portfolio_volatility < 0.35:
                risk_grade = 'High'
            else:
                risk_grade = 'Very High'
            
            return {
                'portfolio_volatility': round(portfolio_volatility, 3),
                'risk_grade': risk_grade,
                'diversification_score': min(100, len(stock_holdings) * 10)  # Simple score
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio risk: {str(e)}")
            return {}
    
    def _get_top_positions(self, holdings, position_type, limit=3):
        """Get top gainers or losers"""
        try:
            positions_with_pnl = []
            
            for holding in holdings:
                quantity = float(holding.quantity)
                cost = float(holding.average_cost)
                current = float(holding.current_price)
                
                pnl_pct = ((current - cost) / cost * 100) if cost > 0 else 0
                
                positions_with_pnl.append({
                    'symbol': holding.symbol,
                    'pnl_pct': round(pnl_pct, 2),
                    'pnl': round(quantity * (current - cost), 2)
                })
            
            # Sort
            if position_type == 'gainers':
                sorted_positions = sorted(positions_with_pnl, key=lambda x: x['pnl_pct'], reverse=True)
            else:
                sorted_positions = sorted(positions_with_pnl, key=lambda x: x['pnl_pct'])
            
            return sorted_positions[:limit]
            
        except:
            return []
    
    def _get_phase3_analysis(self, symbol):
        """Get Phase 3 analysis for symbol (if available)"""
        try:
            # Import Phase 3 modules if available
            from sentiment_analyzer import SentimentAnalyzer
            from risk_analyzer import RiskAnalyzer
            from trading_time_analyzer import TradingTimeAnalyzer
            from pattern_recognizer import PatternRecognizer
            
            # Fetch stock data
            ticker = yf.Ticker(symbol)
            stock_data = ticker.history(period='6mo')
            
            if stock_data.empty or len(stock_data) < 50:
                logger.debug(f"Insufficient stock data for {symbol}")
                return None
            
            # Calculate indicators first
            pr = PatternRecognizer()
            stock_data = pr.calculate_indicators(stock_data)
            
            # Get analyses
            sa = SentimentAnalyzer()
            ra = RiskAnalyzer()
            ta = TradingTimeAnalyzer()
            
            sentiment = sa.analyze_sentiment(stock_data, symbol)
            risk = ra.comprehensive_risk_analysis(stock_data, symbol)
            timing = ta.analyze_entry_points(stock_data, symbol)
            
            return {
                'sentiment': sentiment.get('sentiment_label'),  # Fixed: was 'sentiment'
                'sentiment_score': sentiment.get('overall_score'),
                'risk_grade': risk.get('risk_grade', {}).get('grade') if isinstance(risk.get('risk_grade'), dict) else risk.get('risk_grade'),
                'risk_score': risk.get('overall_risk_score'),  # Fixed: was 'risk_score'
                'entry_score': timing.get('entry_score'),  # Fixed: was 'score'
                'entry_recommendation': timing.get('recommendation')
            }
            
        except ImportError as ie:
            logger.debug(f"Phase 3 modules not available: {ie}")
            return None
        except Exception as e:
            logger.warning(f"Error getting Phase 3 analysis for {symbol}: {str(e)}")
            return None
    
    def _generate_recommendation(self, holding, pnl_pct, phase3, holding_type):
        """Generate actionable recommendation for holding"""
        try:
            logger.debug(f"Generating recommendation for holding with pnl_pct={pnl_pct}, phase3={phase3 is not None}")
            
            # Base recommendation on P/L
            if pnl_pct > 30:
                base_action = 'TRIM'
                base_reason = f'Strong gains (+{pnl_pct:.1f}%). Consider taking some profits.'
            elif pnl_pct > 15:
                base_action = 'HOLD'
                base_reason = f'Good gains (+{pnl_pct:.1f}%). Monitor for further upside.'
            elif pnl_pct > -10:
                base_action = 'HOLD'
                base_reason = 'Position stable. Monitor for entry/exit signals.'
            elif pnl_pct > -20:
                base_action = 'REVIEW'
                base_reason = f'Underperforming ({pnl_pct:.1f}%). Review thesis.'
            else:
                base_action = 'CONSIDER_SELLING'
                base_reason = f'Significant loss ({pnl_pct:.1f}%). Consider cutting losses.'
            
            # Adjust based on Phase 3 if available
            if phase3 and isinstance(phase3, dict):
                risk_grade = phase3.get('risk_grade')
                sentiment = phase3.get('sentiment')
                entry_score = phase3.get('entry_score', 0)
                
                if risk_grade in ['D', 'F']:
                    base_action = 'TRIM'
                    base_reason += ' Risk grade deteriorating.'
                elif sentiment == 'Very Bearish':
                    base_action = 'REVIEW'
                    base_reason += ' Sentiment turning negative.'
                elif entry_score and entry_score > 75 and pnl_pct < 0:
                    base_action = 'ADD'
                    base_reason = f'Strong entry signal ({entry_score:.0f}/100). May be good to average down.'
            
            logger.debug(f"Generated recommendation: {base_action}")
            
            return {
                'action': base_action,
                'reason': base_reason,
                'confidence': 'high' if phase3 else 'medium'
            }
            
        except Exception as e:
            logger.error(f"Error generating recommendation: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {'action': 'HOLD', 'reason': 'Unable to generate recommendation', 'confidence': 'low'}
    
    def _calculate_risk_contribution(self, holding, holding_type):
        """Calculate how much this position contributes to portfolio risk"""
        try:
            if holding_type == 'stock':
                ticker = yf.Ticker(holding.symbol)
                hist = ticker.history(period='1mo')
                
                if len(hist) > 5:
                    returns = hist['Close'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(252)
                    
                    position_value = float(holding.quantity * holding.current_price)
                    risk_contribution = volatility * position_value
                    
                    return round(risk_contribution, 2)
            
            return 0
            
        except:
            return 0


# Standalone testing
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Portfolio Analyzer Module - Ready for integration")
