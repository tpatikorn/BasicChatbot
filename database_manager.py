import csv
import os
import sqlite3


class SingleConnection:
    def __init__(self, sqlite_filename="chatbot.db"):
        self._con = sqlite3.connect(sqlite_filename)
        self._con.row_factory = sqlite3.Row

    def __enter__(self):
        return self._con

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._con.close()


def init_database():
    with SingleConnection() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS chat_logs
                       (
                           id       INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                           user_id  TEXT    NOT NULL,
                           date     TEXT    NOT NULL,
                           time     TEXT    NOT NULL,
                           message  TEXT    NOT NULL,
                           response TEXT    NOT NULL,
                           error    TEXT,
                           model    TEXT
                       )''')
        con.execute('''CREATE TABLE IF NOT EXISTS notifications
                       (
                           id      INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                           user_id TEXT    NOT NULL,
                           date    TEXT    NOT NULL,
                           time    TEXT    NOT NULL,
                           message TEXT    NOT NULL,
                           sent    INTEGER NOT NULL DEFAULT 0
                       )''')


def migrate_database():
    with SingleConnection() as con:
        if os.path.exists("chat_log.csv"):
            with open('chat_log.csv', encoding="utf8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    query_str = ("INSERT INTO chat_logs (user_id, date, time, message, response, error, model) "
                                 "VALUES (:userId, :date, :time, :message, :response, '', '')")
                    con.executemany(query_str, row)
                    con.commit()
        if os.path.exists("chat_log.csv"):
            with open('schedule.csv', encoding="utf8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    query_str = (f"INSERT INTO notifications (user_id, date, time, message, sent) "
                                 f"VALUES ('{row['userId']}', '{row['date']}', '{row['time']}', '{row['message']}', 1)")
                    con.execute(query_str)
                    con.commit()


if __name__ == "__main__":
    migrate_database()

    print("done")
