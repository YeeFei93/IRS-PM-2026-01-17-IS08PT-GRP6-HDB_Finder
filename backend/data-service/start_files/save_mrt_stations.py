
from db_models.mrt_stations_db import MrtStationsDB
from utils.db_connector import DbConnector

db = DbConnector()
mrt_lines_db = MrtStationsDB(db)
mrt_lines_db.DeleteData()
data = mrt_lines_db.InitialiseData()
db.Close()
