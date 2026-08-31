"""
Database Models for Financial Analysis System
Phase 2: SQLAlchemy ORM Models
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta
from sqlalchemy import JSON


def _add_one_month(d):
    """d + 1 calendar month, clamping the day to the target month's length."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    # days in target month
    nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
    last_day = (date(nm_y, nm_m, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User account model"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    picture_url = db.Column(db.Text)
    role = db.Column(db.String(20), default='user', index=True)  # user, moderator, admin
    is_active = db.Column(db.Boolean, default=True)
    bio = db.Column(db.Text)
    copy_trading_enabled = db.Column(db.Boolean, default=False)
    # How often (seconds) the monitor checks this user's alerts. Floor is gated
    # by tier/role at set-time; the monitor just honors whatever is stored.
    alert_check_interval = db.Column(db.Integer, default=900)
    # How often (seconds) the watchlist auto-refreshes prices. Also tier-gated.
    watchlist_refresh_interval = db.Column(db.Integer, default=60)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_active = db.Column(db.DateTime)
    preferences = db.Column(JSON, default={})
    # Soft-delete: when set, the account is deleted — login is blocked and PII is
    # scrubbed, but rows are retained (anonymized) until an admin hard-purges.
    deleted_at = db.Column(db.DateTime, index=True)
    deleted_by = db.Column(db.Integer)  # admin user id, or the user's own id for self-serve

    # Relationships
    # NOTE: lazy='select' (not selectin) is deliberate — verify_session_token loads a
    # User on every authed request and does NOT need groups; eager-loading them here
    # added an extra query to the hot auth path and measurably raised transient 401s.
    # Groups load lazily only when actually accessed (to_dict / permission checks).
    groups = db.relationship('Group', secondary='user_groups', back_populates='members', lazy='select')
    watchlist = db.relationship('Watchlist', backref='user', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    portfolio = db.relationship('Portfolio', backref='user', lazy=True, cascade='all, delete-orphan')
    portfolio_accounts = db.relationship('PortfolioAccount', backref='user', lazy=True, cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    options_positions = db.relationship('OptionsPosition', backref='user', lazy=True, cascade='all, delete-orphan')
    analysis_history = db.relationship('AnalysisHistory', backref='user', lazy=True, cascade='all, delete-orphan')
    sessions = db.relationship('UserSession', backref='user', lazy=True, cascade='all, delete-orphan')
    portfolio_snapshots = db.relationship('PortfolioSnapshot', backref='user', lazy=True, cascade='all, delete-orphan')  # Phase 4
    dividends = db.relationship('Dividend', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'picture_url': self.picture_url,
            'role': self.role or 'user',
            'is_active': self.is_active if self.is_active is not None else True,
            'bio': self.bio,
            'copy_trading_enabled': self.copy_trading_enabled or False,
            'alert_check_interval': self.alert_check_interval or 900,
            'watchlist_refresh_interval': self.watchlist_refresh_interval or 60,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'groups': [{'id': g.id, 'name': g.name} for g in (self.groups or [])],
        }

    def is_admin(self):
        return self.role == 'admin'

    def is_moderator(self):
        return self.role in ('admin', 'moderator')

    def is_deleted(self):
        return self.deleted_at is not None

    def group_permissions(self):
        """Union of permission keys granted by this user's groups (excludes admin bypass)."""
        perms = set()
        for g in (self.groups or []):
            perms.update(g.permissions or [])
        return perms

    def __repr__(self):
        return f'<User {self.email}>'

class Watchlist(db.Model):
    """User's watchlist stocks"""
    __tablename__ = 'watchlist'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'symbol', name='unique_user_symbol'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'notes': self.notes
        }

class Alert(db.Model):
    """Smart alerts for portfolio monitoring (Phase 4)"""
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    
    # Phase 4: Enhanced alert types
    alert_type = db.Column(db.String(50), nullable=False)  # 'price', 'technical', 'sentiment', 'risk', 'greeks', 'pnl'
    
    # Price alerts (legacy)
    target_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    current_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    
    # Phase 4: Smart alert conditions
    condition = db.Column(db.String(200))  # "rsi < 30", "sentiment == 'Very Bearish'", "pnl_pct > 20"
    condition_params = db.Column(JSON)  # Structured condition data
    
    # Alert status
    triggered = db.Column(db.Boolean, default=False)
    triggered_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')  # 'active', 'triggered', 'dismissed', 'expired'
    
    # Alert metadata
    priority = db.Column(db.String(20), default='medium')  # 'low', 'medium', 'high', 'critical'
    message = db.Column(db.Text)  # Alert message when triggered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    enabled = db.Column(db.Boolean, default=True)
    
    # Portfolio position reference (optional)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'))
    options_position_id = db.Column(db.Integer, db.ForeignKey('options_positions.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'alert_type': self.alert_type,
            'condition': self.condition,
            'condition_params': self.condition_params,
            'priority': self.priority,
            'status': self.status,
            'triggered': self.triggered,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'enabled': self.enabled,
            # Legacy fields
            'type': self.alert_type,
            'target_price': float(self.target_price) if self.target_price else None,
            'targetPrice': float(self.target_price) if self.target_price else None,
            'currentPrice': float(self.current_price) if self.current_price else None
        }

class PortfolioAccount(db.Model):
    """Portfolio account for grouping holdings (e.g., different brokerage accounts)"""
    __tablename__ = 'portfolio_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    investment_style = db.Column(db.String(30), default='moderate')  # 'aggressive', 'moderate', 'conservative', 'balanced'
    description = db.Column(db.Text)
    cash_balance = db.Column(db.Numeric(15, 2, asdecimal=False), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    holdings = db.relationship('Portfolio', backref='account', lazy=True)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='unique_user_account_name'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'investment_style': self.investment_style,
            'description': self.description,
            'cash_balance': float(self.cash_balance) if self.cash_balance else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'holdings_count': len(self.holdings) if self.holdings else 0
        }

class Portfolio(db.Model):
    """User's portfolio holdings"""
    __tablename__ = 'portfolio'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('portfolio_accounts.id'), nullable=True, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    asset_type = db.Column(db.String(20), nullable=False)  # 'stock', 'option', 'etf'
    quantity = db.Column(db.Numeric(15, 6, asdecimal=False), nullable=False)
    average_cost = db.Column(db.Numeric(10, 4, asdecimal=False), nullable=False)
    current_price = db.Column(db.Numeric(10, 4, asdecimal=False))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    # Position context (Phase 4b): so the recommendation engine doesn't mis-flag
    # a deliberate lottery bet or an IPO-restricted hold.
    intent = db.Column(db.String(20))       # 'core' | 'lottery' | 'signal' | None
    ipo_lock_until = db.Column(db.Date)     # if set and in the future, can't be sold yet
    # Per-position take-profit / stop-loss targets, as % of average cost. When
    # set, they override the engine's default TP/SL rules for this holding.
    take_profit_pct = db.Column(db.Numeric(6, 2, asdecimal=False))   # e.g. 50 -> +50% from cost
    stop_loss_pct = db.Column(db.Numeric(6, 2, asdecimal=False))     # e.g. 10 -> -10% from cost

    __table_args__ = (
        db.UniqueConstraint('user_id', 'symbol', 'asset_type', 'account_id', name='unique_user_position'),
    )
    
    def to_dict(self):
        quantity = float(self.quantity)
        avg_cost = float(self.average_cost)
        current = float(self.current_price) if self.current_price else avg_cost
        
        cost_basis = quantity * avg_cost
        market_value = quantity * current
        gain_loss = market_value - cost_basis
        gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis != 0 else 0
        
        return {
            'id': self.id,
            'symbol': self.symbol,
            'asset_type': self.asset_type,
            'quantity': quantity,
            'average_cost': avg_cost,
            'current_price': current,
            'cost_basis': round(cost_basis, 2),
            'market_value': round(market_value, 2),
            'gain_loss': round(gain_loss, 2),
            'gain_loss_pct': round(gain_loss_pct, 2),
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'intent': self.intent,
            'ipo_lock_until': self.ipo_lock_until.isoformat() if self.ipo_lock_until else None,
            'take_profit_pct': float(self.take_profit_pct) if self.take_profit_pct is not None else None,
            'stop_loss_pct': float(self.stop_loss_pct) if self.stop_loss_pct is not None else None
        }

class Transaction(db.Model):
    """Transaction history for cost basis tracking"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('portfolio_accounts.id'), nullable=True, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    asset_type = db.Column(db.String(20), nullable=False)  # 'stock', 'option', 'etf'
    transaction_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    quantity = db.Column(db.Numeric(15, 6, asdecimal=False), nullable=False)
    price = db.Column(db.Numeric(10, 4, asdecimal=False), nullable=False)
    commission = db.Column(db.Numeric(10, 2, asdecimal=False), default=0)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    notes = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'asset_type': self.asset_type,
            'transaction_type': self.transaction_type,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'commission': float(self.commission),
            'total': float(self.quantity * self.price + self.commission),
            'transaction_date': self.transaction_date.isoformat() if self.transaction_date else None,
            'account_id': self.account_id,
            'notes': self.notes
        }

class OptionsPosition(db.Model):
    """Options positions tracking"""
    __tablename__ = 'options_positions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    underlying_symbol = db.Column(db.String(10), nullable=False, index=True)
    option_type = db.Column(db.String(10), nullable=False)  # 'call' or 'put'
    strike_price = db.Column(db.Numeric(10, 2, asdecimal=False), nullable=False)
    expiration_date = db.Column(db.Date, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    premium_paid = db.Column(db.Numeric(10, 4, asdecimal=False), nullable=False)
    current_premium = db.Column(db.Numeric(10, 4, asdecimal=False))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='open')  # 'open', 'closed', 'exercised', 'expired'
    
    def to_dict(self):
        premium_paid = float(self.premium_paid)
        current = float(self.current_premium) if self.current_premium else premium_paid
        
        cost_basis = self.quantity * premium_paid * 100  # Options are per 100 shares
        market_value = self.quantity * current * 100
        gain_loss = market_value - cost_basis
        gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis != 0 else 0
        
        return {
            'id': self.id,
            'underlying_symbol': self.underlying_symbol,
            'option_type': self.option_type,
            'strike_price': float(self.strike_price),
            'expiration_date': self.expiration_date.isoformat() if self.expiration_date else None,
            'quantity': self.quantity,
            'premium_paid': premium_paid,
            'current_premium': current,
            'cost_basis': round(cost_basis, 2),
            'market_value': round(market_value, 2),
            'gain_loss': round(gain_loss, 2),
            'gain_loss_pct': round(gain_loss_pct, 2),
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'status': self.status
        }

class AnalysisHistory(db.Model):
    """AI analysis history"""
    __tablename__ = 'analysis_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    period = db.Column(db.String(10), nullable=False)
    chart_type = db.Column(db.String(20), nullable=False)
    analysis_text = db.Column(db.Text)
    chart_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'period': self.period,
            'chart_type': self.chart_type,
            'analysis_text': self.analysis_text,
            'chart_path': self.chart_path,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class MLPattern(db.Model):
    """ML detected patterns"""
    __tablename__ = 'ml_patterns'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    pattern_type = db.Column(db.String(50), nullable=False, index=True)
    confidence = db.Column(db.Numeric(5, 4, asdecimal=False), nullable=False)
    prediction = db.Column(db.String(20), nullable=False)  # 'bullish', 'bearish', 'neutral'
    time_horizon = db.Column(db.String(20))
    detected_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    pattern_data = db.Column(JSON)
    price_at_detection = db.Column(db.Numeric(10, 4, asdecimal=False))
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'pattern_type': self.pattern_type,
            'confidence': float(self.confidence),
            'prediction': self.prediction,
            'time_horizon': self.time_horizon,
            'detected_at': self.detected_at.isoformat() if self.detected_at else None,
            'pattern_data': self.pattern_data,
            'price_at_detection': float(self.price_at_detection) if self.price_at_detection else None
        }

class MLPrediction(db.Model):
    """ML predictions tracking"""
    __tablename__ = 'ml_predictions'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    prediction_type = db.Column(db.String(50), nullable=False)
    predicted_direction = db.Column(db.String(20), nullable=False)  # 'up', 'down', 'sideways'
    predicted_price = db.Column(db.Numeric(10, 4, asdecimal=False))
    confidence = db.Column(db.Numeric(5, 4, asdecimal=False), nullable=False)
    time_horizon = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    target_date = db.Column(db.DateTime, index=True)
    actual_price = db.Column(db.Numeric(10, 4, asdecimal=False))
    actual_direction = db.Column(db.String(20))
    accuracy_score = db.Column(db.Numeric(5, 4, asdecimal=False))
    model_version = db.Column(db.String(50))
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'prediction_type': self.prediction_type,
            'predicted_direction': self.predicted_direction,
            'predicted_price': float(self.predicted_price) if self.predicted_price else None,
            'confidence': float(self.confidence),
            'time_horizon': self.time_horizon,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'actual_price': float(self.actual_price) if self.actual_price else None,
            'actual_direction': self.actual_direction,
            'accuracy_score': float(self.accuracy_score) if self.accuracy_score else None,
            'model_version': self.model_version
        }

class MonitoringLog(db.Model):
    """System monitoring log"""
    __tablename__ = 'monitoring_log'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    check_type = db.Column(db.String(50), nullable=False)
    result = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'check_type': self.check_type,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class UserSession(db.Model):
    """User authentication sessions"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

class MarketCondition(db.Model):
    """Market conditions and volatility indices (Phase 4)"""
    __tablename__ = 'market_conditions'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Volatility Indices
    vix = db.Column(db.Numeric(10, 2, asdecimal=False))  # S&P 500 volatility (^VIX)
    vxn = db.Column(db.Numeric(10, 2, asdecimal=False))  # Nasdaq 100 volatility (^VXN)
    rvx = db.Column(db.Numeric(10, 2, asdecimal=False))  # Russell 2000 volatility (^RVX)
    vix_change = db.Column(db.Numeric(10, 2, asdecimal=False))  # Today's VIX change
    vix_percentile = db.Column(db.Numeric(5, 2, asdecimal=False))  # Historical percentile (0-100)
    
    # Market Sentiment
    market_sentiment = db.Column(db.String(20))  # 'fear', 'greed', 'neutral', 'extreme_fear', 'extreme_greed'
    fear_greed_index = db.Column(db.Integer)  # 0-100
    volatility_regime = db.Column(db.String(20))  # 'low', 'normal', 'elevated', 'high', 'extreme'
    
    # Major Indices
    spx_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    spx_change = db.Column(db.Numeric(10, 2, asdecimal=False))
    spx_change_pct = db.Column(db.Numeric(5, 2, asdecimal=False))
    ndx_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    ndx_change = db.Column(db.Numeric(10, 2, asdecimal=False))
    ndx_change_pct = db.Column(db.Numeric(5, 2, asdecimal=False))
    
    # VIX Term Structure
    vix_futures_contango = db.Column(db.Boolean)  # True if contango, False if backwardation
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'vix': float(self.vix) if self.vix else None,
            'vxn': float(self.vxn) if self.vxn else None,
            'rvx': float(self.rvx) if self.rvx else None,
            'vix_change': float(self.vix_change) if self.vix_change else None,
            'vix_percentile': float(self.vix_percentile) if self.vix_percentile else None,
            'market_sentiment': self.market_sentiment,
            'fear_greed_index': self.fear_greed_index,
            'volatility_regime': self.volatility_regime,
            'spx_price': float(self.spx_price) if self.spx_price else None,
            'spx_change': float(self.spx_change) if self.spx_change else None,
            'spx_change_pct': float(self.spx_change_pct) if self.spx_change_pct else None,
            'ndx_price': float(self.ndx_price) if self.ndx_price else None,
            'ndx_change': float(self.ndx_change) if self.ndx_change else None,
            'ndx_change_pct': float(self.ndx_change_pct) if self.ndx_change_pct else None,
            'vix_futures_contango': self.vix_futures_contango
        }

class PortfolioSnapshot(db.Model):
    """Historical portfolio value snapshots (Phase 4)"""
    __tablename__ = 'portfolio_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Portfolio values
    total_value = db.Column(db.Numeric(15, 2, asdecimal=False), nullable=False)
    total_cost_basis = db.Column(db.Numeric(15, 2, asdecimal=False), nullable=False)
    total_pnl = db.Column(db.Numeric(15, 2, asdecimal=False), nullable=False)
    total_pnl_pct = db.Column(db.Numeric(10, 4, asdecimal=False), nullable=False)
    
    # Daily changes
    daily_change = db.Column(db.Numeric(15, 2, asdecimal=False))
    daily_change_pct = db.Column(db.Numeric(10, 4, asdecimal=False))
    
    # Allocation breakdown
    stock_value = db.Column(db.Numeric(15, 2, asdecimal=False))
    options_value = db.Column(db.Numeric(15, 2, asdecimal=False))
    cash_value = db.Column(db.Numeric(15, 2, asdecimal=False))
    
    # Risk metrics
    portfolio_beta = db.Column(db.Numeric(10, 4, asdecimal=False))
    portfolio_var = db.Column(db.Numeric(15, 2, asdecimal=False))
    portfolio_sharpe = db.Column(db.Numeric(10, 4, asdecimal=False))
    
    # Market context
    spx_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    vix_level = db.Column(db.Numeric(10, 2, asdecimal=False))
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'total_value': float(self.total_value),
            'total_cost_basis': float(self.total_cost_basis),
            'total_pnl': float(self.total_pnl),
            'total_pnl_pct': float(self.total_pnl_pct),
            'daily_change': float(self.daily_change) if self.daily_change else None,
            'daily_change_pct': float(self.daily_change_pct) if self.daily_change_pct else None,
            'stock_value': float(self.stock_value) if self.stock_value else None,
            'options_value': float(self.options_value) if self.options_value else None,
            'cash_value': float(self.cash_value) if self.cash_value else None,
            'portfolio_beta': float(self.portfolio_beta) if self.portfolio_beta else None,
            'portfolio_var': float(self.portfolio_var) if self.portfolio_var else None,
            'portfolio_sharpe': float(self.portfolio_sharpe) if self.portfolio_sharpe else None,
            'spx_price': float(self.spx_price) if self.spx_price else None,
            'vix_level': float(self.vix_level) if self.vix_level else None
        }

class AlertSuggestion(db.Model):
    """AI-generated alert suggestions (Phase 5)"""
    __tablename__ = 'alert_suggestions'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False, index=True)  # 'pattern', 'resistance', 'volume', 'profit_taking', etc.
    message = db.Column(db.Text, nullable=False)
    trigger_price = db.Column(db.Numeric(10, 2, asdecimal=False))
    direction = db.Column(db.String(10))  # 'above', 'below', 'cross'
    priority = db.Column(db.Integer, default=2)  # 1-3, higher is more important
    reason = db.Column(db.Text)
    icon = db.Column(db.String(10), default='🔔')
    
    # Status tracking
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'accepted', 'dismissed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    actioned_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'type': self.type,
            'message': self.message,
            'trigger_price': float(self.trigger_price) if self.trigger_price else None,
            'direction': self.direction,
            'priority': self.priority,
            'reason': self.reason,
            'icon': self.icon,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'actioned_at': self.actioned_at.isoformat() if self.actioned_at else None
        }

