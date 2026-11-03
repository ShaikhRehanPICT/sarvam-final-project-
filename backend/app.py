import os, json, sqlite3, uuid, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader

load_dotenv()
DB = Path(__file__).with_name("workbench.db")
UPLOADS = Path(__file__).with_name("uploads")
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="OSINT Fusion Workbench API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS documents(
          id TEXT PRIMARY KEY, title TEXT, source_type TEXT, source_label TEXT,
          language TEXT, content TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS entities(
          id TEXT PRIMARY KEY, document_id TEXT, name TEXT, entity_type TEXT,
          evidence TEXT, status TEXT DEFAULT 'pending', created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS relations(
          id TEXT PRIMARY KEY, document_id TEXT, source TEXT, target TEXT,
          relation TEXT, evidence TEXT, status TEXT DEFAULT 'pending'
        );
        """)
init_db()

class TextInput(BaseModel):
    title: str
    source_label: str = "User-provided public/authorized source"
    content: str
    language: str = "auto"

class ReviewInput(BaseModel):
    status: str

def rows(query, args=()):
    with connect() as c:
        return [dict(r) for r in c.execute(query, args).fetchall()]

def sarvam_client():
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "SARVAM_API_KEY is not configured. Add it to backend/.env and restart.")
    try:
        from sarvamai import SarvamAI
        return SarvamAI(api_subscription_key=key)
    except Exception as e:
        raise HTTPException(500, f"Sarvam SDK initialization failed: {e}")

def parse_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return a JSON object")
    return json.loads(text[start:end+1])

def analyze_with_sarvam(content):
    client = sarvam_client()
    prompt = """
Analyze this public/authorized source for a research demo. Return ONLY valid JSON:
{
 "language":"detected language or unknown",
 "summary":"brief neutral summary",
 "entities":[{"name":"literal entity name","type":"PERSON|ORG|LOCATION|EVENT|DATE","evidence":"short exact supporting quote"}],
 "relations":[{"source":"entity name","target":"entity name","relation":"neutral relation label","evidence":"short exact supporting quote"}],
 "signals":[{"title":"possible cross-source lead","explanation":"why it may merit review","evidence":"what this source actually says"}]
}
Rules: extract only explicitly mentioned entities; do not infer identity, guilt, intent, sensitive traits, or private details. Do not turn co-occurrence into a factual relationship. Use cautious language. Keep evidence quotes short and verbatim. Signals are hypotheses, not conclusions. Limit entities to 25, relations to 25, signals to 5.
SOURCE:
""" + content[:14000]
    try:
        response = client.chat.completions(
            model=os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b"),
            messages=[
                {"role": "system", "content": "You are a careful multilingual document-analysis assistant. Preserve uncertainty and evidence provenance."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        raw = response.choices[0].message.content
        return parse_json_response(raw)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Sarvam analysis failed: {e}")

@app.get("/api/health")
def health():
    return {"ok": True, "sarvam_configured": bool(os.getenv("SARVAM_API_KEY", "").strip())}

@app.get("/api/documents")
def list_documents():
    return rows("SELECT id,title,source_type,source_label,language,created_at FROM documents ORDER BY created_at DESC")

@app.post("/api/documents")
def add_text(item: TextInput):
    if not item.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    if len(item.content) > 50000:
        raise HTTPException(413, "Text is too long (50,000 character limit)")
    did = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with connect() as c:
        c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                  (did, item.title[:160], "text", item.source_label[:200], item.language, item.content, now))
    return {"id": did, "message": "Source saved. Run analysis when ready."}

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    name = file.filename or "uploaded-file"
    ext = Path(name).suffix.lower()
    if ext not in [".txt", ".md", ".pdf"]:
        raise HTTPException(400, "Only TXT, MD and text-based PDF files are supported.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Maximum upload size is 5 MB.")
    try:
        if ext == ".pdf":
            temp = UPLOADS / f"{uuid.uuid4()}.pdf"
            temp.write_bytes(data)
            content = "\n".join(p.extract_text() or "" for p in PdfReader(str(temp)).pages)
            temp.unlink(missing_ok=True)
        else:
            content = data.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")
    return add_text(TextInput(title=name, content=content, source_label="User-uploaded; authorization attested by uploader"))

@app.post("/api/audio/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Accept only audio supplied by the user and authorized for processing.
    ext = Path(file.filename or "").suffix.lower()
    allowed = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
    if ext not in allowed:
        raise HTTPException(400, "Supported audio: WAV, MP3, M4A, OGG, FLAC, WEBM")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Maximum audio size is 15 MB.")
    client = sarvam_client()
    tmp = UPLOADS / f"{uuid.uuid4()}{ext}"
    tmp.write_bytes(data)
    try:
        result = client.speech_to_text.transcribe(file=open(tmp, "rb"), model="saaras:v4")
        transcript = result.transcript
        lang = getattr(result, "language_code", "unknown")
    except Exception as e:
        raise HTTPException(502, f"Sarvam transcription failed: {e}")
    finally:
        tmp.unlink(missing_ok=True)
    saved = add_text(TextInput(title=f"Audio transcript: {file.filename}", content=transcript,
                               source_label="User-provided authorized/demo audio transcript", language=lang))
    return {"id": saved["id"], "transcript": transcript, "language": lang}

@app.post("/api/analyze/{document_id}")
def analyze_document(document_id: str):
    doc = rows("SELECT * FROM documents WHERE id=?", (document_id,))
    if not doc:
        raise HTTPException(404, "Source not found")
    result = analyze_with_sarvam(doc[0]["content"])
    now = datetime.now(timezone.utc).isoformat()
    with connect() as c:
        c.execute("UPDATE documents SET language=? WHERE id=?", (result.get("language", "unknown"), document_id))
        for e in result.get("entities", [])[:25]:
            if not e.get("name") or not e.get("type"): continue
            c.execute("INSERT INTO entities VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), document_id, str(e["name"])[:160], str(e["type"])[:30],
                 str(e.get("evidence",""))[:500], "pending", now))
        for r in result.get("relations", [])[:25]:
            if not r.get("source") or not r.get("target"): continue
            c.execute("INSERT INTO relations VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), document_id, str(r["source"])[:160], str(r["target"])[:160],
                 str(r.get("relation","mentioned_with"))[:80], str(r.get("evidence",""))[:500], "pending"))
    # Signal candidates are returned with source-specific evidence; not stored as verified facts.
    return {"document_id": document_id, "summary": result.get("summary",""),
            "language": result.get("language","unknown"), "signals": result.get("signals",[])}

@app.get("/api/entities")
def get_entities():
    return rows("""SELECT e.*, d.title AS source_title FROM entities e
                   JOIN documents d ON d.id=e.document_id ORDER BY e.created_at DESC""")

@app.get("/api/relations")
def get_relations():
    return rows("""SELECT r.*, d.title AS source_title FROM relations r
                   JOIN documents d ON d.id=r.document_id ORDER BY r.rowid DESC""")

@app.get("/api/graph")
def graph():
    entities = get_entities()
    rels = get_relations()
    nodes = {}
    for e in entities:
        key = e["name"].strip().lower()
        if key not in nodes:
            nodes[key] = {"data":{"id":key, "label":e["name"], "kind":e["entity_type"], "status":e["status"]}}
    edges = []
    for r in rels:
        a, b = r["source"].strip().lower(), r["target"].strip().lower()
        if a not in nodes:
            nodes[a] = {"data":{"id":a,"label":r["source"],"kind":"UNRESOLVED","status":"pending"}}
        if b not in nodes:
            nodes[b] = {"data":{"id":b,"label":r["target"],"kind":"UNRESOLVED","status":"pending"}}
        edges.append({"data":{"id":r["id"],"source":a,"target":b,"label":r["relation"],"status":r["status"]}})
    return {"nodes":list(nodes.values()),"edges":edges}

@app.get("/api/signals")
def signals():
    # Explainable heuristic: repeated co-mentions across distinct source documents.
    entities = rows("""SELECT name, COUNT(DISTINCT document_id) AS source_count,
                       GROUP_CONCAT(DISTINCT document_id) AS source_ids
                       FROM entities WHERE status='approved' GROUP BY lower(name)
                       HAVING COUNT(DISTINCT document_id)>=2 ORDER BY source_count DESC""")
    out = []
    for e in entities:
        ids = e["source_ids"].split(",")
        docs = rows("SELECT id,title FROM documents WHERE id IN (" + ",".join("?"*len(ids)) + ")", ids)
        # Heuristic score is a transparent prioritization aid, not a truth probability.
        score = min(90, 40 + 15 * (e["source_count"] - 1))
        out.append({"label":e["name"],"source_count":e["source_count"],"score":score,
                    "interpretation":"Repeated approved mention across independent source records; review context and possible name ambiguity.",
                    "sources":docs})
    return out

@app.post("/api/entities/{entity_id}/review")
def review_entity(entity_id: str, item: ReviewInput):
    if item.status not in ["approved","rejected","pending"]:
        raise HTTPException(400, "Status must be approved, rejected or pending")
    with connect() as c:
        cur = c.execute("UPDATE entities SET status=? WHERE id=?", (item.status, entity_id))
        if cur.rowcount == 0: raise HTTPException(404, "Entity not found")
    return {"ok":True}

@app.post("/api/relations/{relation_id}/review")
def review_relation(relation_id: str, item: ReviewInput):
    if item.status not in ["approved","rejected","pending"]:
        raise HTTPException(400, "Status must be approved, rejected or pending")
    with connect() as c:
        cur = c.execute("UPDATE relations SET status=? WHERE id=?", (item.status, relation_id))
        if cur.rowcount == 0: raise HTTPException(404, "Relation not found")
    return {"ok":True}

@app.post("/api/demo")
def load_demo():
    samples = [
      ("Public bulletin (demo)", "English", "A fictional public transport bulletin dated 12 October 2026 says the Rivergate bridge will close for inspection. The notice was issued by the fictional Rivergate Municipal Office. A separate paragraph says a community clean-up event is planned at Central Park on 15 October."),
      ("समाचार नमूना (काल्पनिक)", "Hindi", "काल्पनिक समाचार सूचना के अनुसार, 15 अक्टूबर 2026 को सेंट्रल पार्क में सामुदायिक सफाई कार्यक्रम आयोजित होगा। सूचना रिवरगेट नगर कार्यालय द्वारा जारी की गई है।"),
      ("Marathi public notice (fictional)", "Marathi", "काल्पनिक सार्वजनिक सूचनेनुसार, रिव्हरगेट नगर कार्यालयाने १५ ऑक्टोबर २०२६ रोजी सेंट्रल पार्क येथे स्वच्छता कार्यक्रम जाहीर केला आहे.")
    ]
    created = []
    for title, lang, content in samples:
        did = str(uuid.uuid4())
        with connect() as c:
            c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
              (did,title,"demo","Synthetic fictional public-information sample",lang,content,datetime.now(timezone.utc).isoformat()))
        created.append({"id":did,"title":title})
    return {"created":created,"message":"Synthetic demo sources loaded. Analyze each source to extract candidates."}

@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str):
    with connect() as c:
        c.execute("DELETE FROM entities WHERE document_id=?", (document_id,))
        c.execute("DELETE FROM relations WHERE document_id=?", (document_id,))
        cur = c.execute("DELETE FROM documents WHERE id=?", (document_id,))
        if cur.rowcount == 0: raise HTTPException(404, "Source not found")
    return {"ok":True}
