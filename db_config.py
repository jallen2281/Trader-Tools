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
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
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
        print("✓ Database tables created successfully")
    
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
