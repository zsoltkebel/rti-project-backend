from fastapi import APIRouter, Form, UploadFile, File, Path
from fastapi.responses import JSONResponse
from typing import List, Union
import uuid
import os
import shutil
import json

router = APIRouter(
    prefix="/artifacts",
)

ARTIFACTS_DIR = os.path.join("uploads", "artifacts")
UPLOAD_BASE = "uploads"


# Endpoints

@router.get("/")
async def read_artifacts():
    artifacts = []

    if not os.path.exists(ARTIFACTS_DIR):
        return JSONResponse(content={"artifacts": []})

    for artifact_id in os.listdir(ARTIFACTS_DIR):
        artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_id)

        if not os.path.isdir(artifact_dir):
            continue

        metadata_file = os.path.join(artifact_dir, "metadata.json")
        if not os.path.exists(metadata_file):
            continue

        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
        except json.JSONDecodeError:
            continue

        num_images = count_items_in_dir(os.path.join(artifact_dir, "images"))
        num_rtis = count_items_in_dir(os.path.join(artifact_dir, "rti"))  # TODO rename rti to rtis

        # get a thumbnail from rti or images
        try:
            rti_id = os.listdir(os.path.join(artifact_dir, "rti"))[0]
            thumbnail_file = os.path.join(artifact_dir, "rti", rti_id, "thumbnail.jpg")
            if not os.path.isfile(thumbnail_file):
                raise Exception()
        except:
            try:
                image_id = os.listdir(os.path.join(artifact_dir, "images"))[0]
                thumbnail_file = os.path.join(artifact_dir, "images", image_id)
                if not os.path.isfile(thumbnail_file):
                    raise Exception()
            except:
                thumbnail_file = ""



        # Build the artifact JSON
        artifact = {
            "id": artifact_id,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "creator": metadata.get("creator", "Unknown"),
            "date": metadata.get("date", ""),
            "copyright": metadata.get("copyright", ""),
            "tags": metadata.get("tags", []),
            "num_images": num_images,
            "num_rtis": num_rtis,
            "thumbnail": thumbnail_file.replace("uploads", "/files"),
        }

        artifacts.append(artifact)

    return {"artifacts": artifacts}


@router.post("/")
async def create_artifact(
    title: str = Form(...),
    description: str = Form(...),
    creator: str = Form(...),
    date: str = Form(...),
    copyright: str = Form(...),
    images: list[UploadFile] = File([])
):
    # Generate a unique artifact ID
    artifact_id = str(uuid.uuid4())

    # Create directories
    artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_id)
    images_dir = os.path.join(artifact_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Save images
    for image_file in images:
        image_path = os.path.join(images_dir, image_file.filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)

    # Save metadata.json
    metadata = {
        "title": title,
        "description": description,
        "creator": creator,
        "date": date,
        "copyright": copyright,
        "images": [f"img/images/{img.filename}" for img in images]
    }
    metadata_path = os.path.join(artifact_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return JSONResponse({"artifact_id": artifact_id, "message": "Upload successful"})


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str = Path(..., regex=r"^[\w\-]+$"),
):
    artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_id)
    metadata_file = os.path.join(artifact_dir, 'metadata.json')

    # Collect all image files at root level
    images = read_images(artifact_id)

    # Collect RTI relightable media
    relightable_media = get_relightable_images(artifact_id)

    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
    except json.JSONDecodeError:
        pass

    print(metadata)
    artifact = {
        "id": artifact_id,
        **metadata,
        "images": images,
        "relightableMedia": relightable_media,
    }
    
    return { "artifact": artifact }


