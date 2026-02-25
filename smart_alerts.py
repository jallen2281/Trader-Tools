"""
Smart Alerts Engine - Phase 4
Intelligent real-time alert system for portfolio monitoring
"""

import yfinance as yf
from datetime import datetime
import logging
import traceback
from models import db, Alert, Portfolio, OptionsPosition
import json

logger = logging.getLogger(__name__)

class SmartAlertsEngine:
    """
    Monitor portfolio positions and trigger smart alerts
    """
    
    def __init__(self):
        self.alert_types = [
            'price',
            'technical',
            'sentiment',
            'risk',
            'greeks',
            'pnl'
        ]
    
    def check_all_alerts(self, user_id):
        """
        Check all active alerts for user
        
        Args:
            user_id: User ID
            
        Returns:
            list: Newly triggered alerts
        """
        try:
            # Get all active alerts
            active_alerts = Alert.query.filter_by(
                user_id=user_id,
                status='active',
                enabled=True
            ).all()
            
            triggered_alerts = []
            
            for alert in active_alerts:
                triggered = self._check_alert(alert)
                
                if triggered:
                    alert.status = 'triggered'
                    alert.triggered = True
                    alert.triggered_at = datetime.now()
                    alert.message = triggered['message']
                    
                    triggered_alerts.append({
                        'id': alert.id,
                        'symbol': alert.symbol,
                        'alert_type': alert.alert_type,
                        'message': triggered['message'],
                        'priority': alert.priority,
                        'timestamp': datetime.now().isoformat()
                    })
            
            if triggered_alerts:
                db.session.commit()
                logger.info(f"Triggered {len(triggered_alerts)} alerts for user {user_id}")
            
            return triggered_alerts
            
        except Exception as e:
            logger.error(f"Error checking alerts: {str(e)}")
            db.session.rollback()
            return []
    
    def create_alert(self, user_id, symbol, alert_type, condition, priority='medium', 
                    portfolio_id=None, options_position_id=None):
        """
        Create a new smart alert
        
        Args:
            user_id: User ID
            symbol: Stock symbol
            alert_type: Type of alert ('price', 'technical', 'sentiment', 'risk', 'greeks', 'pnl')
            condition: Alert condition (dict or string)
            priority: Alert priority ('low', 'medium', 'high', 'critical')
            portfolio_id: Optional portfolio holding reference
            options_position_id: Optional options position reference
            
        Returns:
            Alert: Created alert object
        """
        try:
            # Parse condition
            if isinstance(condition, dict):
                condition_params = condition
                condition_str = self._dict_to_condition_string(condition)
            else:
                condition_str = condition
                condition_params = self._parse_condition_string(condition)
            
            logger.debug(f"Creating alert: type={alert_type}, symbol={symbol}, condition_str='{condition_str}', condition_params={condition_params}")
            
            # Ensure condition_params is JSON serializable
            if condition_params:
                import json
                try:
                    json.dumps(condition_params)  # Test serialization
                except (TypeError, ValueError) as e:
                    logger.error(f"condition_params not JSON serializable: {e}")
                    condition_params = {}
            
            # Extract target_price for legacy compatibility
            target_price = None
            if condition_params and 'value' in condition_params:
                target_price = condition_params['value']
            
            alert = Alert(
                user_id=user_id,
                symbol=symbol,
                alert_type=alert_type,
                condition=condition_str,
                condition_params=condition_params,
                target_price=target_price,  # Legacy field required by database
                priority=priority,
                portfolio_id=portfolio_id,
                options_position_id=options_position_id,
                status='active',
                enabled=True
            )
            
            db.session.add(alert)
            db.session.commit()
            
            logger.info(f"Created {alert_type} alert for {symbol}: {condition_str}")
            
            return alert
            
        except Exception as e:
            logger.error(f"Error creating alert: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            db.session.rollback()
            return None
    
    def create_price_alert(self, user_id, symbol, target_price, direction='above', pivot_price=None):
        """
        Create price alert (legacy compatibility + enhanced)
        
        Args:
            user_id: User ID
            symbol: Stock symbol
            target_price: Price threshold
            direction: 'above' or 'below'
            pivot_price: Optional current price for context
        """
        condition = {
            'metric': 'price',
            'operator': '>' if direction == 'above' else '<',
            'value': target_price
        }
        
        return self.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type='price',
            condition=condition,
            priority='medium'
        )
    
    def create_technical_alert(self, user_id, symbol, indicator, operator, value, priority='medium'):
        """
        Create technical indicator alert
        
        Examples:
            RSI < 30 (oversold)
            MACD crosses above signal
            Volume > 2x average
        """
        condition = {
            'indicator': indicator,
            'operator': operator,
            'value': value
        }
        
        return self.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type='technical',
            condition=condition,
            priority=priority
        )
    
    def create_pnl_alert(self, user_id, symbol, threshold_pct, direction='above', portfolio_id=None):
        """
        Create P&L milestone alert
        
        Examples:
            Alert when position gains +20%
            Alert when position loses -10%
        """
        condition = {
            'metric': 'pnl_pct',
            'operator': '>' if direction == 'above' else '<',
            'value': threshold_pct
        }
        
        priority = 'high' if abs(threshold_pct) > 20 else 'medium'
        
        return self.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type='pnl',
            condition=condition,
            priority=priority,
            portfolio_id=portfolio_id
        )
    
    def create_sentiment_alert(self, user_id, symbol, sentiment_trigger, priority='medium'):
        """
        Create sentiment change alert
        
        Examples:
            Alert when sentiment turns 'Very Bearish'
            Alert when fear/greed index > 75
        """
        condition = {
            'metric': 'sentiment',
            'value': sentiment_trigger
        }
        
        return self.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type='sentiment',
            condition=condition,
            priority=priority
        )
    
    def create_risk_alert(self, user_id, symbol, risk_trigger, priority='high'):
        """
        Create risk level alert
        
        Examples:
            Alert when risk grade drops to D or F
            Alert when VaR increases significantly
        """
        condition = {
            'metric': 'risk_grade',
            'value': risk_trigger
        }
        
        return self.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type='risk',
            condition=condition,
            priority=priority
        )
    
    def get_triggered_alerts(self, user_id, limit=20):
        """
        Get recently triggered alerts
        
        Args:
            user_id: User ID
            limit: Maximum number of alerts to return
            
        Returns:
            list: Recent triggered alerts
        """
        try:
            alerts = Alert.query.filter_by(
                user_id=user_id,
                status='triggered'
            ).order_by(Alert.triggered_at.desc()).limit(limit).all()
            
            return [alert.to_dict() for alert in alerts]
            
        except Exception as e:
            logger.error(f"Error fetching triggered alerts: {str(e)}")
            return []
    
    def dismiss_alert(self, alert_id):
        """Mark alert as dismissed"""
        try:
            alert = Alert.query.get(alert_id)
            
            if alert:
                alert.status = 'dismissed'
                db.session.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error dismissing alert: {str(e)}")
            db.session.rollback()
            return False
    
    def delete_alert(self, alert_id):
        """Delete alert"""
        try:
            alert = Alert.query.get(alert_id)
            
            if alert:
                db.session.delete(alert)
                db.session.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting alert: {str(e)}")
            db.session.rollback()
            return False
    
    def _check_alert(self, alert):
        """
        Check if alert condition is met
        
        Args:
            alert: Alert object
            
        Returns:
            dict or None: Alert trigger info if triggered
        """
        try:
            alert_type = alert.alert_type
            
            if alert_type == 'price':
                return self._check_price_alert(alert)
            elif alert_type == 'technical':
                return self._check_technical_alert(alert)
            elif alert_type == 'sentiment':
                return self._check_sentiment_alert(alert)
            elif alert_type == 'risk':
                return self._check_risk_alert(alert)
            elif alert_type == 'greeks':
                return self._check_greeks_alert(alert)
            elif alert_type == 'pnl':
                return self._check_pnl_alert(alert)
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking alert {alert.id}: {str(e)}")
            return None
    
    def _check_price_alert(self, alert):
        """Check price alert condition"""
        try:
            # Get current price
            ticker = yf.Ticker(alert.symbol)
            data = ticker.history(period='1d')
            
            if data.empty:
                return None
            
            current_price = data['Close'].iloc[-1]
            
            # Update alert's current price
            alert.current_price = current_price
            
            # Check condition
            params = alert.condition_params or {}
            operator = params.get('operator', '>')
            target = params.get('value', alert.target_price)
            
            if target is None:
                return None
            
            target = float(target)
            
            triggered = False
            if operator == '>' and current_price > target:
                triggered = True
                message = f"{alert.symbol} price ${current_price:.2f} is above target ${target:.2f}"
            elif operator == '<' and current_price < target:
                triggered = True
                message = f"{alert.symbol} price ${current_price:.2f} is below target ${target:.2f}"
            
            if triggered:
                return {'message': message, 'current_value': current_price}
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking price alert: {str(e)}")
            return None
    
    def _check_technical_alert(self, alert):
        """Check technical indicator alert"""
        try:
            params = alert.condition_params or {}
            indicator = params.get('indicator', '').upper()
            operator = params.get('operator', '>')
            threshold = params.get('value')
            
            if not indicator or threshold is None:
                return None
            
            threshold = float(threshold)
            
            # Fetch data
            ticker = yf.Ticker(alert.symbol)
            data = ticker.history(period='3mo')
            
            if data.empty or len(data) < 20:
                return None
            
            # Calculate indicator
            if indicator == 'RSI':
                current_value = self._calculate_rsi(data['Close'])
            elif indicator == 'MACD':
                macd, signal = self._calculate_macd(data['Close'])
                current_value = macd - signal  # MACD histogram
            elif indicator == 'VOLUME':
                avg_volume = data['Volume'].tail(20).mean()
                current_value = data['Volume'].iloc[-1] / avg_volume
            else:
                return None
            
            # Check condition
            triggered = False
            if operator == '>' and current_value > threshold:
                triggered = True
            elif operator == '<' and current_value < threshold:
                triggered = True
            elif operator == '==' and abs(current_value - threshold) < 0.01:
                triggered = True
            
            if triggered:
                message = f"{alert.symbol} {indicator} is {current_value:.2f} ({operator} {threshold:.2f})"
                return {'message': message, 'current_value': current_value}
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking technical alert: {str(e)}")
            return None
    
    def _check_sentiment_alert(self, alert):
        """Check sentiment alert"""
        try:
            from sentiment_analyzer import SentimentAnalyzer
            
            params = alert.condition_params or {}
            target_sentiment = params.get('value')
            
            if not target_sentiment:
                return None
            
            # Get sentiment analysis
            ticker = yf.Ticker(alert.symbol)
            data = ticker.history(period='6mo')
            
            if data.empty:
                return None
            
            sa = SentimentAnalyzer()
            sentiment_data = sa.analyze_sentiment(data, alert.symbol)
            
            current_sentiment = sentiment_data.get('sentiment')
            
            # Check if sentiment matches
            if current_sentiment == target_sentiment:
                message = f"{alert.symbol} sentiment changed to {current_sentiment}"
                return {'message': message, 'current_value': current_sentiment}
            
            return None
            
        except ImportError:
            logger.warning("Sentiment analyzer not available")
            return None
        except Exception as e:
            logger.error(f"Error checking sentiment alert: {str(e)}")
            return None
    
    def _check_risk_alert(self, alert):
        """Check risk alert"""
        try:
            from risk_analyzer import RiskAnalyzer
            
            params = alert.condition_params or {}
            risk_trigger = params.get('value', 'D')
            
            # Get risk analysis
            ticker = yf.Ticker(alert.symbol)
            data = ticker.history(period='6mo')
            
            if data.empty:
                return None
            
            ra = RiskAnalyzer()
            risk_data = ra.comprehensive_risk_analysis(data, alert.symbol)
            
            current_risk = risk_data.get('risk_grade')
            
            # Check if risk grade matches or worsened
            risk_grades = ['A', 'B', 'C', 'D', 'F']
            trigger_index = risk_grades.index(risk_trigger)
            current_index = risk_grades.index(current_risk)
            
            if current_index >= trigger_index:
                message = f"{alert.symbol} risk grade is {current_risk} (threshold: {risk_trigger})"
                return {'message': message, 'current_value': current_risk}
            
            return None
            
        except ImportError:
            logger.warning("Risk analyzer not available")
            return None
        except Exception as e:
            logger.error(f"Error checking risk alert: {str(e)}")
            return None
    
    def _check_greeks_alert(self, alert):
        """Check option Greeks alert"""
        # Placeholder for options Greeks alerts
        # Would integrate with options_analyzer if position is an option
        return None
    
    def _check_pnl_alert(self, alert):
        """Check P&L alert"""
        try:
            if not alert.portfolio_id:
                return None
            
            holding = Portfolio.query.get(alert.portfolio_id)
            
            if not holding:
                return None
            
            # Get current price
            ticker = yf.Ticker(holding.symbol)
            data = ticker.history(period='1d')
            
            if data.empty:
                return None
            
            current_price = data['Close'].iloc[-1]
            
            # Calculate P&L
            cost_basis = float(holding.average_cost)
            pnl_pct = ((current_price - cost_basis) / cost_basis * 100) if cost_basis > 0 else 0
            
            # Check condition
            params = alert.condition_params or {}
            operator = params.get('operator', '>')
            threshold = float(params.get('value', 0))
            
            triggered = False
            if operator == '>' and pnl_pct > threshold:
                triggered = True
                message = f"{alert.symbol} gain is {pnl_pct:+.1f}% (target: >{threshold:.1f}%)"
            elif operator == '<' and pnl_pct < threshold:
                triggered = True
                message = f"{alert.symbol} loss is {pnl_pct:+.1f}% (stop loss: <{threshold:.1f}%)"
            
            if triggered:
                return {'message': message, 'current_value': pnl_pct}
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking P&L alert: {str(e)}")
            return None
    
    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1]
        except:
            return 50
    
    def _calculate_macd(self, prices):
        """Calculate MACD"""
        try:
            exp1 = prices.ewm(span=12, adjust=False).mean()
            exp2 = prices.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            return macd.iloc[-1], signal.iloc[-1]
        except:
            return 0, 0
    
    def _dict_to_condition_string(self, condition_dict):
        """Convert condition dict to readable string"""
        try:
            if 'indicator' in condition_dict:
                return f"{condition_dict['indicator']} {condition_dict['operator']} {condition_dict['value']}"
            elif 'metric' in condition_dict:
                return f"{condition_dict['metric']} {condition_dict['operator']} {condition_dict['value']}"
            else:
                return json.dumps(condition_dict)
        except:
            return str(condition_dict)
    
    def _parse_condition_string(self, condition_str):
        """Parse condition string to dict (basic parser)"""
        try:
            parts = condition_str.split()
            if len(parts) >= 3:
                return {
                    'metric': parts[0],
                    'operator': parts[1],
                    'value': float(parts[2]) if parts[2].replace('.', '').isdigit() else parts[2]
                }
            return {}
        except:
            return {}


# Standalone testing
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Smart Alerts Engine - Ready for integration")
