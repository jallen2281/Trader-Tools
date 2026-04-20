import sqlite3, json

conn = sqlite3.connect('instance/financial_analysis.db')
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = [r[0] for r in cursor.fetchall()]
print(f"Tables: {tables}\n")
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  {t}: {count} rows")
conn.close()
