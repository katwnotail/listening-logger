import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
)
cur = conn.cursor()
cur.execute("SHOW TABLES")
print("Connected. Tables:", [row[0] for row in cur.fetchall()])
cur.close()
conn.close()