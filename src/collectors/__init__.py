"""
Collectors that push to the same Aggregator API (one database).
- PC Data Collector: existing (cron POST /snapshots or collector_agent).
- 3rd Party: YouTube stream count → POST /orm/upload_snapshot (device_id=youtube-vroom-vroom).
- Mobile: uses src.mobile_collector + mobile_snapshot_bridge → POST /orm/upload_snapshot (device_id=mobile:location_id).
"""
from ._upload import upload_snapshot
from .mobile_upload import collect_and_upload as mobile_collect_and_upload
from .third_party_collector import collect_and_upload as third_party_collect_and_upload

__all__ = [
    "upload_snapshot",
    "third_party_collect_and_upload",
    "mobile_collect_and_upload",
]
