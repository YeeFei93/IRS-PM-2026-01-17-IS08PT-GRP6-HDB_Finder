from db_connector import DbConnector
import mysql.connector
from mysql.connector import errorcode

class DbController:
    def __init__(self, db: DbConnector):
        self.db = db

    def GetColumnNames(self, table_name):
        self.db.cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = [row[0] for row in self.db.cursor.fetchall()]
        return columns

    def PreprocessData(self, data, table_name = None, column_names: list = []):
        if isinstance(data, dict):
            new_data = {}
            if len(column_names) == 0:
                column_names = self.GetColumnNames(table_name)
            for k,v in data.items():
                # print({19: (k,v)})
                if k in column_names:
                    new_data[k] = v
            return new_data
        if isinstance(data, list):
            new_data_arr = []
            for item in data:
                new_data = self.PreprocessData(item, table_name=table_name, column_names=column_names)
                if len(new_data) > 0:
                    new_data_arr.append(new_data)
            
            return new_data_arr
        
    def GetData(self):
        db = self.db    
        query = "SELECT COUNT(*) FROM resale_flats"    
        db.cursor.execute(query)
        db.cursor.fetchone()
    def InsertData(self, table_name, data, filters = None):
        db = self.db
        if isinstance(data, dict):
            
            sub_string_1 = ""
            sub_string_2 = ""
            values = ()
            for k, v in data.items():
                sub_string_1 += k + ","
                sub_string_2 += "%s,"
                values += (v,)
            sub_string_1 = sub_string_1[:-1]
            sub_string_2 = sub_string_2[:-1]

            query = f"""INSERT INTO {table_name} ({sub_string_1}) VALUES({sub_string_2})"""

            try:
                db.cursor.execute(query, values)
                db.Commit()
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_DUP_ENTRY:
                    pass
                else:
                    raise    



