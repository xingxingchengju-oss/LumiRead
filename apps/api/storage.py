"""SQLite storage shared by the HTTPS server and the vision worker."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def runtime():
    return Path(os.environ.get("LUMIREAD_VAR", ROOT / "var")).resolve()


def connect():
    base = runtime()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(base / "lumiread.sqlite3", timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


@contextmanager
def transaction(write=False):
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def uid():
    return secrets.token_urlsafe(15)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def event(db, sid, kind, payload):
    db.execute(
        "INSERT INTO events(session_id,kind,payload,ts) VALUES(?,?,?,?)",
        (sid, kind, json.dumps(payload, ensure_ascii=False), time.time()),
    )


def initialize():
    from . import clouclip, demo, learning, sensors

    db = connect()
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS learners(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners,
            silent INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(hash TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions,
            role TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions,
            role TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions,
            idem TEXT NOT NULL, sha TEXT NOT NULL, source TEXT NOT NULL, user_agent TEXT NOT NULL,
            phone_confirmed INTEGER NOT NULL, camera_model TEXT, created REAL NOT NULL, UNIQUE(session_id,idem));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, capture_id TEXT NOT NULL UNIQUE REFERENCES captures,
            status TEXT NOT NULL, lease TEXT, lease_until REAL, error TEXT, result TEXT,
            provider TEXT, model TEXT, request_id TEXT, usage TEXT, latency REAL, finished REAL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions, kind TEXT NOT NULL, payload TEXT NOT NULL, ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS event_stream ON events(session_id,seq);
        CREATE TABLE IF NOT EXISTS receipts(job_id TEXT NOT NULL REFERENCES jobs, view_id TEXT NOT NULL,
            seen REAL NOT NULL, PRIMARY KEY(job_id,view_id));
        CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners,
            job_id TEXT NOT NULL REFERENCES jobs, ordinal INTEGER NOT NULL, skill TEXT NOT NULL,
            correct INTEGER NOT NULL, created REAL NOT NULL, UNIQUE(job_id,ordinal));
        """)
        db.executescript(learning.SCHEMA + sensors.SCHEMA + demo.SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if db.execute("PRAGMA user_version").fetchone()[0] < 2:
            for row in db.execute(
                "SELECT id,result FROM jobs WHERE status='completed'"
            ):
                learning.save_questions(db, row["id"], json.loads(row["result"]))
            db.execute("PRAGMA user_version=2")
        if db.execute("PRAGMA user_version").fetchone()[0] < 3:
            if "tap_side" not in {
                r["name"] for r in db.execute("PRAGMA table_info(captures)")
            }:
                db.execute(
                    "ALTER TABLE captures ADD COLUMN tap_side TEXT CHECK(tap_side IN ('left','right'))"
                )
            db.execute("PRAGMA user_version=3")
        db.commit()
    finally:
        db.close()
    clouclip.initialize()
