from utils.db_connector import DbConnector
from db_models.resale_flats_public_hospitals_db import ResaleFlatsPublicHospitalsDB

db = DbConnector()
rf_h_db = ResaleFlatsPublicHospitalsDB(db)
rf_h_db.DeleteData()
rf_h_db.InitializeData()
db.Close()
