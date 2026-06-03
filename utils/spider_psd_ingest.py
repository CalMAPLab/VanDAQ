#!/usr/bin/env python3
"""
Ingest ADI SpiderMAGIC inversion export files (.txt) into VanDAQ via /dev-measurements.

WinSCP drops files under data/spider_psd/incoming/. Each file may contain multiple
scans (one CSV row per scan). Re-uploads of the same path are deduped using a state
file keyed by path, mtime, and size.

Run continuously:
  python3 utils/spider_psd_ingest.py

One pass (cron):
  python3 utils/spider_psd_ingest.py --once
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from ipcqueue import posixmq
except ImportError:
    posixmq = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INCOMING = ROOT / "data" / "spider_psd" / "incoming"
DEFAULT_PROCESSED = ROOT / "data" / "spider_psd" / "processed"
DEFAULT_FAILED = ROOT / "data" / "spider_psd" / "failed"
DEFAULT_STATE = ROOT / "data" / "spider_psd" / "ingest_state.json"
DEFAULT_LOG = ROOT / "data" / "spider_psd" / "log" / "spider_psd_ingest.log"
QUEUE_NAME = "/dev-measurements"
QUEUE_MAX_MSG_SIZE = 8000
QUEUE_MAX_MSGS = 50
QUEUE_CHUNK = 40

PLATFORM = "van1"
INSTRUMENT = "ADI_Spider_MAGIC_PSD"
UNIT = "1/cm3"
ACQ_TYPE = "measurement_calibrated"
POLL_SECS = 10
STABLE_SECS = 90
DEFAULT_MAX_AGE_MINUTES = 5
# ADI export "Start datetime (PC)" is local PC clock, not UTC
DEFAULT_SAMPLE_TIMEZONE = "America/Los_Angeles"


def setup_logging(verbose: bool, log_file: Path | None = None) -> logging.Logger:
    log = logging.getLogger("spider_psd_ingest")
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(fmt)
        log.addHandler(handler)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)
    return log


def param_name(dp_nm: float) -> str:
    label = f"{dp_nm:.2f}".replace(".", "p")
    return f"dN_{label}_nm"


def dp_from_param(parameter: str) -> float | None:
    if not parameter.startswith("dN_") or not parameter.endswith("_nm"):
        return None
    core = parameter[3:-3].replace("p", ".")
    try:
        return float(core)
    except ValueError:
        return None


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"files": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp.replace(path)


def path_state_key(path: Path) -> str:
    return str(path.resolve())


def parse_sample_time_pc(value: str, tz: ZoneInfo) -> datetime:
    naive = datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S")
    return naive.replace(tzinfo=tz)


def sample_time_utc_naive(dt_aware: datetime) -> datetime:
    return dt_aware.astimezone(timezone.utc).replace(tzinfo=None)


def scan_within_max_age(scan: dict, max_age_minutes: int) -> bool:
    if max_age_minutes <= 0:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    return scan["sample_time_utc"] >= cutoff


# ADI export columns before the Dp (nm) bin block (header label must match file exactly).
META_COLUMN_SPECS = [
    ("Start datetime (BRD)", "start_datetime_brd", "", "inst_datetime", "string"),
    ("N tot (1/cm^3)", "N_tot", "#/cm3", "measurement_calibrated", "float"),
    ("dg (nm)", "dg_nm", "nm", "engineering", "float"),
    ("sg", "sg", "", "engineering", "float"),
    ("T (deg C)", "T_inlet", "deg_c", "engineering", "float"),
    ("P (mbar)", "P_mbar", "mbar", "engineering", "float"),
    ("RH (%)", "RH", "%_rh", "engineering", "float"),
    ("Dew point (deg C)", "DewPoint", "deg_c", "engineering", "float"),
    ("Qsh (ccm)", "Qsh", "ccm", "engineering", "float"),
    ("Qa (ccm)", "Qa", "ccm", "engineering", "float"),
    ("Qcpc (ccm)", "Qcpc", "ccm", "engineering", "float"),
    ("Gas", "Gas", "", "engineering", "string"),
    ("Impactor", "Impactor", "", "engineering", "string"),
    ("Charger", "Charger", "", "engineering", "string"),
    ("Z+/Z- ion mobility ratio", "Z_ion_mobility_ratio", "", "engineering", "float"),
    ("Multiple charge correction", "MC_charge_corr", "", "engineering", "bool"),
    ("Diffusion losses correction", "Diffusion_corr", "", "engineering", "bool"),
    ("Smoothing window (%)", "Smoothing_pct", "%", "engineering", "float"),
    ("Mode", "Mode", "", "engineering", "string"),
    ("V1 (V)", "V1", "V", "engineering", "float"),
    ("V2 (V)", "V2", "V", "engineering", "float"),
    ("tau (s)", "tau", "s", "engineering", "float"),
    ("Tcon (deg C)", "Tcon", "deg_c", "engineering", "float"),
    ("Tini (deg C)", "Init_T", "deg_c", "engineering", "float"),
    ("Tmod (deg C)", "Mod_T", "deg_c", "engineering", "float"),
    ("Topt (deg C)", "Opt_T", "deg_c", "engineering", "float"),
    ("Thsk (deg C)", "HeatSink_T", "deg_c", "engineering", "float"),
    ("Tcab (deg C)", "Case_T", "deg_c", "engineering", "float"),
    ("Pulse height (mV)", "Pulse_height", "mV", "engineering", "float"),
    ("Wick sensor (%)", "Wick", "%", "engineering", "float"),
    ("Status", "Status", "", "engineering", "string"),
    ("Flags", "Flags", "", "engineering", "string"),
    ("S/N", "SerNum", "", "engineering", "string"),
    ("dlog10Dp", "dlog10Dp", "", "engineering", "float"),
]


def _parse_meta_field(raw: str, kind: str):
    if kind == "float":
        return {"value": float(raw)}
    if kind == "bool":
        return {"value": 1.0 if raw.lower() in ("true", "1", "yes") else 0.0}
    if kind == "string":
        return {"value": 0.0, "string": raw[:100]}
    raise ValueError(f"unknown meta kind {kind}")


def extract_scan_meta(row: list[str], header: list[str], dp_idx: int) -> dict:
    """Per-scan engineering/metadata from ADI export columns (pre-PSD bins)."""
    meta_fields = {}
    for label, param, unit, acq_type, kind in META_COLUMN_SPECS:
        try:
            idx = header.index(label)
        except ValueError:
            continue
        if idx >= dp_idx or idx >= len(row):
            continue
        raw = row[idx].strip()
        if not raw:
            continue
        try:
            parsed = _parse_meta_field(raw, kind)
        except ValueError:
            continue
        meta_fields[param] = {
            "unit": unit,
            "acquisition_type": acq_type,
            **parsed,
        }
    return meta_fields


def parse_adi_export(path: Path, sample_tz: ZoneInfo) -> tuple[list[dict], list[float]]:
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return [], []

    header = [c.strip() for c in rows[0]]
    try:
        dp_idx = header.index("Dp (nm)") + 1
    except ValueError as exc:
        raise ValueError(f"{path.name}: missing 'Dp (nm)' column") from exc

    diameters: list[float] = []
    for col in header[dp_idx:]:
        col = col.strip()
        if not col:
            break
        try:
            diameters.append(float(col))
        except ValueError:
            break
    if not diameters:
        raise ValueError(f"{path.name}: no diameter bins in header")

    scans = []
    for row in rows[1:]:
        if len(row) < dp_idx + len(diameters):
            continue
        scan_id = row[0].strip()
        if not scan_id.startswith("q"):
            continue
        try:
            sample_time_pc = parse_sample_time_pc(row[1], sample_tz)
            sample_time_utc = sample_time_pc.astimezone(timezone.utc)
        except ValueError:
            continue
        values = []
        for j in range(len(diameters)):
            raw = row[dp_idx + j].strip()
            try:
                values.append(float(raw))
            except ValueError:
                values.append(float("nan"))
        scans.append(
            {
                "scan_id": scan_id,
                "sample_time": sample_time_utc_naive(sample_time_utc),
                "sample_time_utc": sample_time_utc,
                "diameters": diameters,
                "values": values,
                "meta_fields": extract_scan_meta(row, header, dp_idx),
            }
        )
    return scans, diameters


def make_records(scan: dict) -> list[dict]:
    acq_time = datetime.now().replace(microsecond=0)
    records = []
    for dp, val in zip(scan["diameters"], scan["values"]):
        if val != val:
            continue
        records.append(
            {
                "platform": PLATFORM,
                "instrument": INSTRUMENT,
                "parameter": param_name(dp),
                "unit": UNIT,
                "acquisition_type": ACQ_TYPE,
                "acquisition_time": acq_time,
                "sample_time": scan["sample_time"],
                "value": val,
            }
        )
    for param, field in scan.get("meta_fields", {}).items():
        rec = {
            "platform": PLATFORM,
            "instrument": INSTRUMENT,
            "parameter": param,
            "unit": field["unit"],
            "acquisition_type": field["acquisition_type"],
            "acquisition_time": acq_time,
            "sample_time": scan["sample_time"],
            "value": field["value"],
        }
        if "string" in field:
            rec["string"] = field["string"]
        records.append(rec)
    records.append(
        {
            "platform": PLATFORM,
            "instrument": INSTRUMENT,
            "parameter": "scan_id",
            "unit": "",
            "acquisition_type": ACQ_TYPE,
            "acquisition_time": acq_time,
            "sample_time": scan["sample_time"],
            "value": 0.0,
            "string": scan["scan_id"],
        }
    )
    return records


def open_queue(log: logging.Logger):
    if posixmq is None:
        raise RuntimeError("ipcqueue.posixmq is not installed")
    try:
        return posixmq.Queue(QUEUE_NAME)
    except (OSError, posixmq.QueueError):
        return posixmq.Queue(QUEUE_NAME, maxsize=QUEUE_MAX_MSGS, maxmsgsize=QUEUE_MAX_MSG_SIZE)


def enqueue_records(queue, records: list[dict], log: logging.Logger) -> None:
    for i in range(0, len(records), QUEUE_CHUNK):
        chunk = records[i : i + QUEUE_CHUNK]
        queue.put(chunk)


def process_file(
    path: Path,
    state: dict,
    queue,
    log: logging.Logger,
    processed_dir: Path,
    failed_dir: Path,
    move_when_done: bool,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    sample_tz: ZoneInfo | None = None,
) -> int:
    if sample_tz is None:
        sample_tz = ZoneInfo(DEFAULT_SAMPLE_TIMEZONE)
    st = path.stat()
    pk = path_state_key(path)
    files = state.setdefault("files", {})
    entry = files.get(pk, {})
    imported = entry.get("scans_imported", 0)
    if st.st_size < entry.get("last_size", 0):
        imported = 0

    try:
        scans, _ = parse_adi_export(path, sample_tz)
    except Exception as exc:
        log.error("Failed to parse %s: %s", path, exc)
        failed_dir.mkdir(parents=True, exist_ok=True)
        dest = failed_dir / path.name
        if path.exists() and not dest.exists():
            shutil.move(str(path), str(dest))
        files.pop(pk, None)
        return 0

    new_scans = scans[imported:]
    new_scans = [s for s in new_scans if scan_within_max_age(s, max_age_minutes)]
    if not new_scans:
        return 0

    total = 0
    for scan in new_scans:
        records = make_records(scan)
        if records:
            enqueue_records(queue, records, log)
            total += 1
            log.info(
                "Ingested %s scan %s @ %s (%d bins)",
                path.name,
                scan["scan_id"],
                scan["sample_time"],
                len(scan["diameters"]),
            )

    files[pk] = {
        "scans_imported": len(scans),
        "last_size": st.st_size,
        "last_import": datetime.now(timezone.utc).isoformat(),
    }

    age = time.time() - st.st_mtime
    if move_when_done and imported + len(new_scans) >= len(scans) and age >= STABLE_SECS:
        processed_dir.mkdir(parents=True, exist_ok=True)
        dest = processed_dir / path.name
        if dest.exists():
            dest.unlink()
        shutil.move(str(path), str(dest))
        files.pop(pk, None)
        log.info("Archived %s -> %s", path.name, dest)

    return total


def ingest_pass(
    incoming: Path,
    processed: Path,
    failed: Path,
    state_path: Path,
    log: logging.Logger,
    move_when_done: bool,
    max_files: int = 5,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    sample_timezone: str = DEFAULT_SAMPLE_TIMEZONE,
) -> int:
    incoming.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path)
    queue = open_queue(log)
    sample_tz = ZoneInfo(sample_timezone)
    count = 0
    paths = sorted(incoming.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if max_files > 0:
        paths = paths[:max_files]
    for path in paths:
        if not path.is_file():
            continue
        count += process_file(
            path, state, queue, log, processed, failed, move_when_done,
            max_age_minutes, sample_tz,
        )
    save_state(state_path, state)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest ADI SpiderMAGIC PSD export files")
    parser.add_argument("--incoming", type=Path, default=DEFAULT_INCOMING)
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--failed", type=Path, default=DEFAULT_FAILED)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--once", action="store_true", help="Single pass then exit")
    parser.add_argument("--no-move", action="store_true", help="Never move files to processed/")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--poll", type=float, default=POLL_SECS)
    parser.add_argument(
        "--max-files",
        type=int,
        default=5,
        help="Max .txt files to process per pass (default 5; use 0 for no limit)",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=DEFAULT_MAX_AGE_MINUTES,
        help="Only ingest scans this recent (default 5; use 0 for no limit)",
    )
    parser.add_argument(
        "--sample-timezone",
        default=DEFAULT_SAMPLE_TIMEZONE,
        help="IANA zone for ADI 'Start datetime (PC)' (default America/Los_Angeles)",
    )
    args = parser.parse_args()

    log = setup_logging(args.verbose, args.log_file)
    move_when_done = not args.no_move

    if args.once:
        n = ingest_pass(
            args.incoming, args.processed, args.failed, args.state, log, move_when_done,
            max_files=args.max_files, max_age_minutes=args.max_age_minutes,
            sample_timezone=args.sample_timezone,
        )
        log.info("Done (%d new scans)", n)
        return 0

    log.info(
        "Watching %s (instrument=%s, poll=%ss)",
        args.incoming,
        INSTRUMENT,
        args.poll,
    )
    while True:
        try:
            ingest_pass(
                args.incoming, args.processed, args.failed, args.state, log, move_when_done,
                max_files=args.max_files, max_age_minutes=args.max_age_minutes,
                sample_timezone=args.sample_timezone,
            )
        except Exception as exc:
            log.exception("Ingest pass failed: %s", exc)
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
