
from datetime import datetime

from utils.db_controller import DbController
from utils.db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
import uuid
import threading
import math
import time
import random

lock = threading.Lock()
class ResaleFlatsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.RESALE_FLATS
        
    def GetAll(self):
        db = self.db
        dbc = DbController(db)
        return dbc.GetAll(self.table_name)
    
    def GetGeolocations(self):
        db = self.db
        query = f"""SELECT * FROM {TABLE_NAME.RESALE_FLATS_GEOLOCATION} a"""
        
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
    
    def UpdateGeolocations(self, data):
        db = self.db
        dbc = DbController(db)
        dbc.UpsertData(TABLE_NAME.RESALE_FLATS_GEOLOCATION, data)
        

      
    
   
    