class Notification(db.Model):
    """Durable feed of fired alerts / system messages so the user can always
    see what triggered and when (Phase 6)."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    alert_id = db.Column(db.Integer, db.ForeignKey('alerts.id', ondelete='SET NULL'), nullable=True)  # source alert, if any
    category = db.Column(db.String(20), default='alert', index=True)  # 'alert', 'system'
    symbol = db.Column(db.String(10), index=True)
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')  # 'low','medium','high','critical'
    read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'alert_id': self.alert_id,
            'category': self.category,
            'symbol': self.symbol,
            'title': self.title,
            'message': self.message,
            'priority': self.priority,
            'read': self.read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Dividend(db.Model):
    """Dividend payments tracking"""
    __tablename__ = 'dividends'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('portfolio_accounts.id'), nullable=True, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    amount_per_share = db.Column(db.Numeric(10, 4, asdecimal=False), nullable=False)
    shares = db.Column(db.Numeric(15, 6, asdecimal=False), nullable=False)
    total_amount = db.Column(db.Numeric(15, 2, asdecimal=False), nullable=False)
    ex_date = db.Column(db.Date, index=True)
    pay_date = db.Column(db.Date)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    reinvested = db.Column(db.Boolean, default=False)
    # Income category: dividend (regular/qualified) | special (special distribution)
    # | lending (share-lending income) | interest
    income_type = db.Column(db.String(20), default='dividend', index=True)
    # Qualified dividends are taxed at long-term rates (0/15/20%); everything
    # else (non-qualified dividends, special distributions, share-lending
    # substitute payments, interest) is ordinary income. Only regular dividends
    # can be qualified — the other income types are inherently ordinary.
    qualified = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'amount_per_share': float(self.amount_per_share),
            'shares': float(self.shares),
            'total_amount': float(self.total_amount),
            'ex_date': self.ex_date.isoformat() if self.ex_date else None,
            'pay_date': self.pay_date.isoformat() if self.pay_date else None,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'reinvested': self.reinvested,
            'income_type': self.income_type or 'dividend',
            'qualified': bool(self.qualified) if self.qualified is not None else True,
            'account_id': self.account_id,
            'notes': self.notes
        }


class PaperTrade(db.Model):
    """Simulated (paper) trades for risk-free strategy testing + expectancy."""
    __tablename__ = 'paper_trades'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(20), nullable=False)
    strategy = db.Column(db.String(60), default='default', index=True)  # tag for grouping
    kind = db.Column(db.String(10), default='option')      # option | stock
    direction = db.Column(db.String(10), default='call')   # call | put | long | short
    contracts = db.Column(db.Numeric(15, 4, asdecimal=False), default=1)
    entry_price = db.Column(db.Numeric(15, 4, asdecimal=False), nullable=False)
    entry_at = db.Column(db.DateTime, default=datetime.utcnow)
    target_price = db.Column(db.Numeric(15, 4, asdecimal=False))
    stop_price = db.Column(db.Numeric(15, 4, asdecimal=False))
    exit_price = db.Column(db.Numeric(15, 4, asdecimal=False))
    exit_at = db.Column(db.DateTime)
    fees = db.Column(db.Numeric(15, 2, asdecimal=False), default=0)
    status = db.Column(db.String(10), default='open', index=True)  # pending | open | closed
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Pending limit order: fills into an open position when the symbol's price crosses
    # limit_price in the trigger direction (set at creation from limit vs. market price).
    limit_price = db.Column(db.Numeric(15, 4, asdecimal=False))
    trigger_side = db.Column(db.String(6))  # 'above' | 'below'

    def fills_at(self, market_price):
        """True if a pending order should fill at the given market price."""
        if self.status != 'pending' or self.limit_price is None or market_price is None:
            return False
        lp = float(self.limit_price)
        return market_price <= lp if self.trigger_side == 'below' else market_price >= lp

    def fill(self):
        """Convert a pending order into an open position. For stock, the fill price IS
        the trigger level (limit_price). For options, limit_price is the UNDERLYING
        trigger and entry_price already holds the premium set at creation — keep it."""
        if (self.kind or 'stock') != 'option':
            self.entry_price = self.limit_price
        self.entry_at = datetime.utcnow()
        self.status = 'open'

    def _mult(self):
        return 100 if (self.kind or 'option') == 'option' else 1

    def pnl(self):
        if self.exit_price is None:
            return None
        sign = -1 if self.direction == 'short' else 1  # bought call/put/long profit if price rises
        gross = sign * (float(self.exit_price) - float(self.entry_price)) * self._mult() * float(self.contracts or 0)
        return round(gross - float(self.fees or 0), 2)

    def pnl_pct(self):
        if self.exit_price is None or not self.entry_price:
            return None
        sign = -1 if self.direction == 'short' else 1
        return round(sign * (float(self.exit_price) - float(self.entry_price)) / float(self.entry_price) * 100, 2)

    def hold_minutes(self):
        if self.exit_at and self.entry_at:
            return round((self.exit_at - self.entry_at).total_seconds() / 60, 1)
        return None

    def to_dict(self):
        return {
            'id': self.id, 'symbol': self.symbol, 'strategy': self.strategy,
            'kind': self.kind, 'direction': self.direction,
            'contracts': float(self.contracts or 0),
            'entry_price': float(self.entry_price) if self.entry_price is not None else None,
            'entry_at': self.entry_at.isoformat() if self.entry_at else None,
            'target_price': float(self.target_price) if self.target_price is not None else None,
            'stop_price': float(self.stop_price) if self.stop_price is not None else None,
            'exit_price': float(self.exit_price) if self.exit_price is not None else None,
            'exit_at': self.exit_at.isoformat() if self.exit_at else None,
            'fees': float(self.fees or 0),
            'status': self.status,
            'notes': self.notes,
            'limit_price': float(self.limit_price) if self.limit_price is not None else None,
            'trigger_side': self.trigger_side,
            'pnl': self.pnl(),
            'pnl_pct': self.pnl_pct(),
            'hold_minutes': self.hold_minutes(),
        }


# Many-to-many: users <-> groups. Referenced by string name in both relationships
# (secondary='user_groups') so class-definition order doesn't matter.
user_groups = db.Table(
    'user_groups',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
)


class Group(db.Model):
    """A permission group (RBAC). Admins define groups, grant each a set of permission
    keys, and assign users. A user's effective permissions = the union across their
    groups (admins bypass and have every permission)."""
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    permissions = db.Column(JSON, default=list)   # list of permission-key strings
    is_system = db.Column(db.Boolean, default=False)  # seeded/built-in groups can't be deleted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('User', secondary='user_groups', back_populates='groups', lazy='selectin')

    def to_dict(self, member_count=None):
        d = {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'permissions': self.permissions or [],
            'is_system': bool(self.is_system),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if member_count is not None:
            d['member_count'] = member_count
        return d


class TradingSOP(db.Model):
    """A user's Standard Operating Procedure — their codified trading policy.

    Versioned: each save is a row. Exactly one row per user is `active`; approving a
    draft archives the prior active one and bumps the version. `rules` is an
    engine-readable JSON of structured knobs (position sizing, filters, blackout);
    `style` holds the questionnaire answers an AI draft was generated from; `doc` is
    the freeform human-readable policy text.
    """
    __tablename__ = 'trading_sops'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    version = db.Column(db.Integer, default=1)
    status = db.Column(db.String(10), default='draft', index=True)  # draft | active | archived
    name = db.Column(db.String(120), default='My Trading SOP')
    rules = db.Column(JSON, default={})    # structured, engine-readable knobs
    style = db.Column(JSON, default={})    # questionnaire answers (if AI-generated)
    doc = db.Column(db.Text)               # freeform policy text (markdown)
    source = db.Column(db.String(20), default='manual')  # manual | ai_generated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'version': self.version,
            'status': self.status,
            'name': self.name,
            'rules': self.rules or {},
            'style': self.style or {},
            'doc': self.doc or '',
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
        }


class FinanceAccount(db.Model):
    """A manually-tracked ASSET account for the net-worth / finances module — bank,
    cash, property, vehicle, etc. Investment accounts are tracked separately
    (PortfolioAccount) and folded into the outlook alongside these."""
    __tablename__ = 'finance_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(30), default='cash')  # checking|savings|cash|brokerage|retirement|property|vehicle|other
    balance = db.Column(db.Numeric(15, 2, asdecimal=False), default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'type': self.type,
            'balance': float(self.balance or 0), 'notes': self.notes,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Debt(db.Model):
    """A liability (mortgage, HELOC, credit card, auto/personal/student loan, etc.) for
    the finances module. `secured` marks debts backed by collateral (a lien on the
    home/car), which matters for borrowing-capacity math."""
    __tablename__ = 'debts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(30), default='other')  # mortgage|heloc|home_equity|credit_card|auto|personal|student|home_improvement|other
    lender = db.Column(db.String(120))
    balance = db.Column(db.Numeric(15, 2, asdecimal=False), default=0)
    apr = db.Column(db.Numeric(6, 3, asdecimal=False), default=0)   # annual %, e.g. 24.490
    min_payment = db.Column(db.Numeric(12, 2, asdecimal=False), default=0)
    secured = db.Column(db.Boolean, default=False)  # backed by collateral (lien)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def monthly_interest(self):
        return round(float(self.balance or 0) * float(self.apr or 0) / 100.0 / 12.0, 2)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'type': self.type, 'lender': self.lender,
            'balance': float(self.balance or 0), 'apr': float(self.apr or 0),
            'min_payment': float(self.min_payment or 0), 'secured': bool(self.secured),
            'monthly_interest': self.monthly_interest(), 'notes': self.notes,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class IncomeSource(db.Model):
    """One income stream for the finances module — a salaried or hourly job (per person).
    Hourly folds overtime at ot_multiplier for hours beyond ot_threshold_hours. Feeds the
    net-worth/DTI outlook, the pay-date calendar, and (Phase 3) the income-tax estimate."""
    __tablename__ = 'income_sources'

    PAY_PERIODS = {'weekly': 52, 'biweekly': 26, 'semimonthly': 24, 'monthly': 12}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    owner = db.Column(db.String(20), default='me')     # me|spouse|joint|other
    type = db.Column(db.String(20), default='salary')  # salary|hourly|self_employed|other
    annual_salary = db.Column(db.Numeric(12, 2, asdecimal=False), default=0)
    hourly_rate = db.Column(db.Numeric(9, 2, asdecimal=False), default=0)
    hours_per_week = db.Column(db.Numeric(6, 2, asdecimal=False), default=40)
    ot_multiplier = db.Column(db.Numeric(4, 2, asdecimal=False), default=1.5)
    ot_threshold_hours = db.Column(db.Numeric(6, 2, asdecimal=False), default=40)
    pay_frequency = db.Column(db.String(15), default='biweekly')
    next_pay_date = db.Column(db.Date)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def weekly_gross(self):
        """Hourly weekly gross incl. overtime; salary → its equivalent weekly slice."""
        if self.type == 'hourly':
            rate = float(self.hourly_rate or 0)
            hrs = float(self.hours_per_week or 0)
            thr = float(self.ot_threshold_hours or 40)
            reg = min(hrs, thr)
            ot = max(0.0, hrs - thr)
            return round(reg * rate + ot * rate * float(self.ot_multiplier or 1.5), 2)
        return round(self.gross_annual() / 52.0, 2)

    def gross_annual(self):
        if self.type == 'hourly':
            rate = float(self.hourly_rate or 0)
            hrs = float(self.hours_per_week or 0)
            thr = float(self.ot_threshold_hours or 40)
            reg = min(hrs, thr)
            ot = max(0.0, hrs - thr)
            return round((reg * rate + ot * rate * float(self.ot_multiplier or 1.5)) * 52.0, 2)
        return round(float(self.annual_salary or 0), 2)

    def gross_monthly(self):
        return round(self.gross_annual() / 12.0, 2)

    def paycheck_estimate(self):
        """Gross per paycheck for the pay frequency (annual ÷ periods)."""
        periods = self.PAY_PERIODS.get(self.pay_frequency, 26)
        return round(self.gross_annual() / periods, 2)

    def upcoming_paydates(self, n=6):
        if not self.next_pay_date:
            return []
        out, d, freq = [], self.next_pay_date, self.pay_frequency
        for _ in range(n):
            out.append(d)
            if freq == 'weekly':
                d = d + timedelta(days=7)
            elif freq == 'biweekly':
                d = d + timedelta(days=14)
            elif freq == 'semimonthly':
                # Anchor to the 1st and 15th; step to the next such date.
                d = date(d.year, d.month, 15) if d.day < 15 else _add_one_month(date(d.year, d.month, 1))
            else:  # monthly
                d = _add_one_month(d)
        return out

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'owner': self.owner, 'type': self.type,
            'annual_salary': float(self.annual_salary or 0), 'hourly_rate': float(self.hourly_rate or 0),
            'hours_per_week': float(self.hours_per_week or 0), 'ot_multiplier': float(self.ot_multiplier or 1.5),
            'ot_threshold_hours': float(self.ot_threshold_hours or 40), 'pay_frequency': self.pay_frequency,
            'next_pay_date': self.next_pay_date.isoformat() if self.next_pay_date else None,
            'active': bool(self.active),
            'weekly_gross': self.weekly_gross(), 'gross_monthly': self.gross_monthly(),
            'gross_annual': self.gross_annual(), 'paycheck_estimate': self.paycheck_estimate(),
            'upcoming_paydates': [d.isoformat() for d in self.upcoming_paydates(4)],
        }


class AIInsight(db.Model):
    """Cached AI read. Keyed by (user_id, kind, input_hash) where input_hash covers the
    model + system + facts, so an unchanged request within its TTL is served from here
    instead of re-calling the (paid) model. This is the main AI cost control — most page
    views hit the cache and spend nothing."""
    __tablename__ = 'ai_insights'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False, index=True)  # finance_outlook|tax|budget|portfolio|sop|...
    input_hash = db.Column(db.String(64), nullable=False, index=True)  # sha256(model|system|facts)
    engine = db.Column(db.String(20))   # claude|gemini|local
    model = db.Column(db.String(60))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, index=True)

    __table_args__ = (db.Index('ix_ai_insights_lookup', 'user_id', 'kind', 'input_hash'),)

    def to_dict(self):
        return {
            'read': self.content, 'engine': self.engine, 'model': self.model,
            'cached': True, 'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DiscussionThread(db.Model):
    """Community discussion threads"""
    __tablename__ = 'discussion_threads'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    symbol = db.Column(db.String(10), index=True)
    category = db.Column(db.String(30), default='general', index=True)  # general, analysis, news, options, crypto
    pinned = db.Column(db.Boolean, default=False)
    locked = db.Column(db.Boolean, default=False)
    upvotes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    author = db.relationship('User', backref='threads', lazy=True)
    replies = db.relationship('ThreadReply', backref='thread', lazy=True, cascade='all, delete-orphan',
                             order_by='ThreadReply.created_at.asc()')
    
    def to_dict(self, include_replies=False):
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'author_name': self.author.name if self.author else 'Unknown',
            'author_picture': self.author.picture_url if self.author else None,
            'title': self.title,
            'body': self.body,
            'symbol': self.symbol,
            'category': self.category,
            'pinned': self.pinned,
            'locked': self.locked,
            'upvotes': self.upvotes,
            'views': self.views,
            'reply_count': len(self.replies) if self.replies else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_replies:
            d['replies'] = [r.to_dict() for r in self.replies]
        return d


class ThreadReply(db.Model):
    """Replies to discussion threads"""
    __tablename__ = 'thread_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('discussion_threads.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    upvotes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    author = db.relationship('User', backref='replies', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'thread_id': self.thread_id,
            'user_id': self.user_id,
            'author_name': self.author.name if self.author else 'Unknown',
            'author_picture': self.author.picture_url if self.author else None,
            'body': self.body,
            'upvotes': self.upvotes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ThreadVote(db.Model):
    """Track user votes on threads and replies"""
    __tablename__ = 'thread_votes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('discussion_threads.id'), nullable=True)
    reply_id = db.Column(db.Integer, db.ForeignKey('thread_replies.id'), nullable=True)
    vote = db.Column(db.Integer, nullable=False)  # 1 = upvote, -1 = downvote
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'thread_id', 'reply_id', name='unique_user_vote'),
    )


class CopyTradingFollow(db.Model):
    """Member-based copy trading follows"""
    __tablename__ = 'copy_trading_follows'
    
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    follower = db.relationship('User', foreign_keys=[follower_id], backref='following')
    leader = db.relationship('User', foreign_keys=[leader_id], backref='followers')
    
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'leader_id', name='unique_follow'),
    )
