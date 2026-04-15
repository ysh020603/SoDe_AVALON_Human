"""
SharedStateManager: SQLite-based shared state for Streamlit <-> Game Engine communication.

Uses WAL mode for concurrent read/write performance across multiple Streamlit sessions
and the game engine background thread.
"""

import sqlite3
import threading
import time
import json
from datetime import datetime
from typing import List, Optional, Dict, Any


class SharedStateManager:
    def __init__(self, db_path: str = "game_shared_state.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS rooms (
                        room_id TEXT PRIMARY KEY,
                        host_session_id TEXT,
                        status TEXT DEFAULT 'waiting',
                        config_json TEXT DEFAULT '{}',
                        seat_mapping_json TEXT DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS players (
                        session_id TEXT PRIMARY KEY,
                        room_id TEXT,
                        nickname TEXT,
                        seat_number INTEGER DEFAULT -1,
                        is_host INTEGER DEFAULT 0,
                        role TEXT DEFAULT '',
                        faction TEXT DEFAULT '',
                        FOREIGN KEY (room_id) REFERENCES rooms(room_id)
                    );

                    CREATE TABLE IF NOT EXISTS pending_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_id TEXT,
                        seat_number INTEGER,
                        phase TEXT,
                        prompt_text TEXT,
                        context_json TEXT DEFAULT '{}',
                        status TEXT DEFAULT 'WAITING',
                        response_json TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (room_id) REFERENCES rooms(room_id)
                    );

                    CREATE TABLE IF NOT EXISTS game_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_id TEXT,
                        seat_number INTEGER,
                        event_type TEXT,
                        content TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (room_id) REFERENCES rooms(room_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_pending_room_seat
                        ON pending_actions(room_id, seat_number, status);
                    CREATE INDEX IF NOT EXISTS idx_events_room_seat
                        ON game_events(room_id, seat_number);
                """)
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------ #
    #  Room management
    # ------------------------------------------------------------------ #

    def create_room(self, room_id: str, host_session_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO rooms (room_id, host_session_id, status) VALUES (?, ?, 'waiting')",
                    (room_id, host_session_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_room_status(self, room_id: str, status: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("UPDATE rooms SET status = ? WHERE room_id = ?", (status, room_id))
                conn.commit()
            finally:
                conn.close()

    def set_room_config(self, room_id: str, config_json: str, seat_mapping_json: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE rooms SET config_json = ?, seat_mapping_json = ? WHERE room_id = ?",
                    (config_json, seat_mapping_json, room_id),
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------ #
    #  Player management
    # ------------------------------------------------------------------ #

    def register_player(self, room_id: str, session_id: str, nickname: str, is_host: bool = False) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO players (session_id, room_id, nickname, is_host) VALUES (?, ?, ?, ?)",
                    (session_id, room_id, nickname, int(is_host)),
                )
                conn.commit()
            finally:
                conn.close()

    def assign_seat(self, room_id: str, session_id: str, seat_number: int,
                    role: str = "", faction: str = "") -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE players SET seat_number = ?, role = ?, faction = ? WHERE session_id = ? AND room_id = ?",
                    (seat_number, role, faction, session_id, room_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_players(self, room_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM players WHERE room_id = ?", (room_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_player_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM players WHERE session_id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_human_players(self, room_id: str) -> List[Dict[str, Any]]:
        """Return players that are not the host (potential human game players)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM players WHERE room_id = ? AND is_host = 0",
                (room_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Core communication: Engine -> Frontend
    # ------------------------------------------------------------------ #

    def post_pending_action(self, room_id: str, seat_number: int, phase: str,
                            prompt_text: str, context_json: str = "{}") -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """INSERT INTO pending_actions
                       (room_id, seat_number, phase, prompt_text, context_json, status)
                       VALUES (?, ?, ?, ?, ?, 'WAITING')""",
                    (room_id, seat_number, phase, prompt_text, context_json),
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def get_pending_action(self, room_id: str, seat_number: int) -> Optional[Dict[str, Any]]:
        """Get the latest WAITING action for a given seat."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT * FROM pending_actions
                   WHERE room_id = ? AND seat_number = ? AND status = 'WAITING'
                   ORDER BY id DESC LIMIT 1""",
                (room_id, seat_number),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Core communication: Frontend -> Engine
    # ------------------------------------------------------------------ #

    def submit_response(self, action_id: int, response_json: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE pending_actions SET status = 'RESPONDED', response_json = ? WHERE id = ?",
                    (response_json, action_id),
                )
                conn.commit()
            finally:
                conn.close()

    def wait_for_response(self, action_id: int, timeout: float = 300,
                          poll_interval: float = 1.0) -> str:
        """Block until the frontend submits a response for the given action_id."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT status, response_json FROM pending_actions WHERE id = ?",
                    (action_id,),
                ).fetchone()
            finally:
                conn.close()

            if row and row["status"] == "RESPONDED":
                return row["response_json"]

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Timed out waiting for response to action {action_id} after {timeout}s"
        )

    # ------------------------------------------------------------------ #
    #  Game event stream
    # ------------------------------------------------------------------ #

    def push_event(self, room_id: str, seat_number: Optional[int],
                   event_type: str, content: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO game_events (room_id, seat_number, event_type, content)
                       VALUES (?, ?, ?, ?)""",
                    (room_id, seat_number, event_type, content),
                )
                conn.commit()
            finally:
                conn.close()

    def get_events(self, room_id: str, seat_number: int,
                   since_id: int = 0) -> List[Dict[str, Any]]:
        """Get events visible to a player: their own events + broadcast (seat_number IS NULL)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM game_events
                   WHERE room_id = ? AND id > ?
                     AND (seat_number = ? OR seat_number IS NULL)
                   ORDER BY id ASC""",
                (room_id, since_id, seat_number),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Cleanup
    # ------------------------------------------------------------------ #

    def reset_room(self, room_id: str) -> None:
        """Clear all game data for a room (for restarting)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM pending_actions WHERE room_id = ?", (room_id,))
                conn.execute("DELETE FROM game_events WHERE room_id = ?", (room_id,))
                conn.execute(
                    "UPDATE players SET seat_number = -1, role = '', faction = '' WHERE room_id = ?",
                    (room_id,),
                )
                conn.execute("UPDATE rooms SET status = 'waiting' WHERE room_id = ?", (room_id,))
                conn.commit()
            finally:
                conn.close()

    def clear_all(self) -> None:
        """Drop all data (used at startup)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM game_events")
                conn.execute("DELETE FROM pending_actions")
                conn.execute("DELETE FROM players")
                conn.execute("DELETE FROM rooms")
                conn.commit()
            finally:
                conn.close()
