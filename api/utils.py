from fastapi import UploadFile
import shutil
import os


def upload_files(dest: str, files: list[UploadFile]):
    for file in files:
        file_path = os.path.join(dest, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            print(f"Added: {file.filename}")
