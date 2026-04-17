
from datetime import datetime

from db_models.mrt_stations_db import MrtStationsDB
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from db_models.parks_db import ParksDB
from db_models.resale_flats_db import ResaleFlatsDB
from env import TABLE_NAME, KEY_NAME, ID
import uuid
import threading
import math
import time
import random

from utils.geolocation_converter import GeolocationConverter

lock = threading.Lock()
class ResaleFlatsMrtStationsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.distance_limit = 1
        self.table_name = TABLE_NAME.RESALE_FLATS_MRT_STATIONS
        
    def InitializeData(self):
        db = self.db
        db = DbConnector()
        resale_flats = ResaleFlatsDB(db).GetGeolocations()
        mrt_exits = MrtStationsDB(db).GetExits()
       
        mrt_unique_exits = {}
        for item in mrt_exits:
            mrt_station_name = item[ID.MRT_STATION_NAME]
            
            if not mrt_unique_exits.get(mrt_station_name):
                mrt_unique_exits[mrt_station_name] = []
            arr: list =  mrt_unique_exits[mrt_station_name]
            arr.append(item)
            mrt_unique_exits[mrt_station_name] = arr
        

        threads = []

        for k, v in mrt_unique_exits.items():
            t = threading.Thread(target=self.InitializeBatch, args=(k, v, resale_flats))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

      
        
     
    def InitializeBatch(self, mrt_station_name, mrt_exits, resale_flats):
        db = DbConnector()
        dbc = DbController(db)
        new_data_arr = []
        for a in resale_flats:
            MIN_DISTANCE = {}
            for b in mrt_exits:
                distance = GeolocationConverter().CalculateDistance(a[KEY_NAME.LATITUDE], a[KEY_NAME.LONGITUDE], b[KEY_NAME.LATITUDE], b[KEY_NAME.LONGITUDE])


                if not MIN_DISTANCE.get(mrt_station_name):
                    MIN_DISTANCE[mrt_station_name] = distance

                if distance > self.distance_limit:
                    continue

                if distance >= MIN_DISTANCE[mrt_station_name]:
                    continue

                new_data = next((x for x in new_data_arr if x[ID.BLOCK] == a[ID.BLOCK]
                                                        and x[ID.STREET_NAME] == a[ID.STREET_NAME]
                                                        and x[ID.MRT_STATION_NAME] == mrt_station_name
                                                        and x[ID.EXIT_CODE] == b[ID.EXIT_CODE]), None)
                if new_data:
                    new_data[KEY_NAME.DISTANCE] = distance

                else:
                    new_data = {ID.BLOCK: a[ID.BLOCK], 
                                ID.STREET_NAME: a[ID.STREET_NAME], 
                                ID.MRT_STATION_NAME: mrt_station_name,
                                ID.EXIT_CODE: b[ID.EXIT_CODE],
                                KEY_NAME.DISTANCE: distance
                                }
                new_data_arr.append(new_data)
                with lock:
                    self.processed_count += 1
                    print(f"Processing {self.processed_count} resale flats to mrt stations...")

        dbc.UpsertData(self.table_name, new_data_arr)
        print("Successfully saved.")
        db.Close()

    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        
        

      
    
   
    