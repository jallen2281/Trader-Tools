
"""
Migrate data from SQLite to PostgreSQL.

Run inside the pod:
  kubectl exec -it <pod> -n trader-tools -- python /app/migrate_sqlite_to_pg.py

Or with explicit args:
  python migrate_sqlite_to_pg.py [sqlite_path] [postgresql_url]

Defaults:
  sqlite_path = /data/financial_analysis.db
  postgresql_url = DATABASE_URL env var
"""

import os
import sys
import sqlite3
import psycopg2
from urllib.parse import quote_plus

SQLITE_PATH = os.getenv('SQLITE_PATH', '/data/financial_analysis.db')

# Tables in dependency order (parents before children)
TABLES = [
    'users',
    'user_sessions',
    'watchlist',
    'portfolio_accounts',
    'portfolio',
    'transactions',
    'options_positions',
    'alerts',
    'analysis_history',
    'ml_patterns',
    'ml_predictions',
    'monitoring_log',
    'market_conditions',
    'portfolio_snapshots',
    'alert_suggestions',
    'dividends',
    'discussion_threads',
    'thread_replies',
    'thread_votes',
    'copy_trading_follows',
]

def get_sqlite_tables(sqlite_conn):
    """Get list of tables that actually exist in SQLite."""
    cursor = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {row[0] for row in cursor.fetchall()}

