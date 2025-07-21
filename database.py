#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database initialization and all data handling methods.
"""

import sqlite3
from datetime import datetime
import os

DB_NAME = os.getenv("DB_PATH", "gym_bot.db")

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- Training Log Functions ---

def add_training_log(user_id: int, chat_id: int, exercise_name: str, weight_kg: float, reps: int) -> int:
    """Adds a new training log and returns the new record's ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO training_logs (user_id, chat_id, exercise_name, weight_kg, reps) VALUES (?, ?, ?, ?, ?)",
        (user_id, chat_id, exercise_name, weight_kg, reps)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def delete_last_log(log_id: int, user_id: int) -> bool:
    """Deletes a specific log entry by its ID, verifying the user ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM training_logs WHERE id = ? AND user_id = ?", (log_id, user_id))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_training_summary(user_id: int, chat_id: int, period: str = 'week'):
    """Fetches training summary for a user in a given period."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if period == 'day':
        date_filter = "date(timestamp) = date('now', 'localtime')"
    elif period == 'month':
        date_filter = "strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now', 'localtime')"
    else: # week
        date_filter = "strftime('%Y-%W', timestamp, 'weekday 0', '-6 days') = strftime('%Y-%W', 'now', 'localtime', 'weekday 0', '-6 days')"

    query = f"""
        SELECT exercise_name, COUNT(*) as sets, SUM(reps) as total_reps, MAX(weight_kg) as max_weight, SUM(weight_kg * reps) as total_volume
        FROM training_logs WHERE user_id = ? AND chat_id = ? AND {date_filter}
        GROUP BY exercise_name ORDER BY total_volume DESC
    """
    cursor.execute(query, (user_id, chat_id))
    summary = cursor.fetchall()
    conn.close()
    return summary

def get_personal_record(user_id: int, exercise_name: str):
    """Gets the personal record (max weight) for a specific exercise."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(weight_kg) as pr_weight FROM training_logs WHERE user_id = ? AND exercise_name = ?",
        (user_id, exercise_name)
    )
    pr = cursor.fetchone()
    conn.close()
    return pr['pr_weight'] if pr else None

def get_exercise_history(user_id: int, exercise_name: str, limit: int = 30):
    """Gets the recent history for a specific exercise for charting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, weight_kg, reps FROM training_logs WHERE user_id = ? AND exercise_name = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, exercise_name, limit)
    )
    history = cursor.fetchall()
    conn.close()
    return history

# --- Body Data & Metrics Functions ---

def get_valid_body_metrics() -> dict:
    """Gets all configured body metrics and their units."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT metric_name, unit FROM body_metrics_config")
    metrics = {row['metric_name']: row['unit'] for row in cursor.fetchall()}
    conn.close()
    return metrics

def add_body_metric_config(metric_name: str, unit: str) -> bool:
    """Adds a new trackable body metric. Returns False if it already exists."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO body_metrics_config (metric_name, unit) VALUES (?, ?)", (metric_name, unit))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # UNIQUE constraint failed
        return False
    finally:
        conn.close()

def delete_body_metric_config(metric_name: str) -> bool:
    """Deletes a trackable body metric."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM body_metrics_config WHERE metric_name = ?", (metric_name,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def add_body_data_log(user_id: int, metric_type: str, value: float, unit: str):
    """Adds a new body data log entry."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO body_data (user_id, metric_type, value, unit) VALUES (?, ?, ?, ?)",
        (user_id, metric_type, value, unit)
    )
    conn.commit()
    conn.close()

def get_body_data_history(user_id: int, metric_type: str, limit: int = 30):
    """Gets the recent history for a specific body metric for charting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, value FROM body_data WHERE user_id = ? AND metric_type = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, metric_type, limit)
    )
    history = cursor.fetchall()
    conn.close()
    return history

# --- Initialization ---

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS training_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            weight_kg REAL,
            reps INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS body_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            metric_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS body_metrics_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM body_metrics_config")
    if cursor.fetchone()[0] == 0:
        default_metrics = [('体重', 'kg'), ('体脂率', '%')]
        cursor.executemany('INSERT INTO body_metrics_config (metric_name, unit) VALUES (?, ?)', default_metrics)
    conn.commit()
    conn.close()
    print("Database checked and initialized successfully.")

if __name__ == '__main__':
    init_db()