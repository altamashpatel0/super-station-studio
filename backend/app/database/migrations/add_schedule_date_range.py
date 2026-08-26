from __future__ import annotations

from sqlalchemy import inspect, text


def upgrade_schedule_date_range(engine) -> None:
    """Add optional start/end calendar dates to the schedules table."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "schedules" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("schedules")}
    with engine.begin() as conn:
        if "start_date" not in columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN start_date VARCHAR(10)"))
        if "end_date" not in columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN end_date VARCHAR(10)"))
