"""
Run 3rd party (YouTube) and mobile (Firebase) collectors once.
Web app must be running. PC data is handled by cron or collector_agent.
Mobile uses existing src.mobile_collector + mobile_snapshot_bridge.
"""
from __future__ import annotations

import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors import mobile_collect_and_upload, third_party_collect_and_upload

API_URL = os.environ.get("VROOMVROOM_API_URL", "http://127.0.0.1:5000")

if __name__ == "__main__":
    third_party_collect_and_upload(API_URL)
    mobile_collect_and_upload(API_URL)
