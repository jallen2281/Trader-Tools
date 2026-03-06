"""
Database Configuration and Utilities
Phase 2: Database Setup and Connection Management
"""

import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseConfig:
    """Database configuration"""
    
    # Database connection string
    # SQLite for local development (no setup required)
    # PostgreSQL for production: postgresql://username:password@localhost:5432/database_name
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///financial_analysis.db'  # Local SQLite database
    )
    
    # SQLAlchemy settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.getenv('SQL_DEBUG', 'False').lower() == 'true'
    SQLALCHEMY_POOL_SIZE = 10
    SQLALCHEMY_MAX_OVERFLOW = 20
    SQLALCHEMY_POOL_RECYCLE = 3600
    
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
        
        # Migrate: add account_id columns if missing
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        portfolio_cols = [c['name'] for c in inspector.get_columns('portfolio')]
        if 'account_id' not in portfolio_cols:
            db.session.execute(text('ALTER TABLE portfolio ADD COLUMN account_id INTEGER REFERENCES portfolio_accounts(id)'))
            db.session.commit()
            print("✓ Added account_id to portfolio table")
        
        txn_cols = [c['name'] for c in inspector.get_columns('transactions')]
        if 'account_id' not in txn_cols:
            db.session.execute(text('ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES portfolio_accounts(id)'))
            db.session.commit()
            print("✓ Added account_id to transactions table")
        
        # Migrate: add cash_balance to portfolio_accounts if missing
        acct_cols = [c['name'] for c in inspector.get_columns('portfolio_accounts')]
        if 'cash_balance' not in acct_cols:
            db.session.execute(text('ALTER TABLE portfolio_accounts ADD COLUMN cash_balance NUMERIC(15,2) DEFAULT 0'))
            db.session.commit()
            print("✓ Added cash_balance to portfolio_accounts table")
        
        # Create dividends table if it doesn't exist
        if 'dividends' not in inspector.get_table_names():
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
            print("✓ Created dividends table")
        
        # Migrate: add new user columns if missing
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'role' not in user_cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
            db.session.commit()
            print("✓ Added role to users table")
        if 'is_active' not in user_cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            db.session.commit()
        if 'bio' not in user_cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN bio TEXT"))
            db.session.commit()
        if 'copy_trading_enabled' not in user_cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN copy_trading_enabled BOOLEAN DEFAULT 0"))
            db.session.commit()
        if 'last_active' not in user_cols:
            db.session.execute(text("ALTER TABLE users ADD COLUMN last_active DATETIME"))
            db.session.commit()
            print("✓ Added user profile columns")
        
        # Drop old unique constraint and recreate (SQLite can't ALTER constraints, so we skip if column exists)
        print("✓ Database tables created successfully")
        
        # Ensure at least one admin exists - promote the first user
        admin_count = db.session.execute(text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar()
        if admin_count == 0:
            db.session.execute(text("UPDATE users SET role = 'admin' WHERE id = (SELECT MIN(id) FROM users)"))
            db.session.commit()
            print("✓ Promoted first user to admin")
    
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
