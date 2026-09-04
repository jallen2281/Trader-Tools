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
    
    # Pool settings only apply to non-SQLite engines.
    # NOTE: Flask-SQLAlchemy >= 3.0 IGNORES the individual SQLALCHEMY_POOL_SIZE /
    # SQLALCHEMY_MAX_OVERFLOW / SQLALCHEMY_POOL_RECYCLE keys — every engine/pool
    # setting must live inside SQLALCHEMY_ENGINE_OPTIONS or it is silently dropped
    # (leaving the default pool size and, critically, NO time-based recycle so
    # connections can go stale between Postgres's server-side timeout and use).
    if not SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,   # test each connection before use (drops stale ones)
            'pool_size': 10,
            'max_overflow': 20,
            'pool_recycle': 3600,    # recycle hourly to pre-empt server-side idle timeouts
        }
    
    # Session configuration.
    # The dev fallback is fine locally and catastrophic in production: it is a literal in a
    # public repo, so anything signed with it (every session cookie, hence every user's
    # identity) is forgeable by anyone. Rather than degrade silently when the env var is
    # missing, refuse to boot in production — a CrashLoopBackOff is a far better outcome
    # than a quietly forgeable session.
    _DEV_SECRET_KEY = 'dev-secret-key-change-in-production'
    SECRET_KEY = os.getenv('SECRET_KEY', _DEV_SECRET_KEY)
    if SECRET_KEY == _DEV_SECRET_KEY and os.getenv('FLASK_ENV', '').lower() == 'production':
        raise RuntimeError(
            'SECRET_KEY is unset or still the built-in development value while '
            'FLASK_ENV=production. Refusing to start with the '
            'built-in development key, which would make every session cookie forgeable. '
            'Set SECRET_KEY in the trader-tools secret.'
        )
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
        is_pg = _is_postgres(db)

        # Imported unconditionally: text() is used all through this function, not just on the
        # Postgres-only paths. Importing it inside `if is_pg` left it unbound on SQLite, so
        # init_database raised and the except handler silently disabled the entire Phase 2
        # stack (auth, RBAC, login) instead of just skipping a migration.
        from sqlalchemy import text

        # PostgreSQL: drop orphaned sequences that conflict with SERIAL columns
        # (Supabase template databases may include pre-existing sequences)
        if is_pg:
            existing_tables = set()
            try:
                result = db.session.execute(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ))
                existing_tables = {r[0] for r in result}
            except Exception:
                pass
            try:
                result = db.session.execute(text(
                    "SELECT sequencename FROM pg_sequences WHERE schemaname='public'"
                ))
                for (seq_name,) in result:
                    # Only drop sequences whose parent table doesn't exist yet
                    table_name = seq_name.replace('_id_seq', '')
                    if table_name not in existing_tables:
                        db.session.execute(text(f'DROP SEQUENCE IF EXISTS "{seq_name}" CASCADE'))
                        logger.info(f"Dropped orphaned sequence: {seq_name}")
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Could not clean orphaned sequences: {e}")
        
        db.create_all()
        
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        # Migrate: add account_id columns if missing
        if _add_column_if_missing(db, inspector, 'portfolio', 'account_id', 'INTEGER REFERENCES portfolio_accounts(id)'):
            logger.info("✓ Added account_id to portfolio table")

        # Migrate: add position-context columns (intent + ipo_lock_until) if missing
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'portfolio', 'intent', 'VARCHAR(20)')
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'portfolio', 'ipo_lock_until', 'DATE'):
            logger.info("✓ Added intent/ipo_lock_until to portfolio table")
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'portfolio', 'take_profit_pct', 'NUMERIC(6,2)')
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'portfolio', 'stop_loss_pct', 'NUMERIC(6,2)')
        
        # Re-inspect after potential schema change
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'transactions', 'account_id', 'INTEGER REFERENCES portfolio_accounts(id)'):
            logger.info("✓ Added account_id to transactions table")
        
        # Migrate: add cash_balance to portfolio_accounts if missing
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'portfolio_accounts', 'cash_balance', 'NUMERIC(15,2)', '0'):
            logger.info("✓ Added cash_balance to portfolio_accounts table")

        # Migrate: add 1099/irregular-income columns to income_sources (create_all only
        # creates NEW tables; it never adds columns to an existing one). income_events is
        # a new table, so create_all handles it — only the added columns need this.
        inspector = inspect(db.engine)
        if 'income_sources' in inspector.get_table_names():
            _add_column_if_missing(db, inspector, 'income_sources', 'tax_form', "VARCHAR(6)", "'W2'")
            inspector = inspect(db.engine)
            _add_column_if_missing(db, inspector, 'income_sources', 'irregular', 'BOOLEAN', 'false')
            inspector = inspect(db.engine)
            _add_column_if_missing(db, inspector, 'income_sources', 'estimated_annual', 'NUMERIC(12,2)', '0')
            inspector = inspect(db.engine)
            if _add_column_if_missing(db, inspector, 'income_sources', 'est_tax_rate', 'NUMERIC(5,2)', '0'):
                logger.info("✓ Added 1099/irregular columns to income_sources table")

        # Migrate: privacy-consent columns on users (create_all never alters an existing table)
        inspector = inspect(db.engine)
        if 'users' in inspector.get_table_names():
            _add_column_if_missing(db, inspector, 'users', 'privacy_consent_at', 'TIMESTAMP')
            inspector = inspect(db.engine)
            if _add_column_if_missing(db, inspector, 'users', 'privacy_consent_version', 'VARCHAR(20)'):
                logger.info("✓ Added privacy-consent columns to users table")

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

        # Migrate: add income_type to dividends (dividend / special / lending / interest)
        inspector = inspect(db.engine)
        if _add_column_if_missing(db, inspector, 'dividends', 'income_type', 'VARCHAR(20)', "'dividend'"):
            logger.info("✓ Added income_type to dividends table")

        # Migrate: add qualified flag (qualified dividends taxed at LT rates).
        # Non-dividend income types are inherently ordinary → set them non-qualified.
        inspector = inspect(db.engine)
        _bool_true = 'TRUE' if _is_postgres(db) else '1'
        _bool_false = 'FALSE' if _is_postgres(db) else '0'
        if _add_column_if_missing(db, inspector, 'dividends', 'qualified', 'BOOLEAN', _bool_true):
            db.session.execute(text(
                f"UPDATE dividends SET qualified = {_bool_false} WHERE income_type != 'dividend'"))
            db.session.commit()
            logger.info("✓ Added qualified to dividends table")

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
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'alert_check_interval', 'INTEGER', '900')
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'watchlist_refresh_interval', 'INTEGER', '60')
        inspector = inspect(db.engine)
        # Soft-delete columns (account lifecycle)
        _add_column_if_missing(db, inspector, 'users', 'deleted_at', timestamp_type)
        inspector = inspect(db.engine)
        _add_column_if_missing(db, inspector, 'users', 'deleted_by', 'INTEGER')
        # Paper pending-limit-order columns
        try:
            inspector = inspect(db.engine)
            if 'paper_trades' in inspector.get_table_names():
                _add_column_if_missing(db, inspector, 'paper_trades', 'limit_price', 'NUMERIC(15,4)')
                inspector = inspect(db.engine)
                _add_column_if_missing(db, inspector, 'paper_trades', 'trigger_side', 'VARCHAR(6)')
        except Exception as _pe:
            logger.warning(f"paper_trades migration skipped: {_pe}")

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
        # Reversibility: if this account was soft-deleted, logging back in with the
        # same Google identity within the retention window restores it (and re-hydrates
        # the PII that was scrubbed at delete time). Once an admin hard-purges, the row
        # is gone and this branch never runs — a fresh account is created instead.
        if getattr(user, 'deleted_at', None) is not None:
            user.deleted_at = None
            user.deleted_by = None
            user.is_active = True
            user.email = email

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
