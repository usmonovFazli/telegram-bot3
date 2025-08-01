import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()

DB_PARAMS = {
    "dbname": os.getenv("PG_DB", "targibot3"),
    "user": os.getenv("PG_USER", "targibot03"),
    "password": os.getenv("PG_PASSWORD", "keXnxu56OvT1um1jdoIBUk9FAdVpr8rD"),
    "host": os.getenv("PG_HOST", "dpg-d25p0u6r433s73eck3n0-a"),
    "port": os.getenv("PG_PORT", "5432"),
}


def connect():
    return psycopg2.connect(**DB_PARAMS)

def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS channelsss (
                    id BIGINT PRIMARY KEY,
                    title TEXT,
                    members INTEGER,
                    videos INTEGER DEFAULT 0,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    type TEXT DEFAULT 'unknown',
                    link TEXT DEFAULT ''
                );
            """)
        conn.commit()

def add_or_update_channel(chat_id, title, members, chat_type="unknown", link=""):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO channelsss (id, title, members, type, link)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET title = EXCLUDED.title,
                    members = EXCLUDED.members,
                    type = EXCLUDED.type,
                    link = EXCLUDED.link;
            """, (chat_id, title, members, chat_type, link))
        conn.commit()

def increment_video_count(chat_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE channelsss SET videos = videos + 1 WHERE id = %s;
            """, (chat_id,))
        conn.commit()

def get_channels():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, members, videos, date_added, type, link
                FROM channelsss ORDER BY title;
            """)
            return cur.fetchall()

def get_channels_full():
    return get_channels()
