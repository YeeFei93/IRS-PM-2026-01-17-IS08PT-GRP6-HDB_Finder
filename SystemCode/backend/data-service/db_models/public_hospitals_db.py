import csv
import re

from utils.db_connector import DbConnector
from utils.db_controller import DbController
from utils.geolocation_converter import GeolocationConverter
from env import TABLE_NAME, KEY_NAME, ID


_HOSPITAL_SEARCH_ALIASES = {
    "Kandang Kerbau Women's & Children's Hospital": [
        "KK Women's and Children's Hospital",
        "KK Women's & Children's Hospital",
    ],
    "Institute Of Mental Health / Woodbridge Hospital": [
        "Institute of Mental Health",
        "Woodbridge Hospital",
    ],
}

_HOSPITALS_TO_NEGLECT = [
    "Communicable Disease Centre",
    "Institute Of Mental Health",
    "National Centre For Infectious Diseases",
]


class PublicHospitalsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.PUBLIC_HOSPITALS

    def EnsureTable(self):
        self.db.cursor.execute(f"SHOW TABLES LIKE %s", (self.table_name,))
        if self.db.cursor.fetchone():
            self.db.cursor.execute(f"SHOW COLUMNS FROM {self.table_name}")
            existing_columns = {row[0] for row in self.db.cursor.fetchall()}
            expected_columns = {
                ID.HOSPITAL_NAME,
                KEY_NAME.LATITUDE,
                KEY_NAME.LONGITUDE,
            }
            if existing_columns != expected_columns:
                self.db.cursor.execute(f"DROP TABLE IF EXISTS {self.table_name}")

        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {ID.HOSPITAL_NAME} VARCHAR(256) NOT NULL,
                {KEY_NAME.LATITUDE} DECIMAL(11, 8) DEFAULT NULL,
                {KEY_NAME.LONGITUDE} DECIMAL(11, 8) DEFAULT NULL,
                PRIMARY KEY ({ID.HOSPITAL_NAME})
            )
        """
        self.db.cursor.execute(query)
        self.db.Commit()

    def InitialiseData(self):
        dbc = DbController(self.db)
        new_data_arr = []
        processed_count = 0
        self.EnsureTable()

        for hospital_name in self.GetRawData():
            geolocation = self._get_hospital_geolocation(hospital_name)
            new_data_arr.append(
                {
                    ID.HOSPITAL_NAME: hospital_name,
                    KEY_NAME.LATITUDE: geolocation.get(KEY_NAME.LATITUDE),
                    KEY_NAME.LONGITUDE: geolocation.get(KEY_NAME.LONGITUDE),
                }
            )
            processed_count += 1
            print(f"Processing {processed_count} public hospitals...")

        dbc.InsertData(self.table_name, new_data_arr)

    def _get_hospital_geolocation(self, hospital_name):
        converter = GeolocationConverter()
        for candidate in self._iter_search_candidates(hospital_name):
            results = converter.SearchGeolocations(candidate)
            geolocation = self._pick_best_result(converter, hospital_name, results)
            if geolocation:
                return geolocation
        return {}

    def _pick_best_result(self, converter, hospital_name, results):
        if not results:
            return {}

        variants = {
            self._normalize_name(hospital_name),
            *(self._normalize_name(alias) for alias in _HOSPITAL_SEARCH_ALIASES.get(hospital_name, [])),
        }
        scored_results = []
        for result in results:
            score = self._score_result(result, variants)
            if score > 0:
                scored_results.append((score, result))

        if not scored_results:
            return {}

        best_score, best_result = max(
            scored_results,
            key=lambda item: (
                item[0],
                item[1].get("POSTAL") != "NIL",
                -len(self._normalize_name(item[1].get("SEARCHVAL", ""))),
            ),
        )
        if best_score < 70:
            return {}

        return converter.ToGeolocation(best_result)

    def _score_result(self, result, variants):
        search_val = self._normalize_name(result.get("SEARCHVAL", ""))
        building = self._normalize_name(result.get("BUILDING", ""))
        address = self._normalize_name(result.get("ADDRESS", ""))
        all_fields = [search_val, building, address]
        score = 0

        for variant in variants:
            if not variant:
                continue
            if search_val == variant or building == variant:
                score = max(score, 100)
            elif search_val.startswith(variant) or building.startswith(variant):
                score = max(score, 95)
            elif any(variant in field for field in all_fields):
                score = max(score, 85)
            else:
                tokens = [token for token in variant.split() if token not in {"AND", "OF", "THE"}]
                if tokens and all(any(token in field for field in all_fields) for token in tokens):
                    score = max(score, 75)

        search_text = f"{search_val} {building}"
        if any(
            noise_term in search_text
            for noise_term in (
                "TAXI STAND",
                "HISTORIC SITE",
                "MUSEUM",
                "CHILD CARE",
                "DEPARTMENT",
            )
        ):
            score -= 20

        return score

    def _normalize_name(self, value):
        cleaned_value = str(value).upper()
        cleaned_value = cleaned_value.replace("&", " AND ")
        cleaned_value = cleaned_value.replace("/", " ")
        cleaned_value = cleaned_value.replace("'", "")
        cleaned_value = re.sub(r"[^A-Z0-9 ]+", " ", cleaned_value)
        return " ".join(cleaned_value.split())

    def _iter_search_candidates(self, hospital_name):
        seen = set()
        candidates = [hospital_name]
        candidates.extend(_HOSPITAL_SEARCH_ALIASES.get(hospital_name, []))

        normalized_ampersand = hospital_name.replace("&", "and")
        if normalized_ampersand != hospital_name:
            candidates.append(normalized_ampersand)

        normalized_slash = hospital_name.replace("/", " ")
        if normalized_slash != hospital_name:
            candidates.append(" ".join(normalized_slash.split()))
            candidates.extend(
                part.strip()
                for part in hospital_name.split("/")
                if part.strip()
            )

        for candidate in candidates:
            cleaned_candidate = " ".join(str(candidate).split())
            if cleaned_candidate and cleaned_candidate not in seen:
                seen.add(cleaned_candidate)
                yield cleaned_candidate

    def GetRawData(self):
        hospital_names = []
        seen = set()
        with open(
            "./raw-data/public-hospitals/AdmissionsToPublicSectorHospitalsMonthly.csv",
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            csv_reader = csv.reader(file)
            next(csv_reader, None)
            next(csv_reader, None)

            for row in csv_reader:
                if not row:
                    continue
                hospital_name = " ".join(str(row[0]).split())
                if hospital_name in _HOSPITALS_TO_NEGLECT:
                    continue
                if not hospital_name or hospital_name.lower() == "na":
                    continue
                if hospital_name not in seen:
                    seen.add(hospital_name)
                    hospital_names.append(hospital_name)

        return hospital_names

    def DeleteData(self):
        dbc = DbController(self.db)
        self.EnsureTable()
        dbc.DeleteData(self.table_name)
