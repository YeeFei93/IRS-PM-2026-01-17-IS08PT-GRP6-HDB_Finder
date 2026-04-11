


from db_connector import DbConnector
from db_models import hawker_centres_db
from db_models.hawker_centres_db import HawkerCentresDB
from db_models.resale_flats_db import ResaleFlatsDB
from db_models.resale_flats_hawker_centres_db import ResaleFlatsHawkerCentresDB
from geolocation_converter import GeolocationConverter

db = DbConnector()
rf_hc_db = ResaleFlatsHawkerCentresDB(db)
rf_hc_db.DeleteData()
rf_hc_db.InitializeData()