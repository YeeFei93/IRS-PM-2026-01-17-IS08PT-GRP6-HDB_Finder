


from db_models.resale_flats_model import ResaleFlatsModel
from db_connector import DbConnector

db = DbConnector()
data = ResaleFlatsModel(db).InitializeData()
db.Close()
