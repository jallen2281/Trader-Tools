"""
AI Alert Suggestion Engine
Generates proactive, intelligent alert suggestions based on technical patterns,
sentiment shifts, volatility spikes, and portfolio context
"""

from datetime import datetime, timedelta
import yfinance as yf
from typing import List, Dict, Optional
from models import db, AlertSuggestion
import logging

logger = logging.getLogger(__name__)


class AlertSuggestionEngine:
    """Generates intelligent alert suggestions"""
    
    def __init__(self, pattern_recognizer=None, sentiment_analyzer=None, 
                 volatility_monitor=None, portfolio_analyzer=None):
        self.pattern_recognizer = pattern_recognizer
        self.sentiment_analyzer = sentiment_analyzer
        self.volatility_monitor = volatility_monitor
        self.portfolio_analyzer = portfolio_analyzer
        logger.info("✓ Alert Suggestion Engine initialized")
    
    def generate_suggestions(self, symbols: List[str], portfolio_holdings: List = None) -> List[Dict]:
        """Generate alert suggestions for given symbols"""
        suggestions = []
        
        for symbol in symbols:
            try:
                # Technical pattern alerts
                pattern_suggestions = self._check_technical_patterns(symbol)
                suggestions.extend(pattern_suggestions)
                
                # Price level alerts
                price_suggestions = self._check_price_levels(symbol)
                suggestions.extend(price_suggestions)
                
                # Volatility alerts
                vol_suggestions = self._check_volatility(symbol)
                suggestions.extend(vol_suggestions)
                
                # Sentiment alerts
                sentiment_suggestions = self._check_sentiment(symbol)
                suggestions.extend(sentiment_suggestions)
                
            except Exception as e:
                logger.error(f"Error generating suggestions for {symbol}: {e}")
        
        # Portfolio-specific alerts
        if portfolio_holdings:
            portfolio_suggestions = self._check_portfolio_alerts(portfolio_holdings)
            suggestions.extend(portfolio_suggestions)
        
        # Sort by priority and limit
        suggestions.sort(key=lambda x: x['priority'], reverse=True)
        return suggestions[:10]  # Top 10 suggestions
    
    def _check_technical_patterns(self, symbol: str) -> List[Dict]:
        """Check for technical pattern breakouts"""
        suggestions = []
        
        if not self.pattern_recognizer:
            return suggestions
        
        try:
            # Get recent data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='3mo')
            
            if len(hist) < 50:
                return suggestions
            
            current_price = hist['Close'].iloc[-1]
            
            # Check for breakout patterns
            patterns = self.pattern_recognizer.detect_patterns(hist)
            
            for pattern in patterns:
                if pattern.get('confidence', 0) > 0.7:
                    pattern_type = pattern.get('type', 'Unknown')
                    prediction = pattern.get('prediction', 'neutral')
                    
                    if prediction == 'bullish':
                        target = current_price * 1.05  # 5% above
                        suggestions.append({
                            'symbol': symbol,
                            'type': 'pattern',
                            'priority': 3,
                            'message': f"{symbol} showing {pattern_type} pattern - Bullish signal detected",
                            'trigger_price': round(target, 2),
                            'direction': 'above',
                            'reason': f"AI detected {pattern_type} with {pattern.get('confidence', 0)*100:.0f}% confidence",
                            'icon': '📈'
                        })
                    elif prediction == 'bearish':
                        target = current_price * 0.95  # 5% below
                        suggestions.append({
                            'symbol': symbol,
                            'type': 'pattern',
                            'priority': 3,
                            'message': f"{symbol} showing {pattern_type} pattern - Bearish signal detected",
                            'trigger_price': round(target, 2),
                            'direction': 'below',
                            'reason': f"AI detected {pattern_type} with {pattern.get('confidence', 0)*100:.0f}% confidence",
                            'icon': '📉'
                        })
        
        except Exception as e:
            logger.error(f"Pattern check error for {symbol}: {e}")
        
        return suggestions
    
    def _check_price_levels(self, symbol: str) -> List[Dict]:
        """Check for approaching support/resistance levels"""
        suggestions = []
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='6mo')
            
            if len(hist) < 20:
                return suggestions
            
            current_price = hist['Close'].iloc[-1]
            high_52w = hist['High'].max()
            low_52w = hist['Low'].min()
            
            # Check if approaching 52-week high
            distance_to_high = (high_52w - current_price) / current_price
            if 0.01 < distance_to_high < 0.05:  # 1-5% away
                suggestions.append({
                    'symbol': symbol,
                    'type': 'resistance',
                    'priority': 2,
                    'message': f"{symbol} approaching 52-week high (${high_52w:.2f})",
                    'trigger_price': round(high_52w * 1.01, 2),  # 1% above high
                    'direction': 'above',
                    'reason': f"Only {distance_to_high*100:.1f}% from 52-week high - potential breakout",
                    'icon': '🎯'
                })
            
            # Check if approaching 52-week low
            distance_to_low = (current_price - low_52w) / current_price
            if 0.01 < distance_to_low < 0.05:  # 1-5% away
                suggestions.append({
                    'symbol': symbol,
                    'type': 'support',
                    'priority': 2,
                    'message': f"{symbol} approaching 52-week low (${low_52w:.2f})",
                    'trigger_price': round(low_52w * 0.99, 2),  # 1% below low
                    'direction': 'below',
                    'reason': f"Only {distance_to_low*100:.1f}% from 52-week low - potential bounce",
                    'icon': '🎯'
                })
            
            # Check moving average crossovers
            if len(hist) >= 50:
                ma20 = hist['Close'].rolling(20).mean().iloc[-1]
                ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                
                # Near 50-day MA
                distance_to_ma50 = abs(current_price - ma50) / current_price
                if distance_to_ma50 < 0.02:  # Within 2%
                    suggestions.append({
                        'symbol': symbol,
                        'type': 'moving_average',
                        'priority': 2,
                        'message': f"{symbol} testing 50-day MA at ${ma50:.2f}",
                        'trigger_price': round(ma50, 2),
                        'direction': 'cross',
                        'reason': "Price near critical 50-day moving average",
                        'icon': '📊'
                    })
        
        except Exception as e:
            logger.error(f"Price level check error for {symbol}: {e}")
        
        return suggestions
    
    def _check_volatility(self, symbol: str) -> List[Dict]:
        """Check for unusual volatility spikes"""
        suggestions = []
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1mo')
            
            if len(hist) < 10:
                return suggestions
            
            # Calculate volume spike
            avg_volume = hist['Volume'][:-1].mean()
            current_volume = hist['Volume'].iloc[-1]
            
            if current_volume > avg_volume * 2:  # 2x normal volume
                current_price = hist['Close'].iloc[-1]
                suggestions.append({
                    'symbol': symbol,
                    'type': 'volume',
                    'priority': 3,
                    'message': f"{symbol} volume spike: {current_volume/avg_volume:.1f}x normal",
                    'trigger_price': round(current_price * 1.03, 2),
                    'direction': 'above',
                    'reason': f"Unusual volume ({current_volume:,.0f} vs avg {avg_volume:,.0f}) - potential breakout",
                    'icon': '⚡'
                })
            
            # Calculate price volatility
            returns = hist['Close'].pct_change()
            volatility = returns.std() * (252 ** 0.5)  # Annualized
            
            if volatility > 0.4:  # High volatility
                current_price = hist['Close'].iloc[-1]
                suggestions.append({
                    'symbol': symbol,
                    'type': 'volatility',
                    'priority': 2,
                    'message': f"{symbol} high volatility: {volatility*100:.1f}% annualized",
                    'trigger_price': round(current_price * 0.95, 2),
                    'direction': 'below',
                    'reason': "Elevated volatility - consider protective stops",
                    'icon': '⚠️'
                })
        
        except Exception as e:
            logger.error(f"Volatility check error for {symbol}: {e}")
        
        return suggestions
    
    def _check_sentiment(self, symbol: str) -> List[Dict]:
        """Check for sentiment shifts"""
        suggestions = []
        
        if not self.sentiment_analyzer:
            return suggestions
        
        try:
            # This would integrate with your sentiment_analyzer
            # For now, placeholder logic
            pass
        
        except Exception as e:
            logger.error(f"Sentiment check error for {symbol}: {e}")
        
        return suggestions
    
    def _check_portfolio_alerts(self, holdings: List) -> List[Dict]:
        """Generate portfolio-specific alerts"""
        suggestions = []
        
        try:
            for holding in holdings:
                symbol = holding.get('symbol')
                current_price = holding.get('current_price', 0)
                avg_cost = holding.get('avg_cost', 0)
                pnl_pct = holding.get('pnl_pct', 0)
                
                # Profit-taking suggestion
                if pnl_pct > 20:  # 20% gain
                    suggestions.append({
                        'symbol': symbol,
                        'type': 'profit_taking',
                        'priority': 2,
                        'message': f"{symbol} up {pnl_pct:.1f}% - Consider taking profits",
                        'trigger_price': round(current_price * 1.05, 2),
                        'direction': 'above',
                        'reason': f"Position up {pnl_pct:.1f}% - lock in gains at next resistance",
                        'icon': '💰'
                    })
                
                # Stop-loss suggestion
                elif pnl_pct < -10:  # 10% loss
                    suggestions.append({
                        'symbol': symbol,
                        'type': 'stop_loss',
                        'priority': 3,
                        'message': f"{symbol} down {abs(pnl_pct):.1f}% - Consider stop-loss",
                        'trigger_price': round(current_price * 0.95, 2),
                        'direction': 'below',
                        'reason': f"Position down {abs(pnl_pct):.1f}% - protect capital with stop",
                        'icon': '🛑'
                    })
        
        except Exception as e:
            logger.error(f"Portfolio alert check error: {e}")
        
        return suggestions
    
    def save_suggestions(self, suggestions: List[Dict], existing_alerts: List = None) -> int:
        """Save suggestions to database with improved deduplication and active alert filtering"""
        saved_count = 0
        
        for sugg in suggestions:
            try:
                # Check if similar suggestion already exists and is pending
                # Look for suggestions with same symbol, type, and similar trigger price
                existing = AlertSuggestion.query.filter_by(
                    symbol=sugg['symbol'],
                    type=sugg['type'],
                    status='pending'
                ).all()
                
                # Check if any existing suggestion has a similar trigger price
                # (within 2% of the new suggestion)
                is_duplicate = False
                new_trigger = sugg.get('trigger_price')
                
                if new_trigger and existing:
                    for ex in existing:
                        if ex.trigger_price:
                            price_diff = abs(float(ex.trigger_price) - new_trigger) / new_trigger
                            if price_diff < 0.02:  # Within 2%
                                is_duplicate = True
                                # Update the existing suggestion with latest data
                                ex.message = sugg['message']
                                ex.reason = sugg.get('reason', ex.reason)
                                ex.priority = max(ex.priority, sugg['priority'])  # Keep highest priority
                                ex.created_at = datetime.utcnow()  # Refresh timestamp
                                break
                elif existing and not new_trigger:
                    # For suggestions without trigger price, avoid duplicates entirely
                    is_duplicate = True
                
                # Check against existing active alerts
                if not is_duplicate and existing_alerts:
                    for alert in existing_alerts:
                        # Skip if not matching symbol
                        if alert.get('symbol') != sugg['symbol']:
                            continue
                        
                        # Check if alert has similar trigger price
                        alert_price = alert.get('target_price') or alert.get('targetPrice')
                        if new_trigger and alert_price:
                            price_diff = abs(float(alert_price) - new_trigger) / new_trigger
                            if price_diff < 0.05:  # Within 5% of existing alert
                                is_duplicate = True
                                logger.debug(f"Skipping suggestion for {sugg['symbol']} - matches existing alert")
                                break
                
                if not is_duplicate:
                    new_suggestion = AlertSuggestion(
                        symbol=sugg['symbol'],
                        type=sugg['type'],
                        message=sugg['message'],
                        trigger_price=sugg.get('trigger_price'),
                        direction=sugg.get('direction', 'above'),
                        priority=sugg['priority'],
                        reason=sugg.get('reason', ''),
                        icon=sugg.get('icon', '🔔')
                    )
                    db.session.add(new_suggestion)
                    saved_count += 1
            
            except Exception as e:
                logger.error(f"Error saving suggestion: {e}")
        
        try:
            db.session.commit()
            logger.info(f"✓ Saved {saved_count} new alert suggestions (updated duplicates)")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error committing suggestions: {e}")
        
        return saved_count
    
    def get_pending_suggestions(self, limit: int = 20) -> List[AlertSuggestion]:
        """Get pending suggestions from database"""
        try:
            # Clean up duplicates before fetching
            self.cleanup_duplicates()
            
            return AlertSuggestion.query.filter_by(status='pending')\
                .order_by(AlertSuggestion.priority.desc(), AlertSuggestion.created_at.desc())\
                .limit(limit).all()
        except Exception as e:
            logger.error(f"Error fetching suggestions: {e}")
            return []
    
    def accept_suggestion(self, suggestion_id: int) -> Optional[Dict]:
        """Accept a suggestion and return alert data"""
        try:
            suggestion = AlertSuggestion.query.get(suggestion_id)
            if not suggestion:
                return None
            
            suggestion.status = 'accepted'
            suggestion.actioned_at = datetime.utcnow()
            db.session.commit()
            
            # Return alert data for creation
            return {
                'symbol': suggestion.symbol,
                'type': 'high' if suggestion.direction == 'above' else 'low',
                'price': suggestion.trigger_price,
                'notes': suggestion.reason
            }
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error accepting suggestion: {e}")
            return None
    
    def dismiss_suggestion(self, suggestion_id: int) -> bool:
        """Dismiss a suggestion"""
        try:
            suggestion = AlertSuggestion.query.get(suggestion_id)
            if not suggestion:
                return False
            
            suggestion.status = 'dismissed'
            suggestion.actioned_at = datetime.utcnow()
            db.session.commit()
            return True
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error dismissing suggestion: {e}")
            return False
    
    def cleanup_duplicates(self) -> int:
        """Remove duplicate pending suggestions, keeping only the most recent for each symbol+type+price combo"""
        try:
            pending = AlertSuggestion.query.filter_by(status='pending').all()
            
            # Group by symbol and type
            grouped = {}
            for sugg in pending:
                key = (sugg.symbol, sugg.type)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(sugg)
            
            removed_count = 0
            for key, suggestions in grouped.items():
                if len(suggestions) <= 1:
                    continue
                
                # Sort by created_at descending (newest first)
                suggestions.sort(key=lambda x: x.created_at, reverse=True)
                
                # Group by similar trigger prices
                keep = []
                remove = []
                
                for sugg in suggestions:
                    should_remove = False
                    for kept in keep:
                        if sugg.trigger_price and kept.trigger_price:
                            price_diff = abs(float(sugg.trigger_price) - float(kept.trigger_price)) / float(kept.trigger_price)
                            if price_diff < 0.02:  # Within 2%
                                should_remove = True
                                break
                        elif not sugg.trigger_price and not kept.trigger_price:
                            # Both have no trigger price - duplicate
                            should_remove = True
                            break
                    
                    if should_remove:
                        remove.append(sugg)
                    else:
                        keep.append(sugg)
                
                # Remove duplicates
                for sugg in remove:
                    db.session.delete(sugg)
                    removed_count += 1
            
            db.session.commit()
            if removed_count > 0:
                logger.info(f"✓ Cleaned up {removed_count} duplicate suggestions")
            return removed_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cleaning up duplicates: {e}")
            return 0
    
    def cleanup_matching_alerts(self, existing_alerts: List) -> int:
        """Remove suggestions that match existing active alerts"""
        try:
            pending = AlertSuggestion.query.filter_by(status='pending').all()
            
            removed_count = 0
            for sugg in pending:
                should_remove = False
                
                for alert in existing_alerts:
                    if alert.get('symbol') != sugg.symbol:
                        continue
                    
                    # Check if alert has similar trigger price
                    alert_price = alert.get('target_price') or alert.get('targetPrice')
                    if sugg.trigger_price and alert_price:
                        price_diff = abs(float(alert_price) - float(sugg.trigger_price)) / float(sugg.trigger_price)
                        if price_diff < 0.05:  # Within 5%
                            should_remove = True
                            break
                
                if should_remove:
                    db.session.delete(sugg)
                    removed_count += 1
            
            db.session.commit()
            if removed_count > 0:
                logger.info(f"✓ Removed {removed_count} suggestions matching existing alerts")
            return removed_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cleaning up matching alerts: {e}")
            return 0
