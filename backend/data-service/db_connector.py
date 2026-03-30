import mysql.connector
from mysql.connector.connection import MySQLConnection

class DbConnector:
    def __init__(self):
        self.conn = None
        self.cursor = self.Connect()
        

    def Connect(self):
        try:
            self.conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password="P@ssw0rd+1",
                database="ais08-pt-01"
            )
            if self.conn.is_connected():
                print("Connected to MySQL database")
                return self.conn.cursor()
            
        except mysql.connector.Error as e:
            print("Error connecting to MySQL:", e)

    def Close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            print("Connection closed")