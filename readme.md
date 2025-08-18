# .env
- GEMINI_API_KEY=.....
- LINE_BOT_ACCESS_TOKEN=.....
- LINE_BOT_CHANNEL_SECRET=.....

# schedule.csv
- columns are 
  - `userId`: LINE user id
  - `date`: date to send a reminder in this format `yyyy-MM-dd` e.g. `2025-08-18`
  - `time`: time to send a reminder in this format `hh:mm` e.g. `20:30`
  - `message`: the message to be sent as a reminder



# Installation
- pip install -r requirements.txt
- webhook is under `domain:port/llm/callback`

# What this chatbot does
- If a message starts with `Reminder` (case-sensitive) then it will try to find the date time in this exact format `yyyy-MM-dd hh:mm` e.g. `2025-08-18 20:30` and put a row in `schedule.csv`
- Every hour at specified minute, according to `schedule.csv`, a push message will be sent to the user id who set up a reminder if the specified date/time is within 1 hour before the current time.
- If the message doesn't start with `Reminder`, then it'll ask Gemini with specified `context.txt` and `system_prompt.txt`
