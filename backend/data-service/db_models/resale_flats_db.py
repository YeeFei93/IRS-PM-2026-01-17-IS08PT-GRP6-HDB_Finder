
from datetime import datetime

from csv_to_json import CsvToJson
from db_controller import DbController
from db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
from configs.hdb_resale_price_mapping import hdb_resale_price_mapping
import uuid
import threading
import math
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
        num_threads = 3
        batch_size =  math.ceil(len(raw_data) / num_threads)

        threads = []

        for i in range(0,num_threads):
            t = threading.Thread(target=self.InitializeBatch, args=(raw_data[i * batch_size : (i +1) * batch_size], i + 1))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

      
        
     
    def InitializeBatch(self, data, thread_num):
        db = DbConnector()
        dbc = DbController(db)

        estate_column_names = dbc.GetColumnNames(TABLE_NAME.ESTATES)
        flat_type_column_names = dbc.GetColumnNames(TABLE_NAME.FLAT_TYPES)
        flat_model_column_names = dbc.GetColumnNames(TABLE_NAME.FLAT_MODELS)
        resale_flats_geolocation_column_names = dbc.GetColumnNames(TABLE_NAME.RESALE_FLATS_GEOLOCATION)
        resale_flat_column_names = dbc.GetColumnNames(TABLE_NAME.RESALE_FLATS)

        new_estates = []
        new_flat_types = []
        new_flat_models = []
        new_resale_flats_geolocations = []
        new_resale_flats = []

        counter = 0
        for item in data:
            processed_estate = dbc.PreprocessData(item, mapping=hdb_resale_price_mapping, column_names=estate_column_names)
            processed_flat_type = dbc.PreprocessData(item, column_names=flat_type_column_names)
            processed_flat_model = dbc.PreprocessData(item, column_names=flat_model_column_names)
            processed_resale_flats_geolocation = dbc.PreprocessData(item, column_names=resale_flats_geolocation_column_names)
            processed_resale_flat = dbc.PreprocessData(item, mapping=hdb_resale_price_mapping, column_names=resale_flat_column_names)
            processed_resale_flat[ID.RESALE_FLAT_ID] = str(uuid.uuid4()) + f"-{thread_num}"
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

            if KEY_NAME.SOLD_DATE in processed_resale_flat:
                processed_resale_flat[KEY_NAME.SOLD_DATE] = processed_resale_flat[KEY_NAME.SOLD_DATE] + "-01"


            if processed_estate[KEY_NAME.ESTATE] not in self.new_estates_uniques:
                with lock:
                    if processed_estate[KEY_NAME.ESTATE] not in self.new_estates_uniques:
                        self.new_estates_uniques[processed_estate[KEY_NAME.ESTATE]] = None
                        new_estates.append(processed_estate)
            
            if processed_flat_type[KEY_NAME.FLAT_TYPE] not in self.new_flat_types_uniques:
                with lock:
                    if processed_flat_type[KEY_NAME.FLAT_TYPE] not in self.new_flat_types_uniques:
                        self.new_flat_types_uniques[processed_flat_type[KEY_NAME.FLAT_TYPE]] = None
                        new_flat_types.append(processed_flat_type)
            
            if processed_flat_model[KEY_NAME.FLAT_MODEL] not in self.new_flat_models_uniques:
                with lock:
                    if processed_flat_model[KEY_NAME.FLAT_MODEL] not in self.new_flat_models_uniques:
                        self.new_flat_models_uniques[processed_flat_model[KEY_NAME.FLAT_MODEL]] = None
                        new_flat_models.append(processed_flat_model)

            temp_key = f"{processed_resale_flats_geolocation[KEY_NAME.BLOCK]}-{processed_resale_flats_geolocation[KEY_NAME.STREET_NAME]}"
            if temp_key not in self.new_resale_flats_geolocations_uniques:
                with lock:
                    if temp_key not in self.new_resale_flats_geolocations_uniques:
                        self.new_resale_flats_geolocations_uniques[temp_key] = None
                        new_resale_flats_geolocations.append(processed_resale_flats_geolocation)

            new_resale_flats.append(processed_resale_flat)

            counter +=1
            if counter % 100 == 0:
                with lock:
                    self.processed_count += 100
                    print(f"Processing {self.processed_count} resale flats...")
   
        dbc.InsertData(TABLE_NAME.ESTATES, new_estates)
        dbc.InsertData(TABLE_NAME.FLAT_TYPES, new_flat_types)
        dbc.InsertData(TABLE_NAME.FLAT_MODELS, new_flat_models)
        dbc.InsertData(TABLE_NAME.RESALE_FLATS_GEOLOCATION, new_resale_flats_geolocations)
        dbc.InsertData(TABLE_NAME.RESALE_FLATS, new_resale_flats)
           
        print("Successfully saved resale flats")
        db.Close()

    
    def GetRawData(self):
        return CsvToJson("./raw-data/hdb-resale-price").data
    
    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        
    