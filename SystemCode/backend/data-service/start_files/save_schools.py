
from utils.db_connector import DbConnector
from db_models.schools_db import SchoolsDB

db = DbConnector()

schools_db = SchoolsDB(db)
schools_db.DeleteData()
schools_db.InitialiseData()
db.Close()
