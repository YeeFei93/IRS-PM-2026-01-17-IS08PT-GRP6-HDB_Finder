from utils.db_connector import DbConnector
from db_models.public_hospitals_db import PublicHospitalsDB

db = DbConnector()

public_hospitals_db = PublicHospitalsDB(db)
public_hospitals_db.DeleteData()
public_hospitals_db.InitialiseData()
db.Close()
