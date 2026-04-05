
from datetime import datetime
from db_controller import DbController
from db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
from configs.raw_to_db_mappings import hawker_centres_mapping
import uuid
import threading
import math
import time
import random
from geojson_to_json import GeojsonToJson
class HawkerCentresDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.HAWKER_CENTRES

    def InitialiseData(self):
        db = self.db
        dbc = DbController(db)
        new_data_arr = []
        column_names = dbc.GetColumnNames(self.table_name)
        processed_count = 0
        for item in self.GetRawData()["features"]:  
            item[ID.HAWKER_CENTRE_ID] = str(uuid.uuid4())  
            item[KEY_NAME.LATITUDE] = item["geometry"]["coordinates"][0]
            item[KEY_NAME.LONGITUDE] = item["geometry"]["coordinates"][0]
            item[KEY_NAME.NAME] = item["properties"]["NAME"]
            item[KEY_NAME.PHOTO_URL] = item["properties"]["PHOTOURL"]
            processed = dbc.PreprocessData(item, mapping=hawker_centres_mapping, column_names=column_names)

            new_data_arr.append(processed)
            processed_count +=1
            print(f"Processing {processed_count} hawker centres...")

        dbc.InsertData(self.table_name, new_data_arr)
   
    def GetRawData(self):
        return GeojsonToJson("./raw-data/hawker-centres").data
    
    def DeleteData(self):
        pass
        
    