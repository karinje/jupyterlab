import snowflake.connector

# Replace these with your actual values
conn = snowflake.connector.connect(
    user="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    account="YOUR_ACCOUNT",  # e.g. 'xy12345.us-east-1'
    warehouse="YOUR_WAREHOUSE",
    database="YOUR_DATABASE",
    schema="YOUR_SCHEMA",
)

try:
    cs = conn.cursor()
    cs.execute("SELECT CURRENT_VERSION()")
    version = cs.fetchone()
    print("Connection successful! Snowflake version:", version[0])
finally:
    cs.close()
    conn.close()
