"""
Shared seed data for the database. Used by both the raw SQL layer (database.py)
and the ORM layer (orm_models.py) so metric types stay in sync.
"""
# Metric types seeded at init: (name, unit).
# Add or edit here; init will INSERT new names and UPDATE units for existing ones.
# PC: Running Threads, RAM Usage, Disk Usage. YouTube: total_streams.
# Mobile: Cold Water Shock Risk, Alert Count, Water Temp.
SEED_METRIC_TYPES = [
    ("total_streams", "count"),
    ("Running Threads", "count"),
    ("RAM Usage", "%"),
    ("Disk Usage", "%"),
    ("Cold Water Shock Risk", "%"),
    ("Alert Count", "count"),
    ("Water Temp", "°C"),
]

# Swim spot locations for the map. Read from here for map markers; metrics come from Postgres.
# (id, name, county, lat, lng)
SEED_LOCATIONS = [
    ("loc_lough_dan", "Lough Dan", "Wicklow", 53.075436, -6.285918),
    ("loc_lough_derg", "Lough Derg", "Tipperary", 52.983, -8.317),
    ("loc_lough_key", "Lough Key", "Roscommon", 54.0, -8.25),
    ("loc_lough_ree", "Lough Ree", "Longford", 53.5, -7.9667),
    ("loc_lough_tay", "Lough Tay", "Wicklow", 53.106014, -6.266763),
]
