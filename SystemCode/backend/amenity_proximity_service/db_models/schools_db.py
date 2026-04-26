
from utils.db_connector import DbConnector
from utils.db_controller import DbController
from env import TABLE_NAME


class SchoolsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.SCHOOLS

    def GetAll(self):
        db = self.db
        dbc = DbController(db)
        return dbc.GetAll(self.table_name)
