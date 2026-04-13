import csv

from utils.db_connector import DbConnector
from utils.db_controller import DbController
from utils.geolocation_converter import GeolocationConverter
from env import TABLE_NAME, KEY_NAME, ID


class SchoolsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.SCHOOLS

    def EnsureTable(self):
        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {ID.SCHOOL_NAME} VARCHAR(256) NOT NULL,
                {KEY_NAME.LATITUDE} DECIMAL(11, 8) DEFAULT NULL,
                {KEY_NAME.LONGITUDE} DECIMAL(11, 8) DEFAULT NULL,
                PRIMARY KEY ({ID.SCHOOL_NAME})
            )
        """
        self.db.cursor.execute(query)
        self.db.Commit()

    def InitialiseData(self):
        db = self.db
        dbc = DbController(db)
        new_data_arr = []
        self.EnsureTable()
        column_names = dbc.GetColumnNames(self.table_name)
        processed_count = 0

        for item in self.GetRawData():
            if item.get("mainlevel_code") != "PRIMARY":
                continue

            school_name = item.get(ID.SCHOOL_NAME, "").strip()
            if not school_name:
                continue

            geolocation = self._get_school_geolocation(item)
            processed_item = {
                ID.SCHOOL_NAME: school_name,
                KEY_NAME.LATITUDE: geolocation.get(KEY_NAME.LATITUDE),
                KEY_NAME.LONGITUDE: geolocation.get(KEY_NAME.LONGITUDE),
            }
            processed = dbc.PreprocessData(processed_item, column_names=column_names)
            new_data_arr.append(processed)

            processed_count += 1
            print(f"Processing {processed_count} primary schools...")

        dbc.InsertData(self.table_name, new_data_arr)

    def _get_school_geolocation(self, item):
        converter = GeolocationConverter()
        address = " ".join(str(item.get("address", "")).split())
        school_name = str(item.get(ID.SCHOOL_NAME, "")).strip()

        if address:
            geolocation = converter.GetGeolocation(address)
            if geolocation:
                return geolocation

        if school_name and address:
            geolocation = converter.GetGeolocation(f"{school_name} {address}")
            if geolocation:
                return geolocation

        if school_name:
            return converter.GetGeolocation(school_name)

        return {}

    def GetRawData(self):
        data = []
        with open("./raw-data/schools.csv", mode="r", encoding="utf-8") as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                data.append(row)
        return data

    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        self.EnsureTable()
        dbc.DeleteData(self.table_name)
