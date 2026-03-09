"""
Database Configuration and Utilities
Phase 2: Database Setup and Connection Management
"""

import os
import logging
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def _build_sqlalchemy_url():
    """Build a SQLAlchemy-compatible URL, safely encoding password characters."""
    raw = os.getenv('DATABASE_URL', 'sqlite:///financial_analysis.db')
    if raw.startswith('postgres://'):
        raw = 'postgresql://' + raw[len('postgres://'):]
    if raw.startswith('sqlite'):
        return raw
    # Manual parsing — urlparse can't handle unescaped # & in passwords
    # Format: postgresql://user:password@host:port/database
    rest = raw.split('://', 1)[1]
    creds, hostpart = rest.rsplit('@', 1)
    user, password = creds.split(':', 1)
    if '/' in hostpart:
        host_port, db = hostpart.split('/', 1)
    else:
        host_port, db = hostpart, 'postgres'
    if ':' in host_port:
        host, port = host_port.rsplit(':', 1)
    else:
        host, port = host_port, '5432'
    return f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{db}"

class DatabaseConfig:
    """Database configuration"""
    
    SQLALCHEMY_DATABASE_URI = _build_sqlalchemy_url()
    
    # SQLAlchemy settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv('SQL_DEBUG', 'False').lower() == 'true'
    
    # Pool settings only apply to non-SQLite engines
    if not SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        SQLALCHEMY_POOL_SIZE = 10
        SQLALCHEMY_MAX_OVERFLOW = 20
        SQLALCHEMY_POOL_RECYCLE = 3600
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,  # Verify connections before use
        }
    
    # Session configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # Google OAuth configuration
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
    
    # Application settings
    APP_NAME = "Financial Analysis System"
    APP_VERSION = "2.0.0"


def _is_postgres(db):
    """Check if we're connected to PostgreSQL"""
    return str(db.engine.url).startswith('postgresql')


def _add_column_if_missing(db, inspector, table, column, col_type, default=None):
    """Safely add a column to a table if it doesn't exist (works on both SQLite and PostgreSQL)"""
    from sqlalchemy import text
    cols = [c['name'] for c in inspector.get_columns(table)]
    if column not in cols:
        default_clause = f" DEFAULT {default}" if default is not None else ""
        db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}'))
        db.session.commit()
        return True
    return False


