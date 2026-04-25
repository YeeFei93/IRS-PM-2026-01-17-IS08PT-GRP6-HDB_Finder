


from db_models.resale_flats_mrt_stations import ResaleFlatsMrtStationsDB
from utils.db_connector import DbConnector

db = DbConnector()
rf_sm_db = ResaleFlatsMrtStationsDB(db)
rf_sm_db.DeleteData()
rf_sm_db.InitializeData()