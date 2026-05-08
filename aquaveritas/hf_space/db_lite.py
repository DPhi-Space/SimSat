"""
SQLite adapter for AquaVeritas HuggingFace Space.

Provides the same interface as the PostgreSQL Database class
(get_observations_for_dashboard, get_latest_per_location) but reads
from a bundled SQLite file instead of a live PostgreSQL connection.

The SQLite file is created by scripts/export_sqlite.py.
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Default path: data/observations.db relative to this file
DEFAULT_DB = Path(__file__).parent / "data" / "observations.db"


class DatabaseLite:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_observations_for_dashboard(
        self,
        location_id: Optional[str] = None,
    ) -> list[dict]:
        """Return labeled observations for dashboard charts."""
        where = "WHERE o.water_extent_status IS NOT NULL"
        params: list = []
        if location_id:
            where += " AND o.location_id = ?"
            params.append(location_id)

        sql = f"""
        SELECT
            o.location_id,
            l.name        AS location_name,
            l.lon,
            l.lat,
            l.category,
            o.observed_at,
            o.water_extent_status,
            o.flood_risk,
            o.water_clarity,
            o.shoreline_encroachment,
            o.agriculture_present,
            o.crop_stress_level,
            o.crop_stress_type,
            o.cultivation_expanding,
            o.settlement_visible,
            o.bare_soil_expansion,
            o.image_quality_limited,
            o.prose_brief
        FROM   observations o
        JOIN   locations l ON l.id = o.location_id
        {where}
        ORDER  BY o.location_id, o.observed_at
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_latest_per_location(self) -> list[dict]:
        """Most recent labeled observation per location — used for map view."""
        sql = """
        SELECT
            o.location_id,
            l.name AS location_name,
            l.lon,
            l.lat,
            l.category,
            o.observed_at,
            o.water_extent_status,
            o.flood_risk,
            o.crop_stress_level
        FROM observations o
        JOIN locations l ON l.id = o.location_id
        WHERE o.water_extent_status IS NOT NULL
          AND o.observed_at = (
              SELECT MAX(o2.observed_at)
              FROM observations o2
              WHERE o2.location_id = o.location_id
                AND o2.water_extent_status IS NOT NULL
          )
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]
