

from db_connector import DbConnector
from db_controller import DbController
from env import TABLE_NAME


class ParksDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.PARKS
        
    def GetAll(self):
        db = self.db
        dbc = DbController(db)
        return dbc.GetAll(self.table_name)