@router.put("/{artifact_id}")
async def put_artifact(
    artifact_id: str = Path(..., regex=r"^[\w\-]+$"),
    title: str = Form(...),
    description: str = Form(...),
    creator: str = Form(...),
    date: str = Form(...),
    copyright: str = Form(...),
    images: list[Union[UploadFile, str]] = File([])
):
    # Create directories
    artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_id)
    images_dir = os.path.join(artifact_dir, "images")
    # os.makedirs(images_dir, exist_ok=True)

    # Save images
    print(images)
    images_to_keep = [os.path.basename(image) for image in images if isinstance(image, str)]
    
    # Delete files
    for filename in os.listdir(images_dir):
        if filename not in images_to_keep:
            file_path = os.path.join(images_dir, filename)
            try:
                os.remove(file_path)
                print(f"Deleted: {filename}")
            except Exception as e:
                print(f"Error deleting {filename}: {e}")

    # Add new image files
    for image_file in images:
        if not isinstance(image_file, str):
            image_path = os.path.join(images_dir, image_file.filename)
            with open(image_path, "wb") as buffer:
                shutil.copyfileobj(image_file.file, buffer)
                print(f"Added: {image_file.filename}")

    # Save metadata.json
    metadata = {
        "title": title,
        "description": description,
        "creator": creator,
        "date": date,
        "copyright": copyright,
    }
    metadata_path = os.path.join(artifact_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return JSONResponse({"artifact_id": artifact_id, "message": "Upload successful"})


@router.post("/rti")
async def upload_relight(
    metadata: str = Form(...),
    files: List[UploadFile] = File(...)
):
    # Generate a unique folder for this upload
    artifact_id = str(uuid.uuid4())
    rti_id = str(uuid.uuid4())
    artifact_folder = os.path.join(ARTIFACTS_DIR, artifact_id)
    relight_folder = os.path.join(artifact_folder, 'rti', rti_id)
    os.makedirs(relight_folder, exist_ok=True)

    # Save metadata JSON
    try:
        metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid metadata JSON"})

    with open(os.path.join(artifact_folder, "metadata.json"), "w") as f:
        json.dump(metadata_dict, f, indent=2)

    # Save uploaded files
    for file in files:
        file_path = os.path.join(relight_folder, file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    return {"artifact_id": artifact_id, "message": "Upload successful"}


# Utils

def is_image_file(filename):
    return any(filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"])

def is_rti_dir(path):
    return os.path.exists(os.path.join(path, "info.json"))

def read_images(artifact_id):
    artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_id)
    images_dir = os.path.join(artifact_dir, "images")
    images = []

    if not os.path.exists(images_dir) or not os.path.isdir(images_dir):
        return images
    
    for file_name in os.listdir(images_dir):
        file_path = os.path.join(images_dir, file_name)
        if os.path.isfile(file_path) and is_image_file(file_name):
            images.append(f"http://localhost:8000/files/artifacts/{artifact_id}/images/{file_name}")  # TODO how should returned url look?
    return images

def count_items_in_dir(dir):
    try:
        with os.scandir(dir) as entries:
            return sum(1 for _ in entries)
    except FileNotFoundError:
        return 0

def get_relightable_images(artifact_id):
    print("hereeee")
    relightable_media = []
    rti_dir = os.path.join(ARTIFACTS_DIR, artifact_id, "rti")

    if not os.path.exists(rti_dir) or not os.path.isdir(rti_dir):
        print("0")
        return relightable_media
    
    for subdir_name in os.listdir(rti_dir):
        print("1")
        subdir_path = os.path.join(rti_dir, subdir_name)
        if os.path.isdir(subdir_path) and is_rti_dir(subdir_path):
            print(2)
            info_url = f"/files/artifacts/{artifact_id}/rti/{subdir_name}/info.json"
            
            thumbnail_path = os.path.join(subdir_path, "thumbnail.jpg")
            if os.path.exists(thumbnail_path):
                thumbnail_url = f"/files/artifacts/{artifact_id}/rti/{subdir_name}/thumbnail.jpg"
            else:
                fallback_thumb_path = os.path.join(subdir_path, f"{subdir_name}.jpg")
                if os.path.exists(fallback_thumb_path):
                    thumbnail_url = f"/files/artifacts/{artifact_id}/rti/{subdir_name}/{subdir_name}.jpg"
                else:
                    thumbnail_url = None

            relightable_entry = {
                "id": subdir_name,
                "type": "relight",
                "url": info_url
            }
            if thumbnail_url:
                relightable_entry["thumbnail"] = thumbnail_url

            relightable_media.append(relightable_entry)

    return relightable_media