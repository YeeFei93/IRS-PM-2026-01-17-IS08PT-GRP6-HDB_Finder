from db_models.shopping_malls_db import ShoppingMallsDB
from utils.db_connector import DbConnector

db = DbConnector()
shopping_malls_db = ShoppingMallsDB(db)
shopping_malls_db.DeleteData()
data = shopping_malls_db.InitialiseData()
db.Close()
