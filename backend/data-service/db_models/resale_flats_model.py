
from csv_to_json import CsvToJson
from db_controller import DbController
from db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
import uuid
import threading
import math

lock = threading.Lock()
class ResaleFlatsModel:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        
    def InitializeData(self):
        db = self.db
        raw_data = self.GetRawData()
        num_threads = 8
        batch_size =  math.ceil(len(raw_data) / num_threads)

        threads = []

        for i in range(0,num_threads):
            t = threading.Thread(target=self.InitializeBatch, args=(raw_data[i * batch_size : (i +1) * batch_size],))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        
        
     
    def InitializeBatch(self, data):
        db = DbConnector()
        dbc = DbController(db)
        estate_column_names = dbc.GetColumnNames(TABLE_NAME.ESTATES)
        flat_type_column_names = dbc.GetColumnNames(TABLE_NAME.FLAT_TYPES)
        resale_flat_column_names = dbc.GetColumnNames(TABLE_NAME.RESALE_FLATS)

        counter = 0
        for item in data:
            item[KEY_NAME.ESTATE] = item[KEY_NAME.TOWN] 
            item[ID.RESALE_FLAT_ID] = str(uuid.uuid4())
            processed_estate = dbc.PreprocessData(item, column_names=estate_column_names)
            processed_flat_type = dbc.PreprocessData(item, column_names=flat_type_column_names)
            processed_resale_flat = dbc.PreprocessData(item, column_names=resale_flat_column_names)
            dbc.InsertData(TABLE_NAME.ESTATES, processed_estate)
            dbc.InsertData(TABLE_NAME.FLAT_TYPES, processed_flat_type)
            # dbc.InsertData(TABLE_NAME.RESALE_FLATS, processed_resale_flat)
            counter += 1
            if counter % 100 == 0:
                with lock:
                    self.processed_count += 100
                    print(f"Processing {self.processed_count} resale flats...")
            # DbController()
            # print(processed_estate)
            # break
        db.Close()


    def GetRawData(self):
        return CsvToJson("./raw-data/hdb-resale-price").data
    