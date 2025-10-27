import os
from typing import List, Optional, Literal, Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId
import requests

from database import db, create_document, get_documents
from schemas import Entry

app = FastAPI(title="NebulaDiary API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utilities
class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        try:
            return str(ObjectId(str(v)))
        except Exception:
            raise ValueError("Invalid ObjectId")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    out = {**doc}
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    return out


@app.get("/")
def read_root():
    return {"message": "NebulaDiary API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# Entry Endpoints
class EntryCreate(Entry):
    pass


class EntryUpdate(BaseModel):
    status: Optional[Literal['Planned', 'Watching', 'Completed', 'Dropped']] = None
    rating: Optional[int] = None
    review: Optional[str] = None


@app.post("/entries")
def create_entry(payload: EntryCreate):
    entry_id = create_document("entry", payload)
    return {"id": entry_id}


@app.get("/entries")
def list_entries(media_type: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = 100):
    filt: Dict[str, Any] = {}
    if media_type:
        filt["media_type"] = media_type
    if status:
        filt["status"] = status
    docs = get_documents("entry", filt, limit)
    return [serialize_doc(d) for d in docs]


@app.patch("/entries/{entry_id}")
def update_entry(entry_id: str, payload: EntryUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = requests.utils.datetime.datetime.utcnow()
    res = db["entry"].update_one({"_id": ObjectId(entry_id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"updated": True}


@app.delete("/entries/{entry_id}")
def delete_entry(entry_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    res = db["entry"].delete_one({"_id": ObjectId(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True}


# Search endpoint (proxy to public APIs)
@app.get("/search")
def search(q: str, media_type: Literal['movie', 'series', 'anime'] = 'movie', limit: int = 10):
    q = q.strip()
    if not q:
        return []

    try:
        results: List[Dict[str, Any]] = []
        if media_type == 'anime':
            # Jikan API (MyAnimeList)
            r = requests.get("https://api.jikan.moe/v4/anime", params={"q": q, "limit": min(limit, 10), "sfw": True}, timeout=10)
            r.raise_for_status()
            for item in r.json().get("data", [])[:limit]:
                results.append({
                    "title": item.get("title"),
                    "year": (item.get("year") or (item.get("aired") or {}).get("prop", {}).get("from", {}).get("year")),
                    "image": (item.get("images", {}).get("jpg", {}) or {}).get("large_image_url") or (item.get("images", {}).get("jpg", {}) or {}).get("image_url"),
                    "external_id": str(item.get("mal_id")),
                    "source": "jikan",
                    "media_type": "anime",
                })
        elif media_type == 'series':
            # TVMaze for shows
            r = requests.get("https://api.tvmaze.com/search/shows", params={"q": q}, timeout=10)
            r.raise_for_status()
            for item in r.json()[:limit]:
                show = item.get("show", {})
                img = show.get("image") or {}
                results.append({
                    "title": show.get("name"),
                    "year": (show.get("premiered") or "")[:4] or None,
                    "image": (img.get("original") or img.get("medium")),
                    "external_id": str(show.get("id")),
                    "source": "tvmaze",
                    "media_type": "series",
                })
        else:
            # iTunes Search for movies
            r = requests.get("https://itunes.apple.com/search", params={"term": q, "media": "movie", "limit": min(limit, 20)}, timeout=10)
            r.raise_for_status()
            for item in r.json().get("results", [])[:limit]:
                results.append({
                    "title": item.get("trackName"),
                    "year": (item.get("releaseDate") or "")[:4] or None,
                    "image": item.get("artworkUrl100"),
                    "external_id": str(item.get("trackId")),
                    "source": "itunes",
                    "media_type": "movie",
                })
        return results
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search failed: {str(e)[:120]}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
