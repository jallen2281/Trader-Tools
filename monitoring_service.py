"""
Real-time Monitoring Service
Phase 2: Continuous market monitoring and alert triggering
"""

import threading
import time
from datetime import datetime
from data_fetcher import FinancialDataFetcher

# Per-user cap on alert notifications created in a single day, so a burst of
# triggers (or a bad-data spike) can never flood the notification feed.
MAX_ALERT_NOTIFS_PER_DAY = 25

# Fallback interval (seconds) if a user has no preference stored.
DEFAULT_ALERT_INTERVAL = 900

class MonitoringService:
    """Background service for real-time market monitoring"""
    
    def __init__(self, app=None, check_interval=60):
        """
        Initialize monitoring service

        Args:
            app: Flask application instance
            check_interval: Base tick in seconds. The loop wakes this often and
                evaluates only users whose per-user interval has elapsed, so this
                should be the finest granularity any tier can select (default 60s).
        """
        self.app = app
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.data_fetcher = FinancialDataFetcher()
        # user_id -> monotonic timestamp of last alert check (in-memory; on
        # restart everyone is treated as due, which is fine).
        self._last_checked = {}
        
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
        """Main monitoring loop.

        Evaluates every active alert through the SmartAlertsEngine (which knows
        how to check price / pnl / technical / sentiment / risk conditions) and
        records a durable Notification for each fresh trigger. The previous
        implementation compared alert_type against 'above'/'below', which never
        matched the stored types ('price', 'pnl', ...), so nothing ever fired.
        """
        from models import db, Alert, Notification, User
        from smart_alerts import SmartAlertsEngine

        engine = SmartAlertsEngine()

        while self.running:
            try:
                with self.app.app_context():
                    # Distinct users that currently have active, enabled alerts
                    user_ids = [
                        row[0] for row in db.session.query(Alert.user_id)
                        .filter_by(status='active', enabled=True)
                        .distinct().all()
                    ]

                    # Each user's preferred check interval (seconds)
                    intervals = {}
                    if user_ids:
                        for u in User.query.filter(User.id.in_(user_ids)).all():
                            intervals[u.id] = u.alert_check_interval or DEFAULT_ALERT_INTERVAL

                    now = time.monotonic()
                    total_fired = 0
                    for user_id in user_ids:
                        interval = intervals.get(user_id, DEFAULT_ALERT_INTERVAL)
                        last = self._last_checked.get(user_id)
                        if last is not None and (now - last) < interval:
                            continue  # not due yet for this user

                        try:
                            # Flips status->'triggered' and commits inside the engine
                            triggered = engine.check_all_alerts(user_id)
                            for t in triggered:
                                self._record_notification(db, Notification, user_id, t)
                                total_fired += 1
                            if triggered:
                                db.session.commit()
                            self._last_checked[user_id] = now
                        except Exception as e:
                            print(f"⚠️ Error checking alerts for user {user_id}: {e}")
                            db.session.rollback()
                            continue

                    if total_fired:
                        print(f"🚨 {total_fired} alert(s) fired this cycle")

            except Exception as e:
                print(f"⚠️ Error in monitoring loop: {e}")

            # Base tick — per-user intervals gate actual checks above
            time.sleep(self.check_interval)

    def _record_notification(self, db, Notification, user_id, trigger):
        """Create a Notification row for a freshly-triggered alert, respecting a
        per-user daily cap so a burst of triggers can't flood the feed.

        Autoflush ensures notifications added earlier in this same cycle are
        counted, so the cap holds even before the cycle commits.
        """
        today = datetime.utcnow().date()
        day_start = datetime(today.year, today.month, today.day)
        todays_count = Notification.query.filter(
            Notification.user_id == user_id,
            Notification.category == 'alert',
            Notification.created_at >= day_start
        ).count()

        if todays_count >= MAX_ALERT_NOTIFS_PER_DAY:
            return  # daily cap reached — skip to avoid flooding

        symbol = trigger.get('symbol', '')
        note = Notification(
            user_id=user_id,
            alert_id=trigger.get('id'),
            category='alert',
            symbol=symbol,
            title=f"{symbol} alert triggered",
            message=trigger.get('message'),
            priority=trigger.get('priority', 'medium'),
        )
        db.session.add(note)
    
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
