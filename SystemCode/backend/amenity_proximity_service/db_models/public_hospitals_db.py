from utils.db_connector import DbConnector
from utils.db_controller import DbController
from env import TABLE_NAME


class PublicHospitalsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.PUBLIC_HOSPITALS

    def GetAll(self):
        dbc = DbController(self.db)
        return dbc.GetAll(self.table_name)
