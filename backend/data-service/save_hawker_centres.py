


from db_models.hawker_centres_db import HawkerCentresDB
from db_connector import DbConnector

db = DbConnector()

HawkerCentresDB(db).InitialiseData()
db.Close()