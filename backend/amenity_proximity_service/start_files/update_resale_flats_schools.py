from utils.db_connector import DbConnector
from db_models.resale_flats_schools_db import ResaleFlatsSchoolsDB

db = DbConnector()
rf_s_db = ResaleFlatsSchoolsDB(db)
rf_s_db.DeleteData()
rf_s_db.InitializeData()
