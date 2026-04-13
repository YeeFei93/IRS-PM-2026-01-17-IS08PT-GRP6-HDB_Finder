
from db_models.shopping_malls_db import ShoppingMallsDB
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from db_models.resale_flats_db import ResaleFlatsDB
from env import TABLE_NAME, KEY_NAME, ID
import threading
import math

from utils.geolocation_converter import GeolocationConverter

lock = threading.Lock()

class ResaleFlatsShoppingMallsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.distance_limit = 1.5
        self.table_name = TABLE_NAME.RESALE_FLATS_SHOPPING_MALLS
        
    def InitializeData(self):
        db = self.db
        db = DbConnector()
        resale_flats_geos = ResaleFlatsDB(db).GetGeolocations()
        x_geos = ShoppingMallsDB(db).GetAll()
       
        num_threads = 4
        batch_size =  math.ceil(len(resale_flats_geos) / num_threads)

        threads = []

        for i in range(0,num_threads):
            t = threading.Thread(target=self.InitializeBatch, args=(resale_flats_geos[i * batch_size : (i +1) * batch_size], x_geos))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

      
        
     
    def InitializeBatch(self, resale_flats_geos, x_geos):
        db = DbConnector()
        dbc = DbController(db)
        new_data_arr = []
        for a in resale_flats_geos:
            for b in x_geos:
                distance = GeolocationConverter().CalculateDistance(a[KEY_NAME.LATITUDE], a[KEY_NAME.LONGITUDE], b[KEY_NAME.LATITUDE], b[KEY_NAME.LONGITUDE])
                if(distance <= self.distance_limit):
                    new_data = {ID.BLOCK: a[ID.BLOCK], 
                                ID.STREET_NAME: a[ID.STREET_NAME], 
                                ID.SHOPPING_MALL_NAME: b[ID.SHOPPING_MALL_NAME],
                                KEY_NAME.DISTANCE: distance
                                }
                    new_data_arr.append(new_data)
                    with lock:
                        self.processed_count += 1
                        print(f"Processing {self.processed_count} resale flats to shopping malls distance...")

        dbc.UpsertData(self.table_name, new_data_arr)
        print("Successfully saved.")
        db.Close()

    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        
        

      
    
   
    