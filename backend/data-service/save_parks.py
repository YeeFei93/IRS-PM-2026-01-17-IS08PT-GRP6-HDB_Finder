

from db_connector import DbConnector
from db_models.parks_db import ParksDB

db = DbConnector()

parks_db = ParksDB(db)
parks_db.DeleteData()
parks_db.InitialiseData()
db.Close()