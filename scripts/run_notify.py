"""GitHub Actions notify job에서 호출하는 스크립트.

환경변수:
  SUMMARIZE_STATUS  - summarize job 결과 (success/failure 등)
  COLLECTED_COUNT   - 수집 건수
  DATE_STR          - 날짜 문자열 (YYYYMMDD)
"""

import os
import sys
import json
import glob
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from notifier import notify_all, send_error_alert

date_str = os.getenv("DATE_STR", datetime.now().strftime("%Y%m%d"))
status   = os.getenv("SUMMARIZE_STATUS", "unknown")
collected = int(os.getenv("COLLECTED_COUNT", "0"))

if status != "success":
    send_error_alert(f"요약 Job 실패: {status} ({date_str})")
    print(f"[ERROR] 요약 실패 알림 발송: {status}")
else:
    files   = sorted(glob.glob("output/summary_*.json"))
    results = json.load(open(files[-1], encoding="utf-8")) if files else []
    stats   = {
        "collected":  collected,
        "filtered":   len(results),
        "summarized": sum(1 for r in results if not (r.get("summary") or {}).get("error")),
    }
    notify_all(results, date_str, stats)
    print(f"[OK] 알림 발송 완료: {stats}")
