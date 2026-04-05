


from db_models.resale_flats_db import ResaleFlatsDB
from db_connector import DbConnector

db = DbConnector()
resale_flats_db = ResaleFlatsDB(db)
resale_flats_db.DeleteData()
data = resale_flats_db.InitializeData()
db.Close()
