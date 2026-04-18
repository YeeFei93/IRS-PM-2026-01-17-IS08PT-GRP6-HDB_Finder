import os

import mysql.connector

class DbConnector:
    def __init__(self):
        self.conn = None
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "P@ssw0rd+1")
        self.database = os.getenv("MYSQL_DATABASE", "iss-irs-ai-estate-recommender-07")
        self.cursor = self.Connect()
        

    def Connect(self):
        try:
            self.conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            if self.conn.is_connected():
                print("Connected to MySQL database")
                return self.conn.cursor()

            raise RuntimeError(
                f"Unable to connect to MySQL database '{self.database}'."
            )
        except mysql.connector.Error as e:
            raise RuntimeError(
                f"Failed to connect to MySQL database '{self.database}' on "
                f"host '{self.host}' as user '{self.user}'. "
                f"Set MYSQL_DATABASE / MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD "
                f"if your local setup is different. Original error: {e}"
            ) from e

    def Commit(self):
        self.conn.commit()

    def Close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            # print("Connection closed")
