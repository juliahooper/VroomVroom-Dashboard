"""
Shared seed data for the database. Used by both the raw SQL layer (database.py)
and the ORM layer (orm_models.py) so metric types stay in sync.
"""
# Metric types seeded at init: (name, unit).
# Add or edit here; init will INSERT new names and UPDATE units for existing ones.
SEED_METRIC_TYPES = [
    ("total_streams", "count"),
    ("Running Threads", "count"),
    ("RAM Usage", "%"),
    ("Disk Read Speed", "MB/s"),
]
