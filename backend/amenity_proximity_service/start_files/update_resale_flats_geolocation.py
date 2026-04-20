from db_models.resale_flats_db import ResaleFlatsDB
from utils.db_connector import DbConnector
from utils.geolocation_converter import GeolocationConverter
from env import ID, KEY_NAME
import threading
import math



lock = threading.Lock()
db = DbConnector()
resale_flats_db = ResaleFlatsDB(db)
#resale_flats_db.DeleteGeolocations()
resale_flats_db.batch_num = 4
resale_flats_geolocations = resale_flats_db.InitialiseGeolocations()
db.Close()
