from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

DOCUMENTS = "documents"
CHUNKS = "chunks"


def document_id_for_object(bucket: str, object_name: str) -> str:
    key = f"{bucket}/{object_name}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def chunk_id_for(document_id: str, chunk_index: int) -> str:
    return f"{document_id}_{chunk_index:05d}"


class FirestoreStore:
    def __init__(self) -> None:
        self.db = firestore.Client()

    def set_document_processing(
        self,
        document_id: str,
        *,
        gcs_uri: str,
        bucket: str,
        object_name: str,
    ) -> None:
        self.db.collection(DOCUMENTS).document(document_id).set(
            {
                "gcs_uri": gcs_uri,
                "bucket": bucket,
                "object_name": object_name,
                "status": "processing",
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )

    def set_document_ready(
        self,
        document_id: str,
        *,
        page_count: int,
        chunk_count: int,
    ) -> None:
        self.db.collection(DOCUMENTS).document(document_id).set(
            {
                "status": "ready",
                "page_count": page_count,
                "chunk_count": chunk_count,
                "updated_at": datetime.now(timezone.utc),
                "ingested_at": datetime.now(timezone.utc),
            },
            merge=True,
        )

    def set_document_failed(self, document_id: str, error: str) -> None:
        self.db.collection(DOCUMENTS).document(document_id).set(
            {
                "status": "failed",
                "error": error[:2000],
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )

    def delete_chunks_for_document(self, document_id: str) -> None:
        query = self.db.collection(CHUNKS).where("document_id", "==", document_id)
        batch = self.db.batch()
        count = 0
        for snap in query.stream():
            batch.delete(snap.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
        if count:
            batch.commit()

    def write_chunks(
        self,
        document_id: str,
        *,
        gcs_uri: str,
        bucket: str,
        object_name: str,
        chunks: list[dict],
    ) -> None:
        batch = self.db.batch()
        count = 0
        for item in chunks:
            cid = chunk_id_for(document_id, item["chunk_index"])
            ref = self.db.collection(CHUNKS).document(cid)
            batch.set(
                ref,
                {
                    "document_id": document_id,
                    "chunk_id": cid,
                    "chunk_index": item["chunk_index"],
                    "text": item["text"],
                    "embedding": Vector(item["embedding"]),
                    "gcs_uri": gcs_uri,
                    "bucket": bucket,
                    "object_name": object_name,
                    "page_start": item["page_start"],
                    "page_end": item["page_end"],
                    "char_start": item["char_start"],
                    "char_end": item["char_end"],
                },
            )
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
        if count:
            batch.commit()

    def get_document(self, document_id: str) -> dict | None:
        snap = self.db.collection(DOCUMENTS).document(document_id).get()
        return snap.to_dict() if snap.exists else None

    def get_chunk(self, chunk_id: str) -> dict | None:
        snap = self.db.collection(CHUNKS).document(chunk_id).get()
        return snap.to_dict() if snap.exists else None

    def vector_search(self, query_vector: list[float], limit: int) -> list[dict]:
        collection = self.db.collection(CHUNKS)
        results = collection.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
        ).get()

        hits: list[dict] = []
        for snap in results:
            data = snap.to_dict() or {}
            data["chunk_id"] = snap.id
            hits.append(data)
        return hits
