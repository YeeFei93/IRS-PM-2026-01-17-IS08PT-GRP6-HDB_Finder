
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from db_models.resale_flats_db import ResaleFlatsDB
from db_models.schools_db import SchoolsDB
from env import TABLE_NAME, KEY_NAME, ID
import threading
import math

from utils.geolocation_converter import GeolocationConverter

lock = threading.Lock()


class ResaleFlatsSchoolsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.distance_limit = 1
        self.table_name = TABLE_NAME.RESALE_FLATS_SCHOOLS

    def EnsureTable(self):
        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {ID.BLOCK} VARCHAR(16) NOT NULL,
                {ID.STREET_NAME} VARCHAR(256) NOT NULL,
                {ID.SCHOOL_NAME} VARCHAR(256) NOT NULL,
                {KEY_NAME.DISTANCE} FLOAT DEFAULT NULL,
                PRIMARY KEY ({ID.BLOCK}, {ID.STREET_NAME}, {ID.SCHOOL_NAME})
            )
        """
        self.db.cursor.execute(query)
        for column_name in (KEY_NAME.LATITUDE, KEY_NAME.LONGITUDE):
            self.db.cursor.execute(f"SHOW COLUMNS FROM {self.table_name} LIKE %s", (column_name,))
            if self.db.cursor.fetchone():
                self.db.cursor.execute(f"ALTER TABLE {self.table_name} DROP COLUMN {column_name}")
        self.db.Commit()

    def InitializeData(self):
        self.EnsureTable()
        db = DbConnector()
        resale_flats_geos = ResaleFlatsDB(db).GetGeolocations()
        schools_geos = SchoolsDB(db).GetAll()

        num_threads = 4
        batch_size = math.ceil(len(resale_flats_geos) / num_threads)
        threads = []

        for i in range(0, num_threads):
            t = threading.Thread(
                target=self.InitializeBatch,
                args=(resale_flats_geos[i * batch_size: (i + 1) * batch_size], schools_geos),
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    def InitializeBatch(self, resale_flats_geos, schools_geos):
        db = DbConnector()
        dbc = DbController(db)
        new_data_arr = []

        for flat in resale_flats_geos:
            flat_lat = flat.get(KEY_NAME.LATITUDE)
            flat_lng = flat.get(KEY_NAME.LONGITUDE)
            if flat_lat is None or flat_lng is None:
                continue

            for school in schools_geos:
                school_lat = school.get(KEY_NAME.LATITUDE)
                school_lng = school.get(KEY_NAME.LONGITUDE)
                if school_lat is None or school_lng is None:
                    continue

                distance = GeolocationConverter().CalculateDistance(
                    flat_lat,
                    flat_lng,
                    school_lat,
                    school_lng,
                )
                if distance <= self.distance_limit:
                    new_data = {
                        ID.BLOCK: flat[ID.BLOCK],
                        ID.STREET_NAME: flat[ID.STREET_NAME],
                        ID.SCHOOL_NAME: school[ID.SCHOOL_NAME],
                        KEY_NAME.DISTANCE: distance,
                    }
                    new_data_arr.append(new_data)
                    with lock:
                        self.processed_count += 1
                        print(f"Processing {self.processed_count} resale flats to schools distance...")

        dbc.UpsertData(self.table_name, new_data_arr)
        print("Successfully saved.")
        db.Close()

    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        self.EnsureTable()
        dbc.DeleteData(self.table_name)
