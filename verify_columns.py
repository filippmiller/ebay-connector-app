import os
import psycopg2

try:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'ebay_events'
          AND column_name IN ('processed_at', 'processing_error')
        ORDER BY column_name;
    """)
    rows = cur.fetchall()
    print(f"Found columns: {[r[0] for r in rows]}")
    
    # Check index
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'ebay_events' AND indexname = 'idx_ebay_events_topic_processed';
    """)
    indexes = cur.fetchall()
    print(f"Found index: {indexes}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
