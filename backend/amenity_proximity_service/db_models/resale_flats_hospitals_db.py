import math
import threading

from db_models.public_hospitals_db import PublicHospitalsDB
from db_models.resale_flats_db import ResaleFlatsDB
from env import TABLE_NAME, KEY_NAME, ID
from utils.db_connector import DbConnector
from utils.db_controller import DbController
from utils.geolocation_converter import GeolocationConverter

lock = threading.Lock()


class ResaleFlatsHospitalsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.processed_count = 0
        self.distance_limit = 3
        self.table_name = TABLE_NAME.RESALE_FLATS_PUBLIC_HOSPITALS

    def EnsureTable(self):
        self.db.cursor.execute(f"SHOW TABLES LIKE %s", (self.table_name,))
        if self.db.cursor.fetchone():
            self.db.cursor.execute(f"SHOW COLUMNS FROM {self.table_name}")
            existing_columns = {row["Field"] for row in self.db.cursor.fetchall()}
            expected_columns = {
                ID.BLOCK,
                ID.STREET_NAME,
                ID.HOSPITAL_NAME,
                KEY_NAME.DISTANCE,
            }
            if existing_columns != expected_columns:
                self.db.cursor.execute(f"DROP TABLE IF EXISTS {self.table_name}")

        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {ID.BLOCK} VARCHAR(16) NOT NULL,
                {ID.STREET_NAME} VARCHAR(256) NOT NULL,
                {ID.HOSPITAL_NAME} VARCHAR(256) NOT NULL,
                {KEY_NAME.DISTANCE} FLOAT DEFAULT NULL,
                PRIMARY KEY ({ID.BLOCK}, {ID.STREET_NAME}, {ID.HOSPITAL_NAME})
            )
        """
        self.db.cursor.execute(query)
        self.db.Commit()

    def InitializeData(self):
        self.EnsureTable()
        db = DbConnector()
        resale_flats_geos = ResaleFlatsDB(db).GetGeolocations()
        hospital_geos = PublicHospitalsDB(db).GetAll()

        num_threads = 4
        batch_size = math.ceil(len(resale_flats_geos) / num_threads) if resale_flats_geos else 0
        threads = []

        for i in range(0, num_threads):
            start_index = i * batch_size
            end_index = (i + 1) * batch_size
            t = threading.Thread(
                target=self.InitializeBatch,
                args=(resale_flats_geos[start_index:end_index], hospital_geos),
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    def InitializeBatch(self, resale_flats_geos, hospital_geos):
        db = DbConnector()
        dbc = DbController(db)
        new_data_arr = []

        for flat in resale_flats_geos:
            for hospital in hospital_geos:
                hospital_lat = hospital.get(KEY_NAME.LATITUDE)
                hospital_lng = hospital.get(KEY_NAME.LONGITUDE)
                if hospital_lat is None or hospital_lng is None:
                    continue

                distance = GeolocationConverter().CalculateDistance(
                    flat[KEY_NAME.LATITUDE],
                    flat[KEY_NAME.LONGITUDE],
                    hospital_lat,
                    hospital_lng,
                )
                if distance <= self.distance_limit:
                    new_data_arr.append(
                        {
                            ID.BLOCK: flat[ID.BLOCK],
                            ID.STREET_NAME: flat[ID.STREET_NAME],
                            ID.HOSPITAL_NAME: hospital[ID.HOSPITAL_NAME],
                            KEY_NAME.DISTANCE: distance,
                        }
                    )
                    with lock:
                        self.processed_count += 1
                        print(
                            f"Processing {self.processed_count} resale flats to public hospitals distance..."
                        )

        if new_data_arr:
            dbc.UpsertData(self.table_name, new_data_arr)
            print("Successfully saved.")
        db.Close()

    def DeleteData(self):
        dbc = DbController(self.db)
        self.EnsureTable()
        dbc.DeleteData(self.table_name)
