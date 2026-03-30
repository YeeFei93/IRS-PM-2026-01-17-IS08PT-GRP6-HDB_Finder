from db_connector import DbConnector

class DbController:
    def __init__(self, db: DbConnector):
        self.db = db

    def GetColumnNames(self, table_name):
        self.db.cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = [row[0] for row in self.db.cursor.fetchall()]
        return columns

    def PreprocessData(self, table_name, data):
        if isinstance(data, dict):
            new_data = {}
            column_names = self.GetColumnNames(table_name)
            for k,v in data.items():
                # print({19: (k,v)})
                if k in column_names:
                    new_data[k] = v
            return new_data
        if isinstance(data, list):
            new_data_arr = []
            for item in data:
                new_data = self.PreprocessData(table_name, item)
                if len(new_data) > 0:
                    new_data_arr.append(new_data)
            
            return new_data_arr

    def InsertData(self, data):
        pass

