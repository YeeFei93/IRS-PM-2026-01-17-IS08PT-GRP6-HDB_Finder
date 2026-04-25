


from db_models.hawker_centres_db import HawkerCentresDB
from utils.db_connector import DbConnector

db = DbConnector()

hawker_centre_db = HawkerCentresDB(db)
hawker_centre_db.DeleteData()
hawker_centre_db.InitialiseData()
db.Close()