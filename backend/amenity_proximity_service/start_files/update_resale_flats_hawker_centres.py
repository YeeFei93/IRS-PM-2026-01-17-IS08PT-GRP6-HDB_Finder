from utils.db_connector import DbConnector
from db_models.resale_flats_hawker_centres_db import ResaleFlatsHawkerCentresDB

db = DbConnector()
rf_hc_db = ResaleFlatsHawkerCentresDB(db)
rf_hc_db.DeleteData()
rf_hc_db.InitializeData()