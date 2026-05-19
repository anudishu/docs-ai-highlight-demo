from __future__ import annotations

import json
import logging
import os
import re
from datetime import timedelta
from html import escape
from urllib.parse import quote

from typing import Annotated

import google.auth
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from google import genai
from google.auth.transport import requests as google_auth_requests
from google.cloud import storage
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from shared.config import (
    GCS_BUCKET,
    GCP_PROJECT,
    GEMINI_API_KEY,
    GEMINI_LOCATION,
    GEMINI_MODEL,
    SERVICE_ACCOUNT_EMAIL,
    TOP_K,
)
from shared.embeddings import embed_query
from shared.firestore_store import FirestoreStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="docs-highlight-api")
store = FirestoreStore()
storage_client = storage.Client(project=GCP_PROJECT or None)

_genai_client: genai.Client | None = None


def _genai_client_instance() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        if GEMINI_API_KEY:
            _genai_client = genai.Client(api_key=GEMINI_API_KEY)
        else:
            _genai_client = genai.Client(
                vertexai=True,
                project=GCP_PROJECT,
                location=GEMINI_LOCATION,
            )
    return _genai_client


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int | None = None


def _highlight_phrase(text: str, max_len: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len]


def _public_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _viewer_url_multi(base_url: str, chunk_ids: list[str]) -> str:
    if not chunk_ids:
        return f"{base_url.rstrip('/')}/view"
    q = "&".join(f"chunkIds={quote(cid)}" for cid in chunk_ids)
    return f"{base_url.rstrip('/')}/view?{q}"


_google_auth_request = google_auth_requests.Request()


def _service_account_email() -> str:
    if SERVICE_ACCOUNT_EMAIL:
        return SERVICE_ACCOUNT_EMAIL
    credentials, _ = google.auth.default()
    email = getattr(credentials, "service_account_email", None) or getattr(
        credentials, "signer_email", None
    )
    if email:
        return email
    raise RuntimeError("SERVICE_ACCOUNT_EMAIL is required for PDF signed URLs on Cloud Run")


def _signed_pdf_url(bucket: str, object_name: str) -> str:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not credentials.valid:
        credentials.refresh(_google_auth_request)

    blob = storage_client.bucket(bucket).blob(object_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=30),
        method="GET",
        service_account_email=_service_account_email(),
        access_token=credentials.token,
    )


def _pdf_blob_from_chunk(chunk_id: str):
    chunk = store.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    bucket = chunk.get("bucket") or GCS_BUCKET
    object_name = chunk.get("object_name")
    if not bucket or not object_name:
        raise HTTPException(status_code=404, detail="Source object missing on chunk")
    return storage_client.bucket(bucket).blob(object_name)


def _build_collapsed_sources(hits: list[dict], base_url: str) -> list[dict]:
    """One row per PDF: merge retrieved chunks so the UI shows a single source with one highlight viewer."""
    groups: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for hit in hits:
        bucket = hit.get("bucket") or GCS_BUCKET or ""
        obj = hit.get("object_name") or ""
        key = (bucket, obj)
        if key not in groups:
            groups[key] = {"chunk_ids": [], "hits": []}
            order.append(key)
        cid = hit.get("chunk_id") or ""
        if cid and cid not in groups[key]["chunk_ids"]:
            groups[key]["chunk_ids"].append(cid)
        groups[key]["hits"].append(hit)

    out: list[dict] = []
    for key in order:
        gh = groups[key]["hits"]
        gids = groups[key]["chunk_ids"]
        ps_min = min(int(h.get("page_start") or 1) for h in gh)
        pe_max = max(int(h.get("page_end") or 1) for h in gh)
        snippets: list[str] = []
        for h in gh:
            t = _highlight_phrase(h.get("text", ""), max_len=220)
            if t and t not in snippets:
                snippets.append(t)
        combined = " · ".join(snippets[:5])
        if len(snippets) > 5:
            combined += f" … (+{len(snippets) - 5} more passages)"

        first = gh[0]
        out.append(
            {
                "object_name": first.get("object_name"),
                "gcs_uri": first.get("gcs_uri"),
                "page_start": ps_min,
                "page_end": pe_max,
                "page": ps_min,
                "snippet": combined,
                "evidence_chunks": len(gids),
                "viewer_url": _viewer_url_multi(base_url, gids),
                "chunk_ids": gids,
            }
        )
    return out
