from app.config import settings

if "postgresql" in settings.DATABASE_URL:
    from app.services.postgres_database import PostgresDatabase
    db = PostgresDatabase()
else:
    from app.services.sqlite_database import SQLiteDatabase
    db = SQLiteDatabase()
