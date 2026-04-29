import os
from datetime import datetime

import dotenv
import psycopg
from psycopg.rows import dict_row

dotenv.load_dotenv()


class SingleConnection:
    def __init__(self):
        self._con = psycopg.connect(user=os.getenv("DB_USER"),
                                    password=os.getenv("DB_PASS"),
                                    host=os.getenv("DB_SERVER"),
                                    port="5432",
                                    dbname=os.getenv("DB_DB"),
                                    row_factory=dict_row)

    def __enter__(self):
        return self._con

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._con.close()


# database functions
def log_chat(user_id, message, response, model_name):
    dt_now = datetime.now()
    date_text = dt_now.strftime("%Y-%m-%d")
    time_text = dt_now.strftime("%H:%M")

    with SingleConnection() as con:
        con.execute("INSERT INTO chat_logs (user_id, date, time, message, response, error, model) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (str(user_id), date_text, time_text, message, response, '', model_name))
        con.commit()


if __name__ == "__main__":
    # migrate_database()

    print("done")
