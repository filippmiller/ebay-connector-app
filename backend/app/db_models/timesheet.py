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
    from sqlalchemy.orm import synonym
    
    class Timesheet(Base):
        """Legacy timesheet table mapped to tbl_timesheet in Supabase.
        
        This table contains 6000+ existing timesheet records. The schema is
        auto-discovered via reflection to ensure perfect compatibility with
        the actual database structure.
        
        Column naming is mixed: PascalCase (DeleteFlag, StartTime, UserName, etc.)
        and snake_case (record_created_by, record_updated_at, record_updated_by).
        """
        
        __table__ = tbl_timesheet_table
        __mapper_args__ = {
            "primary_key": tuple(tbl_timesheet_table.c[col] for col in pk_cols),
        }
        
        # Create synonyms for columns that need snake_case Python access
        # Only create synonyms for PascalCase columns, not already snake_case ones
        if "ID" in tbl_timesheet_table.c:
            id = synonym("ID")
        if "UserName" in tbl_timesheet_table.c:
            # Map user_id to UserName for backward compat with router code
            user_id = synonym("UserName")
            # Also provide username as direct access
            username = synonym("UserName")
        if "StartTime" in tbl_timesheet_table.c:
            start_time = synonym("StartTime")
        if "EndTime" in tbl_timesheet_table.c:
            end_time = synonym("EndTime")
        if "DurationMinutes" in tbl_timesheet_table.c:
            duration_minutes = synonym("DurationMinutes")
        if "Rate" in tbl_timesheet_table.c:
            rate = synonym("Rate")
        if "Description" in tbl_timesheet_table.c:
            description = synonym("Description")
        if "DeleteFlag" in tbl_timesheet_table.c:
            delete_flag = synonym("DeleteFlag")
        # These are already snake_case in the DB, no synonym needed
        # record_created_by, record_updated_at, record_updated_by
        
        # For backward compat, map old column names to actual DB columns
        if "record_created_at" in tbl_timesheet_table.c:
            record_created = synonym("record_created_at")
        if "RecordCreated" in tbl_timesheet_table.c:
            record_created = synonym("RecordCreated")
        if "record_updated_at" in tbl_timesheet_table.c:
            record_updated = synonym("record_updated_at")
        if "RecordUpdated" in tbl_timesheet_table.c:
            record_updated = synonym("RecordUpdated")
        
        # LegacyID mapping if it exists
        if "LegacyID" in tbl_timesheet_table.c:
            legacy_id = synonym("LegacyID")
else:
    class Timesheet(Base):
        """Abstract placeholder when tbl_timesheet does not exist or lacks a usable PK.
        
        Marked abstract so SQLAlchemy does not try to map a non-existent or
        unusable table and the application can still start cleanly.
        """
        
        __abstract__ = True
