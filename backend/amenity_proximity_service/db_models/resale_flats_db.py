
from datetime import datetime

from db_controller import DbController
from db_connector import DbConnector
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
        query = f"""SELECT * FROM {TABLE_NAME.RESALE_FLATS_GEOLOCATION} a
                    LEFT JOIN {TABLE_NAME.RESALE_FLATS} b
                    ON a.{KEY_NAME.BLOCK} = b.{KEY_NAME.BLOCK}
                    AND a.{KEY_NAME.STREET_NAME} = b.{KEY_NAME.STREET_NAME} """
        
        db.cursor.execute(query)
        return db.cursor.fetchall()
    
    def UpdateGeolocations(self, data):
        db = self.db
        dbc = DbController(db)
        dbc.UpsertData(TABLE_NAME.RESALE_FLATS_GEOLOCATION, data)
        

      
    
   
    