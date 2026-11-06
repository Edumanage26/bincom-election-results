import mysql.connector

try:
    connection = mysql.connector.connect(
       host="127.0.0.1",
port=3306,
user="bincom_app",
password="",
database="bincom_test"
    )

    print("SUCCESS: Connected to Bincom database!")

    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM polling_unit")
    result = cursor.fetchone()

    print("Total polling units:", result[0])

    cursor.close()
    connection.close()

except mysql.connector.Error as error:
    print("DATABASE CONNECTION FAILED:")
    print(error)