def init_database(app):
    """Initialize database with app"""
    from models import db
    
    # Configure app
    app.config.from_object(DatabaseConfig)
    
    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Create tables
    with app.app_context():
        db.create_all()
        
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        is_pg = _is_postgres(db)
        
        # Migrate: add account_id columns if missing
        if _add_column_if_missing(db, inspector, 'portfolio', 'account_id', 'INTEGER REFERENCES portfolio_accounts(id)'):
            logger.info("✓ Added account_id to portfolio table")
        
        # Re-inspect after potential schema change
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'transactions', 'account_id', 'INTEGER REFERENCES portfolio_accounts(id)'):
            logger.info("✓ Added account_id to transactions table")
        
        # Migrate: add cash_balance to portfolio_accounts if missing
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'portfolio_accounts', 'cash_balance', 'NUMERIC(15,2)', '0'):
            logger.info("✓ Added cash_balance to portfolio_accounts table")
        
        # Create dividends table if it doesn't exist
        if 'dividends' not in inspector.get_table_names():
            if is_pg:
                db.session.execute(text('''
                    CREATE TABLE IF NOT EXISTS dividends (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        account_id INTEGER REFERENCES portfolio_accounts(id),
                        symbol VARCHAR(10) NOT NULL,
                        amount_per_share NUMERIC(10,4) NOT NULL,
                        shares NUMERIC(15,6) NOT NULL,
                        total_amount NUMERIC(15,2) NOT NULL,
                        ex_date DATE,
                        pay_date DATE,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reinvested BOOLEAN DEFAULT FALSE,
                        notes TEXT
                    )
                '''))
            else:
                db.session.execute(text('''
                    CREATE TABLE IF NOT EXISTS dividends (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        account_id INTEGER REFERENCES portfolio_accounts(id),
                        symbol VARCHAR(10) NOT NULL,
                        amount_per_share NUMERIC(10,4) NOT NULL,
                        shares NUMERIC(15,6) NOT NULL,
                        total_amount NUMERIC(15,2) NOT NULL,
                        ex_date DATE,
                        pay_date DATE,
                        recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        reinvested BOOLEAN DEFAULT 0,
                        notes TEXT
                    )
                '''))
            db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_dividends_user_id ON dividends(user_id)'))
            db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_dividends_symbol ON dividends(symbol)'))
            db.session.commit()
            logger.info("✓ Created dividends table")
        
        # Migrate: add new user columns if missing
        inspector = inspect(db.engine)
        bool_false = 'FALSE' if is_pg else '0'
        bool_true = 'TRUE' if is_pg else '1'
        timestamp_type = 'TIMESTAMP' if is_pg else 'DATETIME'
        
        if _add_column_if_missing(db, inspector, 'users', 'role', "VARCHAR(20)", "'user'"):
            logger.info("✓ Added role to users table")
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'is_active', 'BOOLEAN', bool_true)
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'bio', 'TEXT')
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'copy_trading_enabled', 'BOOLEAN', bool_false)
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'users', 'last_active', timestamp_type):
            logger.info("✓ Added user profile columns")
        
        logger.info("✓ Database tables created successfully")
        
        # Ensure at least one admin exists - promote the first user
        admin_count = db.session.execute(text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar()
        if admin_count == 0:
            db.session.execute(text("UPDATE users SET role = 'admin' WHERE id = (SELECT MIN(id) FROM users)"))
            db.session.commit()
            logger.info("✓ Promoted first user to admin")
        
        # Migrate: normalize crypto symbols (e.g., AVAX → AVAX-USD for yfinance)
        if is_pg:
            crypto_fixed = db.session.execute(text(
                "UPDATE portfolio SET symbol = symbol || '-USD' "
                "WHERE asset_type = 'crypto' AND symbol NOT LIKE '%-USD' "
                "AND symbol NOT LIKE '%-EUR' AND symbol NOT LIKE '%-GBP' "
                "AND symbol NOT LIKE '%-JPY' AND symbol NOT LIKE '%-BTC' "
                "AND symbol NOT LIKE '%-ETH' AND symbol NOT LIKE '%-USDT' "
                "AND symbol NOT LIKE '%-BUSD' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM portfolio p2 "
                "  WHERE p2.user_id = portfolio.user_id "
                "  AND p2.symbol = portfolio.symbol || '-USD' "
                "  AND p2.asset_type = portfolio.asset_type "
                "  AND (p2.account_id = portfolio.account_id OR (p2.account_id IS NULL AND portfolio.account_id IS NULL))"
                ")"
            )).rowcount
        else:
            crypto_fixed = db.session.execute(text(
                "UPDATE OR IGNORE portfolio SET symbol = symbol || '-USD' "
                "WHERE asset_type = 'crypto' AND symbol NOT LIKE '%-USD' "
                "AND symbol NOT LIKE '%-EUR' AND symbol NOT LIKE '%-GBP' "
                "AND symbol NOT LIKE '%-JPY' AND symbol NOT LIKE '%-BTC' "
                "AND symbol NOT LIKE '%-ETH' AND symbol NOT LIKE '%-USDT' "
                "AND symbol NOT LIKE '%-BUSD'"
            )).rowcount
        if crypto_fixed > 0:
            db.session.commit()
            logger.info(f"✓ Normalized {crypto_fixed} crypto symbol(s) (appended -USD)")
    
    return db


def get_or_create_user(google_id, email, name, picture_url):
    """Get existing user or create new one"""
    from models import db, User
    from datetime import datetime
    
    user = User.query.filter_by(google_id=google_id).first()
    
    if not user:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            picture_url=picture_url,
            created_at=datetime.utcnow()
        )
        db.session.add(user)
    else:
        # Update user info
        user.name = name
        user.picture_url = picture_url
    
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    return user


def migrate_localStorage_to_db(user_id, watchlist_data, alerts_data):
    """Migrate data from localStorage to database"""
    from models import db, Watchlist, Alert
    
    # Migrate watchlist
    for symbol in watchlist_data:
        existing = Watchlist.query.filter_by(user_id=user_id, symbol=symbol).first()
        if not existing:
            watchlist_item = Watchlist(user_id=user_id, symbol=symbol)
            db.session.add(watchlist_item)
    
    # Migrate alerts
    for alert in alerts_data:
        existing = Alert.query.filter_by(
            user_id=user_id,
            symbol=alert['symbol'],
            alert_type=alert['type'],
            target_price=alert['targetPrice']
        ).first()
        
        if not existing:
            alert_item = Alert(
                user_id=user_id,
                symbol=alert['symbol'],
                alert_type=alert['type'],
                target_price=alert['targetPrice'],
                enabled=True
            )
            db.session.add(alert_item)
    
    db.session.commit()
    print(f"✓ Migrated {len(watchlist_data)} watchlist items and {len(alerts_data)} alerts")
