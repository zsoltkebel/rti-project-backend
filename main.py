from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Path
from fastapi.responses import JSONResponse
from typing import List, Union
import uuid
import os
import json
import shutil
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow requests from your Vue dev server
origins = [
    "http://localhost:5173",  # Vue dev server
    # add other allowed origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # ✅ Only allow specific dev URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
ARTIFACTS_DIR = os.path.join(UPLOAD_DIR, 'artifacts')
os.makedirs(UPLOAD_DIR, exist_ok=True)

def artifact_dir(id):
    return os.path.join(ARTIFACTS_DIR, id)


from fastapi.staticfiles import StaticFiles
app.mount("/files/artifacts", StaticFiles(directory="uploads/artifacts"), name="artifacts")


@app.post("/upload-relight/")
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


def is_image_file(filename):
    return any(filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"])

def is_rti_dir(path):
    return os.path.exists(os.path.join(path, "info.json"))

@app.get("/artifacts")
def get_artifacts():
    artifacts = []

    if not os.path.exists(ARTIFACTS_DIR):
        return JSONResponse(content={"artifacts": []})

    for artifact_dir_name in os.listdir(ARTIFACTS_DIR):
        artifact_dir = os.path.join(ARTIFACTS_DIR, artifact_dir_name)

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

        artifact_id = artifact_dir_name

        # Collect all image files at root level
        images = []
        for file_name in os.listdir(artifact_dir):
            file_path = os.path.join(artifact_dir, file_name)
            if os.path.isfile(file_path) and is_image_file(file_name):
                images.append(f"/artifacts/{artifact_id}/{file_name}")

        # Collect RTI relightable media
        relightable_media = get_relightable_images(artifact_id)

        # Build the artifact JSON
        artifact = {
            "id": artifact_id,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "images": images,
            "relightableMedia": relightable_media,
            "creator": metadata.get("creator", "Unknown"),
            "date": metadata.get("date", ""),
            "copyright": metadata.get("copyright", ""),
            "tags": metadata.get("tags", []),
        }

        artifacts.append(artifact)

    return {"artifacts": artifacts}

@app.get("/artifact/{id}")
def get_artifact(
    id: str = Path(..., regex=r"^[\w\-]+$"),
):
    artifact_dir = os.path.join(ARTIFACTS_DIR, id)
    metadata_file = os.path.join(artifact_dir, 'metadata.json')

    # Collect all image files at root level
    images = []
    for file_name in os.listdir(os.path.join(artifact_dir, "images")):
        file_path = os.path.join(artifact_dir, "images", file_name)
        if os.path.isfile(file_path) and is_image_file(file_name):
            images.append(f"/artifacts/{id}/images/{file_name}")

    # Collect RTI relightable media
    relightable_media = get_relightable_images(id)

    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
    except json.JSONDecodeError:
        pass

    artifact = {
        "id": id,
        **metadata,
        "images": images,
        "relightableMedia": relightable_media,
    }
    
    return { "artifact": artifact}

def get_relightable_images(artifact_id):
    relightable_media = []
    rti_dir = os.path.join(artifact_dir(artifact_id), "rti")

    if not os.path.exists(rti_dir) or not os.path.isdir(rti_dir):
        return relightable_media

    for subdir_name in os.listdir(rti_dir):
        subdir_path = os.path.join(rti_dir, subdir_name)
        if os.path.isdir(subdir_path) and is_rti_dir(subdir_path):
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


UPLOAD_BASE = "uploads"

@app.post("/artifact/create/")
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

@app.post("/artifact/update/")
async def remove_artifact():
    pass

@app.delete("/artifact/{id}")
async def delete_artifact(
    id: str = Path(..., regex=r"^[\w\-]+$")
):
    artifact_path = os.path.join(ARTIFACTS_DIR, id)

    if not os.path.exists(artifact_path) or not os.path.isdir(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        shutil.rmtree(artifact_path)
        return {"status": "success", "removed": id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove artifact: {str(e)}")
    

@app.post("/artifact/{id}/upload-rti")
async def upload_rti(
    id: str = Path(..., regex=r"^[\w\-]+$"),
    files: list[UploadFile] = File([]),
):
    # Create directories
    rti_id = str(uuid.uuid4())
    artifact_dir = os.path.join(ARTIFACTS_DIR, id)
    images_dir = os.path.join(artifact_dir, "rti", rti_id)
    os.makedirs(images_dir, exist_ok=True)

    # Save images
    for image_file in files:
        image_path = os.path.join(images_dir, image_file.filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)

@app.delete("/artifact/{id}/rti/{rti_id}")
async def delete_rti(
    id: str = Path(..., regex=r"^[\w\-]+$"),  # Artifact ID
    rti_id: str = Path(..., regex=r"^[\w\-]+$"),
):
    rti_path = os.path.join(ARTIFACTS_DIR, id, "rti", rti_id)

    if not os.path.exists(rti_path) or not os.path.isdir(rti_path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        shutil.rmtree(rti_path)
        return {"status": "success", "removed": rti_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove artifact rti: {str(e)}")