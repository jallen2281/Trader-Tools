"""
Real-time Monitoring Service
Phase 2: Continuous market monitoring and alert triggering
"""

import threading
import time
from datetime import datetime
from data_fetcher import FinancialDataFetcher

class MonitoringService:
    """Background service for real-time market monitoring"""
    
    def __init__(self, app=None, check_interval=60):
        """
        Initialize monitoring service
        
        Args:
            app: Flask application instance
            check_interval: Seconds between checks (default 60)
        """
        self.app = app
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.data_fetcher = FinancialDataFetcher()
        
    def start(self):
        """Start the monitoring service"""
        if self.running:
            print("⚠️ Monitoring service already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f"✅ Monitoring service started (checking every {self.check_interval}s)")
    
    def stop(self):
        """Stop the monitoring service"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("🛑 Monitoring service stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        from models import db, Alert, MonitoringLog
        
        while self.running:
            try:
                with self.app.app_context():
                    # Get all active alerts
                    alerts = Alert.query.filter_by(enabled=True, triggered=False).all()
                    
                    if alerts:
                        print(f"🔍 Checking {len(alerts)} active alerts...")
                    
                    # Group alerts by symbol for efficient fetching
                    symbols = {}
                    for alert in alerts:
                        if alert.symbol not in symbols:
                            symbols[alert.symbol] = []
                        symbols[alert.symbol].append(alert)
                    
                    # Check each symbol
                    for symbol, symbol_alerts in symbols.items():
                        try:
                            # Fetch current price
                            stock_data = self.data_fetcher.fetch_stock_data(symbol, '1d')
                            
                            if stock_data is not None and not stock_data.empty:
                                current_price = float(stock_data.iloc[-1]['Close'])
                                
                                # Check each alert for this symbol
                                for alert in symbol_alerts:
                                    triggered = False
                                    
                                    if alert.alert_type == 'above' and current_price >= float(alert.target_price):
                                        triggered = True
                                    elif alert.alert_type == 'below' and current_price <= float(alert.target_price):
                                        triggered = True
                                    
                                    if triggered:
                                        # Trigger alert
                                        alert.triggered = True
                                        alert.triggered_at = datetime.utcnow()
                                        alert.current_price = current_price
                                        
                                        print(f"🚨 Alert triggered: {symbol} {alert.alert_type} ${alert.target_price} (current: ${current_price})")
                                        
                                        # Log to monitoring table
                                        log = MonitoringLog(
                                            symbol=symbol,
                                            check_type='alert_triggered',
                                            result={
                                                'alert_id': alert.id,
                                                'alert_type': alert.alert_type,
                                                'target_price': float(alert.target_price),
                                                'triggered_price': current_price,
                                                'user_id': alert.user_id
                                            }
                                        )
                                        db.session.add(log)
                                
                                db.session.commit()
                        
                        except Exception as e:
                            print(f"⚠️ Error checking {symbol}: {e}")
                            continue
            
            except Exception as e:
                print(f"⚠️ Error in monitoring loop: {e}")
            
            # Wait before next check
            time.sleep(self.check_interval)
    
    def check_symbol(self, symbol):
        """
        Manually check a specific symbol
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            dict: Current price and status
        """
        try:
            stock_data = self.data_fetcher.fetch_stock_data(symbol, '1d')
            
            if stock_data is not None and not stock_data.empty:
                latest = stock_data.iloc[-1]
                return {
                    'symbol': symbol,
                    'price': float(latest['Close']),
                    'volume': int(latest['Volume']),
                    'timestamp': datetime.utcnow().isoformat(),
                    'status': 'ok'
                }
            else:
                return {
                    'symbol': symbol,
                    'status': 'error',
                    'message': 'No data available'
                }
        
        except Exception as e:
            return {
                'symbol': symbol,
                'status': 'error',
                'message': str(e)
            }
    
    def get_monitoring_stats(self):
        """Get monitoring service statistics"""
        from models import MonitoringLog, Alert
        
        try:
            with self.app.app_context():
                total_alerts = Alert.query.filter_by(enabled=True).count()
                triggered_today = Alert.query.filter(
                    Alert.triggered == True,
                    Alert.triggered_at >= datetime.utcnow().date()
                ).count()
                
                recent_checks = MonitoringLog.query.order_by(
                    MonitoringLog.created_at.desc()
                ).limit(10).all()
                
                return {
                    'running': self.running,
                    'check_interval': self.check_interval,
                    'total_active_alerts': total_alerts,
                    'triggered_today': triggered_today,
                    'recent_checks': [
                        {
                            'symbol': log.symbol,
                            'type': log.check_type,
                            'timestamp': log.created_at.isoformat()
                        }
                        for log in recent_checks
                    ]
                }
        
        except Exception as e:
            return {
                'running': self.running,
                'error': str(e)
            }


# Global monitoring service instance
monitoring_service = None

def init_monitoring_service(app, check_interval=60):
    """Initialize and start monitoring service"""
    global monitoring_service
    
    if monitoring_service is None:
        monitoring_service = MonitoringService(app, check_interval)
        monitoring_service.start()
    
    return monitoring_service

def get_monitoring_service():
    """Get the global monitoring service instance"""
    return monitoring_service