def get_columns(sqlite_conn, table):
    """Get column names for a table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info(\"{table}\")")
    return [row[1] for row in cursor.fetchall()]

def _build_pg_url(raw):
    """Build psycopg2-compatible URL with encoded password."""
    if raw.startswith('postgres://'):
        raw = 'postgresql://' + raw[len('postgres://'):]
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

def migrate_table(sqlite_conn, pg_conn, table):
    """Migrate a single table from SQLite to PostgreSQL."""
    columns = get_columns(sqlite_conn, table)
    if not columns:
        print(f"  ⚠ No columns found for {table}, skipping")
        return 0

    # Read all rows from SQLite
    cursor = sqlite_conn.execute(f"SELECT * FROM \"{table}\"")
    rows = cursor.fetchall()

    if not rows:
        print(f"  ℹ {table}: 0 rows (empty)")
        return 0

    # Check which columns exist in PostgreSQL and their types
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        (table,)
    )
    pg_col_types = {row[0]: row[1] for row in pg_cursor.fetchall()}
    pg_columns = set(pg_col_types.keys())

    # Only use columns that exist in both
    common_cols = [c for c in columns if c in pg_columns]
    col_indices = [columns.index(c) for c in common_cols]

    if not common_cols:
        print(f"  ⚠ No matching columns for {table}, skipping")
        return 0

    # Print detected column types for debugging
    print(f"    [DEBUG] {table} column types: {pg_col_types}")

    # Fallback: explicit known boolean columns by table name
    explicit_bool_map = {
        'users': {'is_active', 'copy_trading_enabled'},
        'alerts': {'triggered', 'enabled'},
        'dividends': {'reinvested'},
        'discussion_threads': {'pinned', 'locked'},
    }
    bool_cols = [col for col in common_cols if pg_col_types.get(col) == 'boolean']
    # Add explicit known bools if present
    for col in explicit_bool_map.get(table, set()):
        if col in common_cols and col not in bool_cols:
            bool_cols.append(col)

    # Filter and convert rows to only include common columns, with bool conversion
    filtered_rows = []
    for row in rows:
        new_row = list(row[i] for i in col_indices)
        for idx, col in enumerate(common_cols):
            if col in bool_cols:
                val = new_row[idx]
                if val is None:
                    new_row[idx] = None
                elif isinstance(val, bool):
                    new_row[idx] = val
                elif isinstance(val, int):
                    new_row[idx] = bool(val)
                elif isinstance(val, str):
                    if val in ('0', '1'):
                        new_row[idx] = val == '1'
                    elif val.lower() in ('true', 'false'):
                        new_row[idx] = val.lower() == 'true'
        filtered_rows.append(tuple(new_row))

    # Build INSERT with ON CONFLICT DO NOTHING to skip duplicates
    col_list = ', '.join(f'"{c}"' for c in common_cols)
    placeholders = ', '.join(['%s'] * len(common_cols))
    insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # Insert in batches
    batch_size = 500
    inserted = 0
    for i in range(0, len(filtered_rows), batch_size):
        batch = filtered_rows[i:i + batch_size]
        for row in batch:
            try:
                pg_cursor.execute(insert_sql, row)
                inserted += 1
            except Exception as e:
                pg_conn.rollback()
                print(f"  ⚠ Error inserting row in {table}: {e}")
                continue
    pg_conn.commit()

    # Reset sequence to max id
    if 'id' in common_cols:
        seq_name = f"{table}_id_seq"
        try:
            pg_cursor.execute(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM \"{table}\"), 0) + 1, false)")
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()

    print(f"  ✓ {table}: {inserted}/{len(rows)} rows migrated")
    return inserted

def main():
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else SQLITE_PATH
    pg_raw = sys.argv[2] if len(sys.argv) > 2 else os.getenv('DATABASE_URL', '')

    if not pg_raw:
        print("Error: No PostgreSQL URL. Provide as arg or set DATABASE_URL env var.")
        sys.exit(1)

    if not os.path.exists(sqlite_path):
        print(f"Error: SQLite file not found: {sqlite_path}")
        sys.exit(1)

    pg_url = _build_pg_url(pg_raw)

    print(f"SQLite source: {sqlite_path}")
    print(f"PostgreSQL target: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print()

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)

def migrate_table(sqlite_conn, pg_conn, table):
    """Migrate a single table from SQLite to PostgreSQL."""
    columns = get_columns(sqlite_conn, table)
    if not columns:
        print(f"  ⚠ No columns found for {table}, skipping")
        return 0

    # Read all rows from SQLite
    cursor = sqlite_conn.execute(f"SELECT * FROM \"{table}\"")
    rows = cursor.fetchall()

    if not rows:
        print(f"  ℹ {table}: 0 rows (empty)")
        return 0

    # Check which columns exist in PostgreSQL
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        (table,)
    )
    pg_columns = {row[0] for row in pg_cursor.fetchall()}

    # Only use columns that exist in both
    common_cols = [c for c in columns if c in pg_columns]
    col_indices = [columns.index(c) for c in common_cols]

    if not common_cols:
        print(f"  ⚠ No matching columns for {table}, skipping")
        return 0

    # Filter rows to only include common columns
    filtered_rows = []
    for row in rows:
        filtered_rows.append(tuple(row[i] for i in col_indices))

    # Build INSERT with ON CONFLICT DO NOTHING to skip duplicates
    col_list = ', '.join(f'"{c}"' for c in common_cols)
    placeholders = ', '.join(['%s'] * len(common_cols))
    insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # Insert in batches
    batch_size = 500
    inserted = 0
    for i in range(0, len(filtered_rows), batch_size):
        batch = filtered_rows[i:i + batch_size]
        for row in batch:
            try:
                pg_cursor.execute(insert_sql, row)
                inserted += 1
            except Exception as e:
                pg_conn.rollback()
                print(f"  ⚠ Error inserting row in {table}: {e}")
                continue
    

    pg_cursor.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        (table,)
    )
    pg_col_types = {row[0]: row[1] for row in pg_cursor.fetchall()}
    pg_columns = set(pg_col_types.keys())

    # Only use columns that exist in both
    common_cols = [c for c in columns if c in pg_columns]
    col_indices = [columns.index(c) for c in common_cols]

    if not common_cols:
        print(f"  ⚠ No matching columns for {table}, skipping")
        return 0

    # Print detected column types for debugging
    print(f"    [DEBUG] {table} column types: {pg_col_types}")

    # Fallback: explicit known boolean columns by table name
    explicit_bool_map = {
        'users': {'is_active', 'copy_trading_enabled'},
        'alerts': {'triggered', 'enabled'},
        'dividends': {'reinvested'},
        'discussion_threads': {'pinned', 'locked'},
    }
    bool_cols = [col for col in common_cols if pg_col_types.get(col) == 'boolean']
    # Add explicit known bools if present
    for col in explicit_bool_map.get(table, set()):
        if col in common_cols and col not in bool_cols:
            bool_cols.append(col)

    # Filter and convert rows to only include common columns, with bool conversion
    filtered_rows = []
    for row in rows:
        new_row = list(row[i] for i in col_indices)
        for idx, col in enumerate(common_cols):
            if col in bool_cols:
                val = new_row[idx]
                if val is None:
                    new_row[idx] = None
                elif isinstance(val, bool):
                    new_row[idx] = val
                elif isinstance(val, int):
                    new_row[idx] = bool(val)
                elif isinstance(val, str):
                    if val in ('0', '1'):
                        new_row[idx] = val == '1'
                    elif val.lower() in ('true', 'false'):
                        new_row[idx] = val.lower() == 'true'

        filtered_rows.append(tuple(new_row))

if __name__ == '__main__':
    main()
