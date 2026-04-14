from utils.db_connector import DbConnector
from db_models.resale_flats_hospitals_db import ResaleFlatsHospitalsDB

db = DbConnector()
rf_h_db = ResaleFlatsHospitalsDB(db)
rf_h_db.DeleteData()
rf_h_db.InitializeData()
db.Close()
