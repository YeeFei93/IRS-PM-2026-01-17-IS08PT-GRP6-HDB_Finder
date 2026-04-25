from datetime import datetime
from utils.csv_to_json import CsvToJson
from utils.db_controller import DbController
from utils.db_connector import DbConnector
from env import TABLE_NAME, KEY_NAME, ID
from utils.geojson_to_json import GeojsonToJson

class MrtStationsDB:
    def __init__(self, db: DbConnector):
        self.db = db
        self.table_name = TABLE_NAME.MRT_STATIONS

    def InitialiseData(self):
        self.InitialiseLines()
        self.InitialiseExits()

        

    def InitialiseLines(self):
        db = self.db
        dbc = DbController(db)

        new_mrt_stations = []
        new_mrt_lines = []
        new_mrt_stations_lines = []
       
        processed_count = 0
        for item in self.GetLinesRawData():  
            
            mrt_line_name = str(item.get("mrt_line_english")).upper()
            if "LRT" in mrt_line_name: 
                continue
            if "CHANGI AIRPORT BRANCH LINE" in mrt_line_name: 
                continue
            if "CIRCLE LINE EXTENSION" in mrt_line_name: 
                continue

            mrt_station = {}
            mrt_line = {}
            mrt_stations_line = {}

            mrt_station_name = f"{str(item["mrt_station_english"]).upper()} MRT STATION"
            mrt_station[ID.MRT_STATION_NAME] = mrt_station_name
            new_mrt_stations.append(mrt_station)

            mrt_line[ID.MRT_LINE_NAME] = mrt_line_name
            new_mrt_lines.append(mrt_line)

            mrt_stations_line[ID.MRT_STATION_NAME] = mrt_station_name
            mrt_stations_line[ID.MRT_LINE_NAME] = mrt_line_name
            new_mrt_stations_lines.append(mrt_stations_line)

            processed_count +=1
            print(f"Processing {processed_count} mrt station lines...")

        dbc.InsertData(self.table_name, new_mrt_stations)
        dbc.InsertData(TABLE_NAME.MRT_LINES, new_mrt_lines)
        dbc.InsertData(TABLE_NAME.MRT_STATIONS_LINES, new_mrt_stations_lines)

    def InitialiseExits(self):
        db = self.db
        dbc = DbController(db)

        new_mrt_stations = []
        new_mrt_stations_exits = []


        processed_count = 0
        for item in self.GetStationsRawData()["features"]:  
            mrt_station_name = str(item["properties"]["STATION_NA"]).upper()
            if "MRT STATION" not in mrt_station_name:
                continue

            mrt_station = {}
            mrt_stations_exit = {}

            mrt_station[ID.MRT_STATION_NAME] = mrt_station_name
            new_mrt_stations.append(mrt_station)

            mrt_stations_exit[ID.MRT_STATION_NAME] = mrt_station_name
            mrt_stations_exit[KEY_NAME.EXIT_CODE] = str(item["properties"]["EXIT_CODE"]).upper()
            mrt_stations_exit[KEY_NAME.LATITUDE] = item["geometry"]["coordinates"][1]
            mrt_stations_exit[KEY_NAME.LONGITUDE] = item["geometry"]["coordinates"][0]
            new_mrt_stations_exits.append(mrt_stations_exit)


            processed_count +=1
            print(f"Processing {processed_count} mrt station exits...")
        
        dbc.InsertData(self.table_name, new_mrt_stations)
        dbc.InsertData(TABLE_NAME.MRT_STATIONS_EXITS, new_mrt_stations_exits)

    def GetLinesRawData(self):
        return CsvToJson("./raw-data/mrt-stations-lines").data
    
    def GetStationsRawData(self):
        return GeojsonToJson("./raw-data/mrt-stations-exits").data
    
    def DeleteData(self):
        db = self.db
        dbc = DbController(db)
        dbc.DeleteData(self.table_name)
        dbc.DeleteData(TABLE_NAME.MRT_LINES)
        
    