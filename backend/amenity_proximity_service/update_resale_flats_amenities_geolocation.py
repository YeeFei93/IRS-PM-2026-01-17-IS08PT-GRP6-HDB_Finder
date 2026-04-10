


from db_connector import DbConnector
from db_models import hawker_centres_db
from db_models.hawker_centres_db import HawkerCentresDB
from db_models.resale_flats_db import ResaleFlatsDB
from db_models.resale_flats_hawker_centres_db import ResaleFlatsHawkerCentresDB
from geolocation_converter import GeolocationConverter

db = DbConnector()
ResaleFlatsHawkerCentresDB(db).InitializeData()
# dist = GeolocationConverter().CalculateDistance(1.30367135, 103.86447866, 1.31190696, 103.75912802)
# print(dist)