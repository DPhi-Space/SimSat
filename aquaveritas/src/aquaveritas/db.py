"""PostgreSQL + PostGIS database layer."""

import json
import os
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://aqua:<redacted>@localhost:5433/aquaveritas",
)

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS locations (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    lon                  DOUBLE PRECISION NOT NULL,
    lat                  DOUBLE PRECISION NOT NULL,
    geom                 GEOMETRY(POINT, 4326)
                         GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED,
    water_boundary       GEOMETRY(POLYGON, 4326),
    agri_buffer          GEOMETRY(POLYGON, 4326),
    description          TEXT,
    expected_water_status TEXT,
    category             TEXT,
    baseline_date        DATE
);

CREATE INDEX IF NOT EXISTS idx_locations_geom
    ON locations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_locations_water_boundary
    ON locations USING GIST (water_boundary)
    WHERE water_boundary IS NOT NULL;

CREATE TABLE IF NOT EXISTS observations (
    id                          SERIAL PRIMARY KEY,
    location_id                 TEXT NOT NULL REFERENCES locations(id),
    observed_at                 TIMESTAMPTZ NOT NULL,

    -- Satellite position (mandatory decimal degrees)
    sat_lon                     DOUBLE PRECISION NOT NULL,
    sat_lat                     DOUBLE PRECISION NOT NULL,
    sat_alt_km                  DOUBLE PRECISION NOT NULL,
    sat_geom                    GEOMETRY(POINT, 4326)
                                GENERATED ALWAYS AS (
                                    ST_SetSRID(ST_MakePoint(sat_lon, sat_lat), 4326)
                                ) STORED,

    -- Tile footprints from Sentinel metadata
    core_footprint              GEOMETRY(POLYGON, 4326),
    buffer_footprint            GEOMETRY(POLYGON, 4326),

    -- Water body fields (core zone, nullable until labeled)
    water_extent_status         TEXT,
    flood_risk                  TEXT,
    water_clarity               TEXT,
    shoreline_encroachment      BOOLEAN,

    -- Agricultural fields (buffer zone, nullable until labeled)
    agriculture_present         BOOLEAN,
    crop_stress_level           TEXT,
    crop_stress_type            TEXT,
    cultivation_expanding       BOOLEAN,
    settlement_visible          BOOLEAN,
    bare_soil_expansion         BOOLEAN,

    -- Quality flag (set during collection if image unavailable)
    image_quality_limited       BOOLEAN,

    -- Raw model outputs (stored for re-parsing if schema evolves)
    model_output_core           JSONB,
    model_output_buffer         JSONB,

    -- Image paths on disk
    rgb_core_path               TEXT,
    swir_core_path              TEXT,
    rgb_buffer_path             TEXT,
    swir_buffer_path            TEXT,

    created_at                  TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (location_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_obs_location_time
    ON observations (location_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_sat_geom
    ON observations USING GIST (sat_geom);
CREATE INDEX IF NOT EXISTS idx_obs_core_footprint
    ON observations USING GIST (core_footprint)
    WHERE core_footprint IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_obs_unlabeled
    ON observations (location_id)
    WHERE water_extent_status IS NULL;
"""

# ── Connection ─────────────────────────────────────────────────────────────────

class Database:
    def __init__(self, url: str = DATABASE_URL):
        self.url = url

    @contextmanager
    def connect(self):
        conn = psycopg2.connect(self.url)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def init_schema(self):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)

    def seed_locations(self, locations):
        """Insert Location objects; skip existing."""
        sql = """
        INSERT INTO locations
            (id, name, lon, lat, description, expected_water_status, category,
             baseline_date, agri_buffer)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s,
             ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 10000)::geometry)
        ON CONFLICT (id) DO NOTHING
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                for loc in locations:
                    cur.execute(sql, (
                        loc.id, loc.name, loc.lon, loc.lat,
                        loc.description, loc.expected_water_status,
                        loc.category, loc.baseline_date,
                        loc.lon, loc.lat,   # for ST_MakePoint inside ST_Buffer
                    ))

    # ── Polling trigger ────────────────────────────────────────────────────────

    def get_trigger_locations(self, sat_lon: float, sat_lat: float) -> list[dict]:
        """
        Return locations within 50km of the satellite that have not been
        observed in the past 24 hours.
        """
        sql = """
        SELECT l.id, l.name, l.lon, l.lat
        FROM   locations l
        LEFT JOIN observations o
               ON  o.location_id = l.id
               AND o.observed_at > NOW() - INTERVAL '24 hours'
        WHERE  ST_DWithin(
                   l.geom::geography,
                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                   50000
               )
        AND    o.id IS NULL
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, (sat_lon, sat_lat))
                return [dict(row) for row in cur.fetchall()]

    # ── Observations ───────────────────────────────────────────────────────────

    def observation_exists(self, location_id: str, observed_at: str) -> bool:
        sql = "SELECT 1 FROM observations WHERE location_id=%s AND observed_at=%s"
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (location_id, observed_at))
                return cur.fetchone() is not None

    def insert_observation(
        self,
        location_id:        str,
        observed_at:        str,
        sat_lon:            float,
        sat_lat:            float,
        sat_alt_km:         float,
        core_footprint:     Optional[list],     # [lon_min, lat_min, lon_max, lat_max]
        buffer_footprint:   Optional[list],
        image_quality_limited: bool,
        rgb_core_path:      Optional[str] = None,
        swir_core_path:     Optional[str] = None,
        rgb_buffer_path:    Optional[str] = None,
        swir_buffer_path:   Optional[str] = None,
    ) -> int:
        """Insert a new observation (unlabeled). Returns the new row id."""
        core_env   = _make_envelope(core_footprint)
        buffer_env = _make_envelope(buffer_footprint)

        sql = f"""
        INSERT INTO observations (
            location_id, observed_at,
            sat_lon, sat_lat, sat_alt_km,
            core_footprint, buffer_footprint,
            image_quality_limited,
            rgb_core_path, swir_core_path, rgb_buffer_path, swir_buffer_path
        ) VALUES (
            %s, %s, %s, %s, %s,
            {core_env}, {buffer_env},
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (location_id, observed_at) DO NOTHING
        RETURNING id
        """
        params = _envelope_params(
            [location_id, observed_at, sat_lon, sat_lat, sat_alt_km],
            core_footprint,
            buffer_footprint,
            [image_quality_limited, rgb_core_path, swir_core_path,
             rgb_buffer_path, swir_buffer_path],
        )
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else -1

    def apply_labels(
        self,
        observation_id:      int,
        core_output:         Optional[dict],
        buffer_output:       Optional[dict],
    ):
        """Write label fields from model/oracle output onto an existing observation."""
        if core_output is None and buffer_output is None:
            return

        sets, params = [], []

        if core_output:
            sets  += ["water_extent_status=%s", "flood_risk=%s",
                      "water_clarity=%s", "shoreline_encroachment=%s",
                      "model_output_core=%s"]
            params += [
                core_output.get("water_extent_status"),
                core_output.get("flood_risk"),
                core_output.get("water_clarity"),
                core_output.get("shoreline_encroachment"),
                json.dumps(core_output),
            ]

        if buffer_output:
            sets  += ["agriculture_present=%s", "crop_stress_level=%s",
                      "crop_stress_type=%s", "cultivation_expanding=%s",
                      "settlement_visible=%s", "bare_soil_expansion=%s",
                      "model_output_buffer=%s"]
            params += [
                buffer_output.get("agriculture_present"),
                buffer_output.get("crop_stress_level"),
                buffer_output.get("crop_stress_type"),
                buffer_output.get("cultivation_expanding_toward_water"),
                buffer_output.get("settlement_visible"),
                buffer_output.get("bare_soil_expansion"),
                json.dumps(buffer_output),
            ]

        params.append(observation_id)
        sql = f"UPDATE observations SET {', '.join(sets)} WHERE id=%s"
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def get_unlabeled(self, limit: int = 100) -> list[dict]:
        """Return observations where core labels are missing."""
        sql = """
        SELECT o.id, o.location_id, o.observed_at,
               o.rgb_core_path, o.swir_core_path,
               o.rgb_buffer_path, o.swir_buffer_path,
               o.image_quality_limited
        FROM   observations o
        WHERE  o.water_extent_status IS NULL
          AND  o.image_quality_limited IS NOT TRUE
        ORDER  BY o.observed_at
        LIMIT  %s
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, (limit,))
                return [dict(r) for r in cur.fetchall()]

    def get_labeled(self, split: str = "train") -> list[dict]:
        """
        Return fully labeled observations for dataset export.
        split='train'  → before 2024-01-01
        split='test'   → 2024-01-01 onwards
        """
        cutoff = "2024-01-01"
        op     = "<" if split == "train" else ">="
        sql    = f"""
        SELECT o.*, l.name AS location_name, l.category
        FROM   observations o
        JOIN   locations l ON l.id = o.location_id
        WHERE  o.water_extent_status IS NOT NULL
          AND  o.observed_at {op} %s
        ORDER  BY o.location_id, o.observed_at
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, (cutoff,))
                return [dict(r) for r in cur.fetchall()]

    def get_observations_for_dashboard(
        self,
        location_id: Optional[str] = None,
    ) -> list[dict]:
        """Return observations for Streamlit dashboard queries."""
        where = "WHERE o.water_extent_status IS NOT NULL"
        params = []
        if location_id:
            where += " AND o.location_id = %s"
            params.append(location_id)
        sql = f"""
        SELECT o.location_id, l.name AS location_name, l.lon, l.lat, l.category,
               o.observed_at, o.water_extent_status, o.flood_risk,
               o.water_clarity, o.shoreline_encroachment,
               o.agriculture_present, o.crop_stress_level, o.crop_stress_type,
               o.cultivation_expanding, o.settlement_visible, o.bare_soil_expansion,
               o.image_quality_limited,
               o.rgb_core_path, o.swir_core_path
        FROM   observations o
        JOIN   locations l ON l.id = o.location_id
        {where}
        ORDER  BY o.location_id, o.observed_at
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    def get_latest_per_location(self) -> list[dict]:
        """Most recent labeled observation per location — used for map view."""
        sql = """
        SELECT DISTINCT ON (o.location_id)
               o.location_id, l.name, l.lon, l.lat, l.category,
               o.observed_at, o.water_extent_status, o.flood_risk,
               o.crop_stress_level
        FROM   observations o
        JOIN   locations l ON l.id = o.location_id
        WHERE  o.water_extent_status IS NOT NULL
        ORDER  BY o.location_id, o.observed_at DESC
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_envelope(footprint: Optional[list]) -> str:
    """Return SQL fragment for footprint or NULL."""
    if footprint:
        return "ST_MakeEnvelope(%s, %s, %s, %s, 4326)"
    return "NULL"


def _envelope_params(prefix: list, core_fp, buffer_fp, suffix: list) -> list:
    params = list(prefix)
    if core_fp:
        params.extend(core_fp)
    if buffer_fp:
        params.extend(buffer_fp)
    params.extend(suffix)
    return params