def _rag_answer(question: str, hits: list[dict]) -> str:
    context_blocks = []
    for i, hit in enumerate(hits, start=1):
        context_blocks.append(
            f"[{i}] (pages {hit.get('page_start')}-{hit.get('page_end')}, "
            f"source={hit.get('gcs_uri')})\n{hit.get('text', '')}"
        )
    context = "\n\n".join(context_blocks)
    prompt = f"""You are a helpful assistant. Answer ONLY using the context below.
If the answer is not in the context, say you do not have enough information.

Context:
{context}

Question: {question}

Answer clearly and cite source numbers like [1], [2] where relevant."""

    client = _genai_client_instance()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1024,
        ),
    )
    return (response.text or "").strip()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Docs Highlight RAG</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; }
    textarea { width: 100%; min-height: 100px; }
    button { padding: 0.5rem 1rem; }
    .source { border: 1px solid #ddd; padding: 0.75rem; margin: 0.5rem 0; border-radius: 8px; }
    pre { white-space: pre-wrap; background: #f6f8fa; padding: 1rem; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>Docs Highlight RAG</h1>
  <p>Upload text-based PDFs to the ingest GCS bucket. Ask a question below.</p>
  <textarea id="q" placeholder="Ask about your documents..."></textarea>
  <p><button id="go">Ask</button></p>
  <h2>Answer</h2>
  <pre id="answer"></pre>
  <h2>Sources</h2>
  <div id="sources-list"></div>
  <script>
    const list = document.getElementById('sources-list');
    document.getElementById('go').onclick = async () => {
      const question = document.getElementById('q').value.trim();
      if (!question) return;
      document.getElementById('answer').textContent = 'Loading...';
      list.innerHTML = '';
      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question })
        });
        const raw = await res.text();
        if (!res.ok) {
          document.getElementById('answer').textContent = 'Error ' + res.status + ': ' + raw;
          return;
        }
        const data = JSON.parse(raw);
        document.getElementById('answer').textContent = data.answer || JSON.stringify(data, null, 2);
      (data.sources || []).forEach((s, i) => {
        const div = document.createElement('div');
        div.className = 'source';
        div.innerHTML = `<strong>[${i+1}]</strong> ${s.object_name || ''} (pages ${s.page_start}–${s.page_end}, ${s.evidence_chunks || 1} evidence passage(s))<br/>
          <code>${s.gcs_uri || ''}</code><br/>
          <em>${s.snippet || ''}</em><br/>
          <a href="${s.viewer_url}" target="_blank">Open highlighted PDF</a>`;
        list.appendChild(div);
      });
      } catch (err) {
        document.getElementById('answer').textContent = 'Request failed: ' + err;
      }
    };
  </script>
