import sqlite3
import pandas as pd

# path to your existing SQLite file
conn = sqlite3.connect("chat_history_memori.db")

# read both tables
chat_df = pd.read_sql_query("SELECT * FROM chat_history", conn)
session_df = pd.read_sql_query("SELECT * FROM session_meta", conn)

# preview and save to CSV (for backup)
chat_df.to_csv("chat_history_backup.csv", index=False)
session_df.to_csv("session_meta_backup.csv", index=False)

print(len(chat_df), "chat rows exported")
print(len(session_df), "session rows exported")
