from sqlalchemy import Column, BigInteger, String, DateTime, Text, Boolean, Integer, Numeric, ForeignKey, Table, inspect
from sqlalchemy.sql import func
from sqlalchemy.exc import NoSuchTableError, OperationalError

from app.database import Base, engine
from app.utils.logger import logger


# Reflect the legacy tbl_timesheet table from Supabase
# This table contains 6000+ timesheet records and is the source of truth
try:
    tbl_timesheet_table = Table(
        "tbl_timesheet",  # REAL table name, do not change
        Base.metadata,
        autoload_with=engine,
    )
    # Inspect primary key constraint
    inspector = inspect(engine)
    pk_info = inspector.get_pk_constraint(
        tbl_timesheet_table.name,
        schema=tbl_timesheet_table.schema,
    )
    pk_cols = list(pk_info.get("constrained_columns") or [])
    # If no explicit PK constraint, look for common PK column names
    if not pk_cols:
        for potential_pk in ["ID", "id", "TimesheetID", "timesheet_id"]:
            if potential_pk in tbl_timesheet_table.c:
                pk_cols = [potential_pk]
                logger.info(f"Using {potential_pk} as primary key for tbl_timesheet")
                break
except (NoSuchTableError, OperationalError) as exc:
    logger.warning(
        "tbl_timesheet reflection failed (%s); Timesheet will be abstract in this environment",
        type(exc).__name__,
    )
    tbl_timesheet_table = None
    pk_cols = []


if tbl_timesheet_table is not None and pk_cols:
    class Timesheet(Base):
        """Legacy timesheet table mapped to tbl_timesheet in Supabase.
        
        This table contains 6000+ existing timesheet records. The schema is
        auto-discovered via reflection to ensure perfect compatibility with
        the actual database structure.
        """
        
        __table__ = tbl_timesheet_table
        __mapper_args__ = {
            "primary_key": tuple(tbl_timesheet_table.c[col] for col in pk_cols),
        }
else:
    class Timesheet(Base):
        """Abstract placeholder when tbl_timesheet does not exist or lacks a usable PK.
        
        Marked abstract so SQLAlchemy does not try to map a non-existent or
        unusable table and the application can still start cleanly.
        """
        
        __abstract__ = True
