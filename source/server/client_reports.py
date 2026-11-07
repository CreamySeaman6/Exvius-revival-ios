"""Ask the game to upload its own error log, and keep what it sends.

The client keeps a report log (`Reports`, the "REPORTSMODULE"): among other things, a failed table load
writes `Error loading MST INFO=<details>` to it (LoginScene::procStateMstLoadWait and
procStateTextMstLoadWait). The live servers could ask for that log with a "report back" group in any
reply; the client's report scheduler (`Reports::update`) then uploads it with `sgStoreLogReportRequest`
and waits for a "report state" group in the answer. Read from the Android 9.0 library:

  report back   group 383e98ad (sgReportBackResponse)
                  86f76840  send-after time, "%Y-%m-%d %H:%M:%S" UTC (CommonUtils::convertToTime);
                            "0" means "no request"
                  da99ba05  hold flag; "0" lets the upload go ahead
  store log     request sgStoreLogReportRequest, /actionSymbol/6611dc2f.php, key af7a56a0
  report state  group cd87bd8b (sgReportStateResponse), 950510b8 = 0 for success

This matters for a stock client such as the iPhone app, whose own system log is redacted: its reports
are the only place the client says what went wrong. Turned on with EXVIUS_CLIENT_REPORTS=1; each upload
is saved under <server data>/client-reports/.
"""
from __future__ import annotations

import json
import os
import time

REPORT_BACK_GROUP = "383e98ad"
REPORT_BACK_TIME = "86f76840"
REPORT_BACK_HOLD = "da99ba05"
REPORT_STATE_GROUP = "cd87bd8b"
REPORT_STATE_VALUE = "950510b8"
STORE_LOG_REQUEST = "6611dc2f"
# Replies that carry the request: the first call of every launch, and the last one before the table load.
CARRIERS = {"OTX6Fmvu",   # GameSettingRequest
            "Daud71Hn"}   # RoutineHomeUpdateRequest


def enabled() -> bool:
    return os.environ.get("EXVIUS_CLIENT_REPORTS") == "1"


def _folder() -> str:
    import data_paths
    base = os.environ.get("FFBE_DATA") or getattr(data_paths, "DATA_ROOT", None) or "."
    folder = os.path.join(base, "client-reports")
    os.makedirs(folder, exist_ok=True)
    return folder


def _save(plaintext) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_folder(), f"{stamp}-{int(time.time() * 1000) % 1000:03d}.txt")
    text = plaintext if isinstance(plaintext, str) else repr(plaintext)
    # The log itself is usually one string field inside the request; unwrap it so the file is readable.
    pretty = text
    try:
        body = json.JSONDecoder().raw_decode(text)[0]
        pieces = []
        for group, rows in body.items():
            for row in rows if isinstance(rows, list) else [rows]:
                if isinstance(row, dict):
                    for key, value in row.items():
                        pieces.append(f"[{group}.{key}]\n{value}")
        if pieces:
            pretty = "\n\n".join(pieces)
    except (ValueError, AttributeError):
        pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(pretty)
        fh.write("\n\n----- raw request -----\n")
        fh.write(text)
    return path


def handle(spec, reply_id, plaintext):
    """Add the report-back request to carrier replies, and answer and save a log upload."""
    if not enabled():
        return spec
    if reply_id == STORE_LOG_REQUEST:
        path = _save(plaintext or "")
        size = len(plaintext or "")
        print(f"CLIENT REPORT: game uploaded its log ({size} chars) -> {path}", flush=True)
        return {REPORT_STATE_GROUP: [{REPORT_STATE_VALUE: "0"}]}
    if reply_id in CARRIERS and isinstance(spec, dict):
        spec = dict(spec)
        # A time in the past: upload as soon as the report scheduler next runs.
        spec[REPORT_BACK_GROUP] = [{REPORT_BACK_TIME: "2020-01-01 00:00:00", REPORT_BACK_HOLD: "0"}]
    return spec
