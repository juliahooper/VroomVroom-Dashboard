"""
Mobile data collector: reads metrics from Firestore using config-driven collection
and field mappings. New services, devices, and metrics can be added via config
without code changes.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .configlib import MobileConfig
from .mobile_models import CountResult, LocationSummary, TimeSeriesPoint

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Logical key in mobile.collections for the locations list (document ids and fields: name, county)
LOCATIONS_COLLECTION_KEY = "locations"


def _get_firestore():
    """Lazy Firestore client. Returns None if Firebase is not configured or init fails."""
    try:
        import firebase_admin
        from firebase_admin import firestore
    except ImportError:
        logger.warning("firebase-admin not installed; mobile metrics disabled.")
        return None
    if not firebase_admin._apps:
        return None
    return firestore.client()


def init_firebase(mobile_config: MobileConfig | None) -> bool:
    """
    Initialise Firebase app if mobile config is present and credentials are available.
    Call once at app startup. Returns True if initialised, False otherwise.
    """
    if mobile_config is None or not mobile_config.enabled:
        return False
    try:
        import os
        from firebase_admin import credentials
        import firebase_admin
    except ImportError:
        logger.warning("firebase-admin not installed; mobile metrics disabled.")
        return False
    if firebase_admin._apps:
        return True
    creds_path = mobile_config.firebase_credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        logger.warning("Mobile enabled but no firebase_credentials_path or GOOGLE_APPLICATION_CREDENTIALS.")
        return False
    try:
        cred = credentials.Certificate(creds_path)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        logger.warning("Firebase init failed: %s", e)
        return False
    return True


def _timestamp_to_millis(t) -> int:
    """Convert Firestore Timestamp to milliseconds since epoch."""
    if hasattr(t, "timestamp"):
        return int(t.timestamp() * 1000)
    return int(t * 1000) if isinstance(t, (int, float)) else 0


class MobileDataCollector:
    """
    Fetches mobile metrics from Firestore. All collection names and field mappings
    come from MobileConfig; add new time-series or count metrics in config.
    """

    def __init__(self, config: MobileConfig | None) -> None:
        self._config = config
        self._db = None

    def _client(self):
        if self._config is None or not self._config.enabled:
            return None
        if self._db is None:
            self._db = _get_firestore()
        return self._db

    def list_locations(self) -> list[LocationSummary]:
        """List available locations (id = doc.id, name and county from config collection)."""
        db = self._client()
        if db is None:
            return []
        coll_name = self._config.collection_name(LOCATIONS_COLLECTION_KEY) if self._config else None
        if not coll_name:
            logger.warning("mobile.collections has no '%s' entry; cannot list locations.", LOCATIONS_COLLECTION_KEY)
            return []
        try:
            ref = db.collection(coll_name)
            docs = ref.stream()
            out = []
            for doc in docs:
                data = doc.to_dict() or {}
                name = data.get("name") or ""
                county = data.get("county") or ""
                out.append(LocationSummary(id=doc.id, name=name, county=county))
            return out
        except Exception as e:
            logger.exception("Firestore list_locations failed: %s", e)
            raise

    def get_time_series_diagnostic(self, location_id: str) -> dict | None:
        """When no docs returned, call this to get collection name, sample doc keys, location field value for logging."""
        db = self._client()
        if db is None or not self._config or not self._config.time_series_sources:
            return None
        source = self._config.time_series_sources[0]
        coll_name = self._config.collection_name(source.collection_key)
        if not coll_name:
            return None
        try:
            ref = db.collection(coll_name)
            sample = list(ref.limit(1).stream())
            if not sample:
                return {"collection": coll_name, "empty": True}
            data = sample[0].to_dict() or {}
            return {
                "collection": coll_name,
                "query_location_id": location_id,
                "location_field": source.location_field,
                "sample_doc_keys": list(data.keys()),
                "sample_location_value": data.get(source.location_field),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_time_series(
        self,
        location_id: str,
        metric_id: str | None = None,
        limit_override: int | None = None,
        since_timestamp_millis: int | None = None,
        end_timestamp_millis: int | None = None,
    ) -> list[TimeSeriesPoint]:
        """
        Fetch time-series points for a location. If metric_id is given, use that
        time_series_sources entry; otherwise use the first. Value fields come from config.
        limit_override: if set, use instead of source.limit (e.g. for backfill).
        since_timestamp_millis: if set, only return points with timestamp > this (incremental sync).
        end_timestamp_millis: if set, only return points with timestamp <= this (e.g. "current time").
        """
        db = self._client()
        if db is None or not self._config:
            return []
        sources = self._config.time_series_sources
        if not sources:
            return []
        source = next((s for s in sources if s.metric_id == metric_id), sources[0])
        coll_name = self._config.collection_name(source.collection_key)
        if not coll_name:
            logger.warning("Unknown collection_key '%s' for time_series.", source.collection_key)
            return []
        limit = limit_override if limit_override is not None else source.limit
        ref = db.collection(coll_name)

        def _doc_to_point(doc, ts_field, value_fields, end_millis):
            data = doc.to_dict() or {}
            ts = data.get(ts_field)
            millis = _timestamp_to_millis(ts) if ts else 0
            if end_millis is not None and end_millis > 0 and millis > end_millis:
                return None
            values = {}
            for f in value_fields:
                v = data.get(f)
                if v is not None:
                    try:
                        values[f] = float(v)
                    except (TypeError, ValueError):
                        pass
            return TimeSeriesPoint(timestamp_millis=millis, values=values)

        # Try full query (with optional since, order_by) first
        try:
            query = ref.where(source.location_field, "==", location_id)
            if since_timestamp_millis is not None and since_timestamp_millis > 0:
                since_dt = datetime.fromtimestamp(since_timestamp_millis / 1000.0, tz=timezone.utc)
                query = query.where(source.timestamp_field, ">", since_dt)
            query = query.order_by(source.timestamp_field).limit(limit)
            docs = query.stream()
            out = []
            for doc in docs:
                pt = _doc_to_point(doc, source.timestamp_field, source.value_fields, end_timestamp_millis)
                if pt is not None:
                    out.append(pt)
            if out:
                return out
        except Exception as e:
            logger.warning("get_time_series ordered query failed (%s), trying simple query.", e)

        # Fallback: no order_by, no since (no composite index needed). Sort in memory.
        try:
            simple_query = ref.where(source.location_field, "==", location_id).limit(limit)
            docs = simple_query.stream()
            out = []
            for doc in docs:
                pt = _doc_to_point(doc, source.timestamp_field, source.value_fields, end_timestamp_millis)
                if pt is not None:
                    out.append(pt)
            out.sort(key=lambda p: p.timestamp_millis)
            if not out:
                # Diagnostic: fetch one doc with no filter to see actual field names
                try:
                    sample = list(ref.limit(1).stream())
                    if sample:
                        data = sample[0].to_dict() or {}
                        logger.warning(
                            "get_time_series 0 docs: collection=%r, query location_id=%r; sample doc keys=%r, sample %r=%r",
                            coll_name, location_id, list(data.keys()), source.location_field, data.get(source.location_field),
                        )
                    else:
                        logger.warning(
                            "get_time_series 0 docs: collection=%r is empty (no documents at all)",
                            coll_name,
                        )
                except Exception as diag_e:
                    logger.warning("get_time_series diagnostic failed: %s", diag_e)
            return out
        except Exception as e:
            logger.exception("Firestore get_time_series failed: %s", e)
            raise

    def get_count(self, location_id: str, metric_id: str | None = None) -> CountResult | None:
        """
        Count documents for a location (all-time). If metric_id is given, use that
        count_sources entry; otherwise use the first.
        """
        db = self._client()
        if db is None or not self._config:
            return None
        sources = self._config.count_sources
        if not sources:
            return None
        source = next((s for s in sources if s.metric_id == metric_id), sources[0])
        coll_name = self._config.collection_name(source.collection_key)
        if not coll_name:
            logger.warning("Unknown collection_key '%s' for count.", source.collection_key)
            return None
        try:
            ref = db.collection(coll_name)
            query = ref.where(source.location_field, "==", location_id)
            snapshot = query.get()
            count = len(snapshot)
            return CountResult(
                location_id=location_id,
                metric_id=source.metric_id,
                count=count,
                measured_at_millis=int(time.time() * 1000),
            )
        except Exception as e:
            logger.exception("Firestore get_count failed: %s", e)
            raise
