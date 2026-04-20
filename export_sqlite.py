"""Export SQLite data to JSON for import into PostgreSQL."""
import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect('instance/financial_analysis.db')
conn.row_factory = sqlite3.Row

tables_to_export = [
    'users', 'watchlist', 'alerts', 'portfolio_accounts', 'portfolio',
    'transactions', 'options_positions', 'dividends', 'user_sessions',
    'market_conditions', 'portfolio_snapshots', 'alert_suggestions',
    'discussion_threads', 'thread_replies', 'thread_votes', 'copy_trading_follows',
]

export = {}
for table in tables_to_export:
    try:
        cursor = conn.execute(f'SELECT * FROM "{table}"')
        rows = [dict(row) for row in cursor.fetchall()]
        if rows:
            export[table] = rows
            print(f"  {table}: {len(rows)} rows")
    except Exception as e:
        pass  # Table doesn't exist in SQLite

conn.close()

with open('sqlite_export.json', 'w') as f:
    json.dump(export, f, default=str, indent=2)

print(f"\nExported to sqlite_export.json ({len(export)} tables)")
