from utils.db_connector import DbConnector
import mysql.connector
from mysql.connector import errorcode

class DbController:
    def __init__(self, db: DbConnector):
        self.db = db

    def GetColumnNames(self, table_name):
        self.db.cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = [row[0] for row in self.db.cursor.fetchall()]
        return columns

    def PreprocessData(self, data, table_name = None, mapping = None, column_names: list = []):
        if isinstance(data, dict):
            new_data = {}

            if table_name != None:
                column_names = self.GetColumnNames(table_name)
            for k,v in data.items():
                if mapping and k in mapping:
                    k = mapping[k]
                    
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
        
    def GetData(self, table_name):
        db = self.db    
        query = f"SELECT * FROM {table_name}"    
        db.cursor.execute(query)
        db.cursor.fetchone()

    def GetAll(self, table_name):
        db = self.db    
        query = f"SELECT * FROM {table_name}"    
        db.cursor.execute(query)
        return db.cursor.fetchall()

    def UpsertData(self, table_name, data, filters = None):
        db = self.db
        if isinstance(data, dict):
            
            sub_string_1 = ""
            sub_string_2 = ""
            sub_string_3 = ""
            values = ()

            for k, v in data.items():
                sub_string_1 += k + ","
                sub_string_2 += "%s,"
                sub_string_3 += f"{k} = new.{k},"
                values += (v,)
            sub_string_1 = sub_string_1[:-1]
            sub_string_2 = sub_string_2[:-1]
            sub_string_3 = sub_string_3[:-1]

            query = f"""INSERT INTO {table_name} ({sub_string_1}) VALUES({sub_string_2})  AS new 
                        ON DUPLICATE KEY UPDATE 
                                {sub_string_3}
            """

            try:
                db.cursor.execute(query, values)
                db.Commit()
                print("Successfuly Updated.")
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_DUP_ENTRY:
                    # print(err)
                    pass


        if isinstance(data, list):
            main_query = ""
            main_values = []
           
            for item in data:
                sub_string_1 = ""
                sub_string_2 = ""
                sub_string_3 = ""
                values = ()
                for k, v in item.items():
                    sub_string_1 += k + ","
                    sub_string_2 += "%s,"
                    sub_string_3 += f"{k} = new.{k},"
                    values += (v,)
                main_values.append(values)
                sub_string_1 = sub_string_1[:-1]
                sub_string_2 = sub_string_2[:-1]
                sub_string_3 = sub_string_3[:-1]

                main_query = f"""INSERT INTO {table_name} ({sub_string_1}) VALUES({sub_string_2}) AS new 
                                ON DUPLICATE KEY UPDATE 
                                {sub_string_3}
                                """

            try:
                db.cursor.executemany(main_query, main_values)
                # print({87: main_query})
                # print({88: main_values})
                db.Commit()
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_DUP_ENTRY:
                    print(err)
                    pass
                else:
                    raise    

    def DeleteData(self, table_name, filters = None):
        db = self.db
        query = f"Delete from {table_name}"

        db.cursor.execute(query)
        db.Commit()

 



