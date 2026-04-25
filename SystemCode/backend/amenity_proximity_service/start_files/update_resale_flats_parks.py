


from utils.db_connector import DbConnector
from db_models.resale_flats_parks_db import ResaleFlatsParksDB

db = DbConnector()
rf_p_db = ResaleFlatsParksDB(db)
rf_p_db.DeleteData()
rf_p_db.InitializeData()