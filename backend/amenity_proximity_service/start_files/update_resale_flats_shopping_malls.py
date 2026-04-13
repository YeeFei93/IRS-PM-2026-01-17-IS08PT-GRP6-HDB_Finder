


from utils.db_connector import DbConnector
from db_models.resale_flats_shopping_malls_db import ResaleFlatsShoppingMallsDB

db = DbConnector()
rf_sm_db = ResaleFlatsShoppingMallsDB(db)
rf_sm_db.DeleteData()
rf_sm_db.InitializeData()