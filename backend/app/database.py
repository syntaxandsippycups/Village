from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import DATABASE_URL
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {})
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_connect(conn, _):
        conn.isolation_level = None
        conn.execute('PRAGMA foreign_keys=ON')
    @event.listens_for(engine, 'begin')
    def sqlite_begin(conn):
        # SQLite has no row locks. Serialize write/read transactions locally so
        # capacity checks and slot claims have the same guarantees as PostgreSQL.
        conn.exec_driver_sql('BEGIN IMMEDIATE')
class Base(DeclarativeBase):
    pass
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
def get_db():
    with SessionLocal() as db:
        yield db
