# Restore exported CSV data into the hosted Mongo Atlas cluster.
import pandas as pd
from pymongo import MongoClient

# 1. connect to your MongoDB cluster
client = MongoClient("mongodb+srv://devananda1502_db_user:PDuFX3jYjvQJSLy3@aibuddy.furcexz.mongodb.net/?appName=AIBuddy")
db = client["AIBuddy"]

# 2. load exported CSVs
chat_df = pd.read_csv("chat_history_backup.csv")
session_df = pd.read_csv("session_meta_backup.csv")

# 3. insert into Mongo collections
chat_records = chat_df.to_dict(orient="records")
session_records = session_df.to_dict(orient="records")

if chat_records:
    db.chat_messages.insert_many(chat_records)
if session_records:
    db.sessions.insert_many(session_records)

print("Inserted", len(chat_records), "chat docs")
print("Inserted", len(session_records), "session docs")
