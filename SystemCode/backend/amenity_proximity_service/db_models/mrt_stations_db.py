

from utils.db_connector import DbConnector
from utils.db_controller import DbController
from utils.db_controller import DbController
from env import TABLE_NAME


class MrtStationsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.MRT_STATIONS
        
    def GetExits(self):
        db = self.db
        dbc = DbController(db)
        return dbc.GetAll(TABLE_NAME.MRT_STATIONS_EXITS)