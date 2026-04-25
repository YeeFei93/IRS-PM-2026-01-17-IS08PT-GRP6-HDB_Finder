
from datetime import datetime

from utils.db_controller import DbController
from utils.db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
import uuid
import threading
import math
import time
import random

from utils.geolocation_converter import GeolocationConverter

lock = threading.Lock()
class ResaleFlatsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.table_name = TABLE_NAME.RESALE_FLATS
        self.batch_num = 0
        self.MAX_BATCH_NUM = 5
        
    def GetAll(self):
        db = self.db
        dbc = DbController(db)
        return dbc.GetAll(self.table_name)
    
    def GetGeolocations(self):
        db = self.db
        query = f"""SELECT * FROM {TABLE_NAME.RESALE_FLATS_GEOLOCATION} a"""
        
        db.cursor.execute(query)
        return db.cursor.fetchall()
    

    def GetDistinctAddresses(self):
        db = self.db
        query = f"SELECT DISTINCT {ID.BLOCK}, {ID.STREET_NAME} FROM {self.table_name} order by {ID.BLOCK} asc"
        db.cursor.execute(query)
        return db.cursor.fetchall()

    def GetAllWithGeolocations(self):
        db = self.db
        query = f"""
            SELECT DISTINCT
                rf.{ID.RESALE_FLAT_ID},
                rf.{ID.BLOCK},
                rf.{ID.STREET_NAME},
                g.{KEY_NAME.LATITUDE},
                g.{KEY_NAME.LONGITUDE}
            FROM {TABLE_NAME.RESALE_FLATS} rf
            JOIN {TABLE_NAME.RESALE_FLATS_GEOLOCATION} g
              ON g.{ID.BLOCK} = rf.{ID.BLOCK}
             AND g.{ID.STREET_NAME} = rf.{ID.STREET_NAME}
            WHERE g.{KEY_NAME.LATITUDE} IS NOT NULL
              AND g.{KEY_NAME.LONGITUDE} IS NOT NULL
        """

        db.cursor.execute(query)
        return db.cursor.fetchall()
    
    def GetLastGeolocation(self):
        db = self.db
        query = f"SELECT DISTINCT {ID.BLOCK}, {ID.STREET_NAME} FROM {TABLE_NAME.RESALE_FLATS_GEOLOCATION} order by {ID.BLOCK} desc LIMIT 1"
        db.cursor.execute(query)
        return db.cursor.fetchone()

    
    def InitialiseGeolocations(self):
        
        addresses = self.GetDistinctAddresses()
        addresses_count = len(addresses)
        items_per_batch = math.ceil(addresses_count / self.MAX_BATCH_NUM)
        batch_i = self.batch_num - 1
        last_geolocation = self.GetLastGeolocation() or {}

        new_batch = None
        for item in addresses[batch_i * items_per_batch: (batch_i + 1) * items_per_batch]:
            if new_batch != None:
                new_batch.append(item)

            if (item.get(ID.BLOCK) == last_geolocation.get(ID.BLOCK)
                    and item.get(ID.STREET_NAME) ==  last_geolocation.get(ID.STREET_NAME)):
                new_batch = []
            
        
        # print(new_batch)
        GeolocationConverter().OSM_Connect()

        if new_batch == None:
            new_batch = addresses[batch_i * items_per_batch: (batch_i + 1) * items_per_batch]

        self.InitialiseGeolocationsBatch(new_batch)
       
    def InitialiseGeolocationsBatch(self, data):

        db = DbConnector()
        dbc = DbController(db)
      
        for item in data:
            new_data = {}
            block = item[ID.BLOCK]
            street_name = item[ID.STREET_NAME]

            geo = GeolocationConverter().GetOSMGeolocation(block, street_name)
            if geo == None:
                continue

            
           
            new_data[ID.BLOCK] = block
            new_data[ID.STREET_NAME] = street_name
            new_data[KEY_NAME.LATITUDE] =  geo[0]
            new_data[KEY_NAME.LONGITUDE] = geo[1]
            #     item[k] = geolocation[k]
            
            dbc.UpsertData(TABLE_NAME.RESALE_FLATS_GEOLOCATION, new_data)
            with lock:
                self.processed_count += 1
                print(f"{self.processed_count}: Updating blk: {block}, street_name:{street_name} geolocation...")
        
        


    def DeleteGeolocations(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(TABLE_NAME.RESALE_FLATS_GEOLOCATION)
       
        

      
    
   
    
