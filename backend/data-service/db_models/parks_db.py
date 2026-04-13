
from datetime import datetime
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
import uuid
from utils.geojson_to_json import GeojsonToJson
class ParksDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.PARKS

    def InitialiseData(self):
        db = self.db
        dbc = DbController(db)
        new_data_arr = []
        column_names = dbc.GetColumnNames(self.table_name)
        processed_count = 0
        for item in self.GetRawData()["features"]:  
            park_name = item["properties"]["NAME"]

            if "PLAYGROUND" in park_name:
                continue
            
            item[ID.PARK_NAME] = item["properties"]["NAME"]
            item[KEY_NAME.LATITUDE] = item["geometry"]["coordinates"][1]
            item[KEY_NAME.LONGITUDE] = item["geometry"]["coordinates"][0]
            processed = dbc.PreprocessData(item, column_names=column_names)

            new_data_arr.append(processed)
            processed_count +=1
            print(f"Processing {processed_count} parks...")

        dbc.InsertData(self.table_name, new_data_arr)
   
    def GetRawData(self):
        return GeojsonToJson("./raw-data/parks").data
    
    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        
    