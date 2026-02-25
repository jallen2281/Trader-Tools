"""
Database Models for Financial Analysis System
Phase 2: SQLAlchemy ORM Models
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import JSON

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User account model"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    picture_url = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    preferences = db.Column(JSON, default={})
    
    # Relationships
    watchlist = db.relationship('Watchlist', backref='user', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    portfolio = db.relationship('Portfolio', backref='user', lazy=True, cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    options_positions = db.relationship('OptionsPosition', backref='user', lazy=True, cascade='all, delete-orphan')
    analysis_history = db.relationship('AnalysisHistory', backref='user', lazy=True, cascade='all, delete-orphan')
    sessions = db.relationship('UserSession', backref='user', lazy=True, cascade='all, delete-orphan')
    portfolio_snapshots = db.relationship('PortfolioSnapshot', backref='user', lazy=True, cascade='all, delete-orphan')  # Phase 4
    
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
    target_price = db.Column(db.Numeric(10, 2))
    current_price = db.Column(db.Numeric(10, 2))
    
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

class Portfolio(db.Model):
    """User's portfolio holdings"""
    __tablename__ = 'portfolio'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    asset_type = db.Column(db.String(20), nullable=False)  # 'stock', 'option', 'etf'
    quantity = db.Column(db.Numeric(15, 6), nullable=False)
    average_cost = db.Column(db.Numeric(10, 4), nullable=False)
    current_price = db.Column(db.Numeric(10, 4))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'symbol', 'asset_type', name='unique_user_position'),
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
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

class Transaction(db.Model):
    """Transaction history for cost basis tracking"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    asset_type = db.Column(db.String(20), nullable=False)  # 'stock', 'option', 'etf'
    transaction_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    quantity = db.Column(db.Numeric(15, 6), nullable=False)
    price = db.Column(db.Numeric(10, 4), nullable=False)
    commission = db.Column(db.Numeric(10, 2), default=0)
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
            'notes': self.notes
        }

class OptionsPosition(db.Model):
    """Options positions tracking"""
    __tablename__ = 'options_positions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    underlying_symbol = db.Column(db.String(10), nullable=False, index=True)
    option_type = db.Column(db.String(10), nullable=False)  # 'call' or 'put'
    strike_price = db.Column(db.Numeric(10, 2), nullable=False)
    expiration_date = db.Column(db.Date, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    premium_paid = db.Column(db.Numeric(10, 4), nullable=False)
    current_premium = db.Column(db.Numeric(10, 4))
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
    confidence = db.Column(db.Numeric(5, 4), nullable=False)
    prediction = db.Column(db.String(20), nullable=False)  # 'bullish', 'bearish', 'neutral'
    time_horizon = db.Column(db.String(20))
    detected_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    pattern_data = db.Column(JSON)
    price_at_detection = db.Column(db.Numeric(10, 4))
    
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
    predicted_price = db.Column(db.Numeric(10, 4))
    confidence = db.Column(db.Numeric(5, 4), nullable=False)
    time_horizon = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    target_date = db.Column(db.DateTime, index=True)
    actual_price = db.Column(db.Numeric(10, 4))
    actual_direction = db.Column(db.String(20))
    accuracy_score = db.Column(db.Numeric(5, 4))
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
    vix = db.Column(db.Numeric(10, 2))  # S&P 500 volatility (^VIX)
    vxn = db.Column(db.Numeric(10, 2))  # Nasdaq 100 volatility (^VXN)
    rvx = db.Column(db.Numeric(10, 2))  # Russell 2000 volatility (^RVX)
    vix_change = db.Column(db.Numeric(10, 2))  # Today's VIX change
    vix_percentile = db.Column(db.Numeric(5, 2))  # Historical percentile (0-100)
    
    # Market Sentiment
    market_sentiment = db.Column(db.String(20))  # 'fear', 'greed', 'neutral', 'extreme_fear', 'extreme_greed'
    fear_greed_index = db.Column(db.Integer)  # 0-100
    volatility_regime = db.Column(db.String(20))  # 'low', 'normal', 'elevated', 'high', 'extreme'
    
    # Major Indices
    spx_price = db.Column(db.Numeric(10, 2))
    spx_change = db.Column(db.Numeric(10, 2))
    spx_change_pct = db.Column(db.Numeric(5, 2))
    ndx_price = db.Column(db.Numeric(10, 2))
    ndx_change = db.Column(db.Numeric(10, 2))
    ndx_change_pct = db.Column(db.Numeric(5, 2))
    
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
    total_value = db.Column(db.Numeric(15, 2), nullable=False)
    total_cost_basis = db.Column(db.Numeric(15, 2), nullable=False)
    total_pnl = db.Column(db.Numeric(15, 2), nullable=False)
    total_pnl_pct = db.Column(db.Numeric(10, 4), nullable=False)
    
    # Daily changes
    daily_change = db.Column(db.Numeric(15, 2))
    daily_change_pct = db.Column(db.Numeric(10, 4))
    
    # Allocation breakdown
    stock_value = db.Column(db.Numeric(15, 2))
    options_value = db.Column(db.Numeric(15, 2))
    cash_value = db.Column(db.Numeric(15, 2))
    
    # Risk metrics
    portfolio_beta = db.Column(db.Numeric(10, 4))
    portfolio_var = db.Column(db.Numeric(15, 2))
    portfolio_sharpe = db.Column(db.Numeric(10, 4))
    
    # Market context
    spx_price = db.Column(db.Numeric(10, 2))
    vix_level = db.Column(db.Numeric(10, 2))
    
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
    trigger_price = db.Column(db.Numeric(10, 2))
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
