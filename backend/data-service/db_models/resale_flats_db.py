
from datetime import datetime

from utils.csv_to_json import CsvToJson
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
from configs.raw_to_db_mappings import resale_flats_mapping
import uuid
import threading
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import random

lock = threading.Lock()
class ResaleFlatsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.table_name = TABLE_NAME.RESALE_FLATS

        self.new_estates_uniques = {}
        self.new_flat_types_uniques = {}
        self.new_flat_models_uniques = {}
        self.new_resale_flats_geolocations_uniques = {}
        self.new_resale_flats_uniques = {}
        
    def InitializeData(self):
        db = self.db
        raw_data = self.GetRawData()

        MAX_SOLD_DATE = None
        # Get the last sold date
        new_data = []
        for item in raw_data:
            sold_date = item.get("month")
            if MAX_SOLD_DATE == None:
                MAX_SOLD_DATE = sold_date

            if sold_date > MAX_SOLD_DATE:
                MAX_SOLD_DATE = sold_date

        for item in raw_data:
            sold_date = datetime.strptime(item.get("month") + "-01", "%Y-%m-%d")
            min_sold_date = datetime.strptime(MAX_SOLD_DATE  + "-01", "%Y-%m-%d") - relativedelta(months=6)

            if sold_date < min_sold_date:
                continue
            
            item[KEY_NAME.SOLD_DATE] = sold_date
            new_data.append(item)
        print({54: len(new_data)})
        batches = {}
        for item in new_data:
            key_name = item["town"]
            if not key_name in batches:
                batches[key_name] = []
            
            batches[key_name].append(item)



        threads = []
        for k, v in batches.items():
            t = threading.Thread(target=self.InitializeBatch, args=(v,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

      
        
     
    def InitializeBatch(self, data):
        db = DbConnector()
        dbc = DbController(db)

        estate_column_names = dbc.GetColumnNames(TABLE_NAME.ESTATES)
        flat_type_column_names = dbc.GetColumnNames(TABLE_NAME.FLAT_TYPES)
        flat_model_column_names = dbc.GetColumnNames(TABLE_NAME.FLAT_MODELS)
        resale_flat_column_names = dbc.GetColumnNames(TABLE_NAME.RESALE_FLATS)

        new_estates = []
        new_flat_types = []
        new_flat_models = []
        new_resale_flats_geolocations = []
        new_resale_flats = []

        counter = 0
        for item in data:
            processed_estate = dbc.PreprocessData(item, mapping=resale_flats_mapping, column_names=estate_column_names)
            processed_flat_type = dbc.PreprocessData(item, column_names=flat_type_column_names)
            processed_flat_model = dbc.PreprocessData(item, column_names=flat_model_column_names)
            processed_resale_flat = dbc.PreprocessData(item, mapping=resale_flats_mapping, column_names=resale_flat_column_names)
            processed_resale_flat[ID.RESALE_FLAT_ID] = str(uuid.uuid4())

            if KEY_NAME.STOREY_RANGE in item:
                temp_str: str = item[KEY_NAME.STOREY_RANGE]
                storeys = temp_str.split(" TO ")
                processed_resale_flat[KEY_NAME.STOREY_RANGE_START] = int(storeys[0])
                processed_resale_flat[KEY_NAME.STOREY_RANGE_END] = int(storeys[1])

            if KEY_NAME.REMAINING_LEASE in item:
                temp_str: str = item[KEY_NAME.REMAINING_LEASE]
                years_months = temp_str.split(" years ")
                if len(years_months) > 1:
                    processed_resale_flat[KEY_NAME.REMAINING_LEASE_YEARS] = int(years_months[0])
                    processed_resale_flat[KEY_NAME.REMAINING_LEASE_MONTHS] = int(years_months[1].replace(" months", "").replace(" month", ""))
                else: 
                    processed_resale_flat[KEY_NAME.REMAINING_LEASE_YEARS] = int(years_months[0].replace(" years", "").replace(" year", ""))
                    processed_resale_flat[KEY_NAME.REMAINING_LEASE_MONTHS] = 0
        
            new_estates.append(processed_estate)
            new_flat_types.append(processed_flat_type)
            new_flat_models.append(processed_flat_model)
            new_resale_flats.append(processed_resale_flat)

            counter +=1
            if counter % 100 == 0:
                with lock:
                    self.processed_count += 100
                    print(f"Processing {self.processed_count} resale flats...")


        with lock:
            dbc.InsertData(TABLE_NAME.ESTATES, new_estates)
            dbc.InsertData(TABLE_NAME.FLAT_TYPES, new_flat_types)
            dbc.InsertData(TABLE_NAME.FLAT_MODELS, new_flat_models)
            dbc.InsertData(TABLE_NAME.RESALE_FLATS, new_resale_flats)
           
        print("Successfully saved resale flats")
        db.Close()

    
    def GetRawData(self):
        return CsvToJson("./raw-data/hdb-resale-price").data
    
    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        
    