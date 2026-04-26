import csv
import json
import os

json_file = "data.json"


class GeojsonToJson:
    def __init__(self, source_folder_path):
        self.source_folder_path = source_folder_path
        file_path = self.GetFilePath()

        data = []
        with open(file_path, "r") as f:
            data = json.load(f)

        self.data = data

    def GetFilePath(self):
        files = [f for f in os.listdir(self.source_folder_path) if os.path.isfile(os.path.join(self.source_folder_path, f))]

        if files:
            first_file = files[0]
            print(first_file)
            return self.source_folder_path + "/" + first_file
        else:
            print("No files found")
        
