import mysql.connector

class DbConnector:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password="P@ssw0rd+1",
                database="ais08-pt-01"
            )
            if self.conn.is_connected():
                print("Connected to MySQL database")
        except mysql.connector.Error as e:
            print("Error connecting to MySQL:", e)

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            print("Connection closed")


DbConnector()