</body>
</html>"""


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> JSONResponse:
    try:
        top_k = body.top_k or TOP_K
        query_vector = embed_query(body.question)
        hits = store.vector_search(query_vector, limit=top_k)
        if not hits:
            return JSONResponse(
                {
                    "answer": "No indexed content found. Upload a text-based PDF to the ingest bucket and wait for ingestion.",
                    "sources": [],
                }
            )

        base_url = _public_base_url(request)
        sources = _build_collapsed_sources(hits, base_url)
        answer = _rag_answer(body.question, hits)
        return JSONResponse({"answer": answer, "sources": sources})
    except Exception as exc:
        logger.exception("chat failed")
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "answer": None, "sources": []},
        )


@app.head("/documents/pdf-proxy/{chunk_id}")
def pdf_proxy_head(chunk_id: str) -> Response:
    blob = _pdf_blob_from_chunk(chunk_id)
    blob.reload()

    object_name = blob.name.split("/")[-1] if blob.name else "document.pdf"
    disposition = object_name.encode("latin-1", errors="ignore").decode("latin-1") or "document.pdf"

    headers = {
        "Content-Length": str(blob.size or 0),
        "Content-Disposition": f'inline; filename="{disposition}"',
        "Cache-Control": "private, max-age=60",
        "Accept-Ranges": "bytes",
    }
    return Response(media_type="application/pdf", headers=headers)


@app.get("/documents/pdf-proxy/{chunk_id}")
def pdf_proxy(chunk_id: str) -> StreamingResponse:
    """Serve PDF bytes through this API so the browser avoids GCS ↔ origin CORS for PDF.js."""
    blob = _pdf_blob_from_chunk(chunk_id)

    object_name = blob.name.split("/")[-1] if blob.name else "document.pdf"
    disposition = object_name.encode("latin-1", errors="ignore").decode("latin-1") or "document.pdf"

    def body():
        with blob.open("rb") as fh:
            while True:
                part = fh.read(1024 * 1024)
                if not part:
                    break
                yield part

    return StreamingResponse(
        body(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{disposition}"',
            "Cache-Control": "private, max-age=60",
            "Accept-Ranges": "bytes",
        },
    )


@app.get("/view", response_class=HTMLResponse)
def view(
    chunkId: str | None = None,
    chunkIds: Annotated[list[str] | None, Query()] = None,
) -> str:
    incoming: list[str] = []
    if chunkIds:
        incoming.extend(chunkIds)
    if chunkId:
        incoming.insert(0, chunkId)
    ids = list(dict.fromkeys(incoming))
    if not ids:
        raise HTTPException(status_code=400, detail="Provide chunkId or chunkIds")

    chunks: list[dict] = []
    for cid in ids:
        row = store.get_chunk(cid)
        if not row:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {cid}")
        chunks.append(row)

    keys = {(c.get("bucket") or GCS_BUCKET, c.get("object_name") or "") for c in chunks}
    if len(keys) != 1 or not next(iter(keys))[1]:
        raise HTTPException(status_code=400, detail="All chunks must reference the same PDF object")

    bucket, object_name = next(iter(keys))
    gcs_uri = chunks[0].get("gcs_uri", f"gs://{bucket}/{object_name}")

    page_nums_set: set[int] = set()
    for c in chunks:
        ps, pe = int(c.get("page_start") or 1), int(c.get("page_end") or 1)
        for p in range(ps, pe + 1):
            page_nums_set.add(p)
    page_nums = sorted(page_nums_set)

    page_highlights: dict[str, str] = {}
    for p in page_nums:
        parts: list[str] = []
        for c in chunks:
            ps, pe = int(c.get("page_start") or 1), int(c.get("page_end") or 1)
            if ps <= p <= pe:
                parts.append(c.get("text") or "")
        page_highlights[str(p)] = _highlight_phrase("\n".join(parts), max_len=900)

    if len(page_nums) == 1:
        page_banner = str(page_nums[0])
    elif len(page_nums) <= 8:
        page_banner = ", ".join(str(p) for p in page_nums)
    else:
        page_banner = f"{len(page_nums)} pages ({page_nums[0]} … {page_nums[-1]})"

    proxy_chunk_id = ids[0]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>PDF Viewer — {escape(object_name)}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.min.mjs" type="module"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; }}
    header {{ padding: 0.75rem 1rem; background: #111; color: #fff; }}
    header a {{ color: #9cf; }}
    #viewer {{ display: flex; flex-direction: column; align-items: center; gap: 1rem; padding: 1rem; }}
    #viewer-error {{
      padding: 1rem; margin: 0 1rem; background: #fee; border: 1px solid #c33; border-radius: 8px; max-width: 52rem;
    }}
    canvas {{ border: 1px solid #ccc; max-width: 95vw; }}
    .meta {{ font-size: 0.9rem; opacity: 0.9; }}
    h3.page-heading {{ margin: 1.5rem 0 0.25rem; width: 100%; max-width: 52rem; }}
  </style>
</head>
<body>
  <header>
    <div><strong>{escape(object_name)}</strong></div>
    <div class="meta">Source: <code>{escape(gcs_uri)}</code> · Pages {escape(page_banner)}</div>
    <div><a href="/">Back to chat</a> · <a href="{escape(_signed_pdf_url(bucket, object_name))}" target="_blank" rel="noopener">Download from GCS (signed)</a></div>
  </header>
  <div id="viewer-error" style="display:none;"></div>
  <div id="viewer"></div>
  <script type="module">
    import * as pdfjsLib from 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.min.mjs';
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.worker.min.mjs';

    const proxyChunkId = {json.dumps(proxy_chunk_id)};
    const pdfUrl = new URL('/documents/pdf-proxy/' + encodeURIComponent(proxyChunkId), window.location.origin).href;
    const pagesToShow = {json.dumps(page_nums)};
    const pageHighlights = {json.dumps(page_highlights)};

    const container = document.getElementById('viewer');
    const errBox = document.getElementById('viewer-error');
    let pdf;
    try {{
      const loadingTask = pdfjsLib.getDocument({{ url: pdfUrl, withCredentials: false }});
      pdf = await loadingTask.promise;
    }} catch (e) {{
      errBox.style.display = 'block';
      errBox.textContent = 'Could not load PDF: ' + (e && e.message ? e.message : e);
      throw e;
    }}

    function termsFromHighlight(h) {{
      const t = (h || '').toLowerCase();
      return t.split(/\\s+/).filter(w => w.length > 2).slice(0, 36);
    }}

    async function renderPage(num, highlightText) {{
      const pdfPage = await pdf.getPage(num);
      const viewport = pdfPage.getViewport({{ scale: 1.35 }});
      const wrap = document.createElement('div');
      wrap.style.position = 'relative';
      wrap.style.display = 'inline-block';

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      wrap.appendChild(canvas);
      await pdfPage.render({{ canvasContext: ctx, viewport }}).promise;

      if (highlightText) {{
        const terms = termsFromHighlight(highlightText);
        const textContent = await pdfPage.getTextContent();
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;';
        overlay.style.width = canvas.width + 'px';
        overlay.style.height = canvas.height + 'px';

        let hitCount = 0;
        for (const item of textContent.items) {{
          const token = (item.str || '').toLowerCase();
          if (!token || !terms.some(t => token.includes(t))) continue;
          const m = pdfjsLib.Util.transform(viewport.transform, item.transform);
          const el = document.createElement('span');
          el.style.cssText = 'position:absolute;background:rgba(255,235,59,0.55);';
          el.style.left = m[4] + 'px';
          el.style.top = (m[5] - Math.abs(m[0])) + 'px';
          el.style.width = (item.width * Math.abs(m[0])) + 'px';
          el.style.height = Math.abs(m[0]) + 'px';
          overlay.appendChild(el);
          hitCount += 1;
        }}
        wrap.appendChild(overlay);

        const badge = document.createElement('div');
        badge.style.cssText = 'padding:0.5rem;background:#fff3cd;border:1px solid #ffc107;border-radius:6px;max-width:95vw;margin-bottom:0.5rem;align-self:flex-start;width:100%;max-width:52rem';
        badge.textContent = hitCount
          ? `Highlighted ${{hitCount}} text region(s) on page ${{num}}`
          : `Page ${{num}}: few token matches vs extracted text — try wording in snippet. Preview terms: ${{terms.slice(0, 10).join(', ')}}`;
        container.appendChild(badge);
      }}

      container.appendChild(wrap);
    }}

    const summary = document.createElement('p');
    summary.style.cssText = 'max-width:52rem;text-align:center;';
    summary.textContent = 'Showing ' + pagesToShow.length + ' page(s) with retrieved evidence · PDF has ' + pdf.numPages + ' page(s).';
    container.appendChild(summary);

    for (const num of pagesToShow) {{
      const heading = document.createElement('h3');
      heading.className = 'page-heading';
      heading.textContent = 'Page ' + num;
      container.appendChild(heading);
      const hl = pageHighlights[String(num)] || '';
      await renderPage(num, hl);
    }}
  </script>
</body>
</html>"""


@app.get("/documents/{document_id}")
def document_status(document_id: str) -> dict:
    doc = store.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
