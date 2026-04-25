import csv
import json
import os

json_file = "data.json"


class CsvToJson:
    def __init__(self, source_folder_path):
        self.source_folder_path = source_folder_path

        csv_path = self.GetFilePath()
        data = []
        with open(csv_path, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                data.append(row)

        data.append(row)
        self.data = data

    def GetFilePath(self):
        files = [f for f in os.listdir(self.source_folder_path) if os.path.isfile(os.path.join(self.source_folder_path, f))]

        if files:
            first_file = files[0]
            print(first_file)
            return self.source_folder_path + "/" + first_file
        else:
            print("No files found")
        
