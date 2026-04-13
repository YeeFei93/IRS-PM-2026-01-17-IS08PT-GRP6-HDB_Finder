from db_models.resale_flats_db import ResaleFlatsDB
from utils.db_connector import DbConnector
from utils.geolocation_converter import GeolocationConverter
from env import ID, KEY_NAME
import threading
import math



lock = threading.Lock()
db = DbConnector()
resale_flats_db = ResaleFlatsDB(db)
resale_flats_geolocations = resale_flats_db.GetGeolocations()
print({14: len(resale_flats_geolocations)})



counter = 0
def UpdateGeolocations(data):
   
    def UpdateGeolocationBatch(data):
        new_data = []
        for item in data:
            geolocation = GeolocationConverter().GetGeolocation(item[ID.BLOCK], item[ID.STREET_NAME])
            for k in geolocation:
                item[k] = geolocation[k]
            
            new_data.append(item)
            with lock:
                global counter
                counter += 1
                print(f"Updating {counter} resale flat geolocation...")
        resale_flats_db.UpdateGeolocations(new_data)

    num_threads = 4
    batch_size =  math.ceil(len(data) / num_threads)
    
    threads = []

    for i in range(0,num_threads):
        t = threading.Thread(target= UpdateGeolocationBatch, args=(data[i * batch_size : (i +1) * batch_size],))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()



UpdateGeolocations(resale_flats_geolocations)

db.Close()
