from datetime import datetime, timedelta

from constants import ReminderState
from manager.database_manager import SingleConnection, log_chat
from manager.helper_line import reply_message, datetime_message, plain_text_push_and_log
from manager.util import formatted_thai_dt

user_sessions = {}


def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {'state': ReminderState.IDLE, 'data': {}}
    return user_sessions[user_id]


def set_session(user_id, state, title=None, target_datetime=None, detail=None):
    if user_id not in user_sessions:
        user_sessions[user_id] = {'state': ReminderState.IDLE, 'data': {}}

    user_sessions[user_id]['state'] = state
    if title is not None:
        user_sessions[user_id]['data']['title'] = title
    if target_datetime is not None:
        user_sessions[user_id]['data']['datetime'] = target_datetime
    if detail is not None:
        user_sessions[user_id]['data']['detail'] = detail
    return user_sessions[user_id]


def schedule_notification(user_id, date_text, time_text, message):
    with SingleConnection() as con:
        con.execute("INSERT INTO notifications (user_id, date, time, message) "
                    "VALUES (%s, %s, %s, %s)",
                    (str(user_id), date_text, time_text, message))
        con.commit()


def insert_reminder(user_id, target_dt, title, detail):
    morning_of = target_dt.replace(hour=6, minute=0, second=0, microsecond=0)
    night_before = morning_of.replace(day=morning_of.day - 1, hour=18)
    seven_days = morning_of.replace(day=morning_of.day - 7)
    reminder_text = (f"การเตือนการนัดหมาย เรื่อง:\n {title}\n\n"
                     f"นัดหมายวันเดือนปี เวลา:\n {formatted_thai_dt(target_dt)}\n\n"
                     f"รายละเอียดอื่น ๆ:\n {detail}")

    reply_text = (f"สร้างการเตือนการนัดหมายสำเร็จ\n\n"
                  f"{reminder_text}\n\n"
                  f"วันเวลาที่จะเตือน: \n")
    if seven_days > datetime.now():
        reply_text += f"- {formatted_thai_dt(seven_days)} (7 วันก่อนวันนัด)\n"
    if night_before > datetime.now():
        reply_text += f"- {formatted_thai_dt(night_before)} (คืนก่อนวันนัด)\n"
    if morning_of > datetime.now():
        reply_text += f"- {formatted_thai_dt(morning_of)} (เช้าวันนัด)\n"
    reply_text += f"- {formatted_thai_dt(target_dt)} (วันและเวลาที่นัด)"

    for to_remind in [morning_of, night_before, seven_days, target_dt]:
        if to_remind > datetime.now():
            date_text = to_remind.strftime("%Y-%m-%d")
            time_text = to_remind.strftime("%H:%M")
            schedule_notification(user_id=user_id, date_text=date_text, time_text=time_text,
                                  message=reminder_text)
    return reply_text


def create_reminder(user_id, reply_token, action="new", text=None):
    if action == "new":
        set_session(user_id, ReminderState.TITLE)
        reply_message(reply_token, "กรุณาใส่การชื่อการนัดหมายที่ต้องการเตือน")
    elif action == "cancel":
        set_session(user_id, ReminderState.IDLE)
    else:
        match get_session(user_id)['state']:
            case ReminderState.TITLE:
                set_session(user_id, ReminderState.DATETIME, title=text)
                datetime_message(reply_token, "กรุณาเลือกวันที่และเวลาของการนัดหมาย")
            case ReminderState.DATETIME:
                target_dt = datetime.fromisoformat(text)
                if target_dt < datetime.now() + timedelta(hours=1):
                    datetime_message(reply_token,
                                     "คุณเลือกเวลาที่ใกล้เกินไป (น้อยกว่า 1 ชั่วโมงจากนี้) กรุณาเลือกวันที่และเวลาของการนัดหมายใหม่")
                else:
                    set_session(user_id, ReminderState.DETAIL, target_datetime=text)
                    reply_message(reply_token, f"คุณใส่เลือกวันเวลา {formatted_thai_dt(datetime.fromisoformat(text))}\n"
                                               f"กรุณาใส่รายละเอียดอื่น ๆ เกี่ยวกับการนัดหมาย เช่น การเตรียมตัว")
            case ReminderState.DETAIL:
                set_session(user_id, ReminderState.IDLE, detail=text)
                print(user_sessions[user_id]['data'])
                print("DONE!")
                reminder_info = user_sessions[user_id]['data']
                target_dt = datetime.fromisoformat(reminder_info['datetime'])
                reply_text = insert_reminder(user_id, target_dt, reminder_info['title'], reminder_info['detail'])
                log_chat(user_id, message="scheduling from LINE OA", response=reply_text,
                         model_name="automated message")
                reply_message(reply_token, content=reply_text)
            case _:
                pass

    pass


def check_for_notification():
    with SingleConnection() as con:
        # check the notifications table
        now = datetime.now()
        date = now.strftime("%Y-%m-%d")
        ytd = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        notifications = con.execute("SELECT * FROM notifications WHERE sent = 0 and (date = %s or date = %s)",
                                    (date, ytd)).fetchall()
        sent_count = 0
        for n in notifications:
            n = dict(n)  # to prevent sqlite3 different thread problem
            scheduled_dt = datetime.strptime(f"{n['date']} {n['time']}", "%Y-%m-%d %H:%M")
            if scheduled_dt < now:
                con.execute("UPDATE notifications SET sent=1 WHERE id=%s", (int(n['id']),))
                con.commit()
                plain_text_push_and_log(push_text=f"อย่าลืม: {n['message']}", model_name="automated message",
                                        user_id=n['user_id'], original_text="scheduled notification")
                sent_count += 1

        # check the med_reminders table
        med_reminders = con.execute("SELECT * FROM med_reminders WHERE "
                                    "start_date <= %s and "
                                    "%s <= end_date and "
                                    "enabled = 1",(date, date)).fetchall()

        for n in med_reminders:
            remind_time = n['remind_time']
            if (now.time().hour == remind_time.hour) and (now.time().minute == remind_time.minute):
                push_text = f"แจ้งเตือน: {n['medicine']} เวลา {n['remind_time']}\n\n{n['description']}"
                plain_text_push_and_log(push_text=push_text, model_name="automated message",
                                        user_id=n['user_id'], original_text="scheduled notification")
                sent_count += 1

        if sent_count > 0:
            print(f"checking for notifications to be sent... now {now}: {sent_count} messages sent.")
