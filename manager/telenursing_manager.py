import datetime

from manager.database_manager import SingleConnection
from manager.util import to_dt_str, to_date_str, to_time_str


def fetch_all_telenursing():
    with SingleConnection() as con:
        all_telenursing = con.execute("SELECT telenursing.*, users.display_name, users.picture_url "
                                      "FROM telenursing "
                                      "LEFT JOIN users on telenursing.user_id = users.user_id "
                                      "ORDER BY meeting_dt").fetchall()
        dt_now = datetime.datetime.now()
        all_telenursing = [{
            "id": _['id'],
            "user_id": _['user_id'],
            "meeting_dt": _['meeting_dt'],
            "meeting_url": _['meeting_url'],
            "description": _['description'],
            "enabled": _['enabled'],
            "passed": datetime.datetime.fromisoformat(_['meeting_dt']) < dt_now,
            "display_name": _['display_name'],
            "picture_url": _['picture_url']
        } for _ in all_telenursing]
        return all_telenursing


def insert_telenursing(user_id, meeting_dt, meeting_url, description):
    with SingleConnection() as con:
        result_id = con.execute("INSERT INTO telenursing (user_id, meeting_dt, meeting_url, description) "
                                "VALUES(%s, %s, %s, %s) RETURNING id",
                                (user_id, to_dt_str(meeting_dt), meeting_url, description)).fetchone()
        con.commit()
        return result_id['id']


def cancel_telenursing(telenursing_id):
    with SingleConnection() as con:
        con.execute("UPDATE telenursing SET enabled = 0 WHERE telenursing.id = %s", (telenursing_id,))
        con.commit()
        return con.fetchone()


def fetch_all_med_reminders():
    with SingleConnection() as con:
        all_med_reminders = con.execute("SELECT med_reminders.*, users.display_name, users.picture_url "
                                        "FROM med_reminders "
                                        "LEFT JOIN users on med_reminders.user_id = users.user_id "
                                        "ORDER BY med_reminders.id").fetchall()
        date_now = datetime.date.today()
        all_med_reminders = [{
            "id": _['id'],
            "user_id": _['user_id'],
            "medicine": _['medicine'],
            "description": _['description'],
            "start_date": _['start_date'],
            "end_date": _['end_date'],
            "remind_time": _['remind_time'],
            "enabled": _['enabled'],
            "passed": _['end_date'] < date_now,
            "display_name": _['display_name'],
            "picture_url": _['picture_url']
        } for _ in all_med_reminders]
        return all_med_reminders


def insert_med_reminder(user_id, medicine, description,
                        start_date: datetime.date, end_date: datetime.date, remind_time: datetime.time):
    with SingleConnection() as con:
        result_id = con.execute("INSERT INTO med_reminders (user_id, medicine, description,"
                                "start_date, end_date, remind_time) "
                                "VALUES(%s, %s, %s, %s, %s, %s) RETURNING id",
                                (user_id, medicine, description,
                                 to_date_str(start_date), to_date_str(end_date), to_time_str(remind_time))).fetchone()
        con.commit()
        return result_id['id']


def cancel_med_reminder(med_reminder_id):
    with SingleConnection() as con:
        con.execute("UPDATE med_reminders SET enabled = 0 WHERE med_reminders.id = %s", (med_reminder_id,))
        con.commit()
        return con.fetchone()
