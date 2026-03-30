
from csv_to_json import CsvToJson
from db_controller import DbController
from db_connector import DbConnector
class ResaleFlatsModel:
    def __init__(self, db: DbConnector):
        self.db = db
        res = DbController(db).PreprocessData("resale_flats", 
                                              [{"id2": "AAA", "BBB":"CCC"},
                                              {"id": "AAA2", "BBB":"CCC3"}])
        print(res)
        pass


    def GetRawData(self):
        return CsvToJson("./raw-data/hdb-resale-price").data
    