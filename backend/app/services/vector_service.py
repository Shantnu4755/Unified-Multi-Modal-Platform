from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.models import Filter, FieldCondition, Range, MatchValue
from qdrant_client.models import PayloadSchemaType
from typing import List, Dict, Optional
import uuid
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class VectorService:
    def __init__(self):
        self.client = None
        self.memory_storage = {}  # Fallback in-memory storage
        self.base_collection_name = "documents"
        self.vector_size = settings.embedding_dim
        self.collection_name = f"{self.base_collection_name}_{self.vector_size}"
        self._qdrant_available = False

        # Try to initialize Qdrant client
        try:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=5
            )
            # Test connection
            self.client.get_collections()
            self._qdrant_available = True
            logger.info("Qdrant connection successful")
            self._select_collection_name()
            self._ensure_collection()
        except Exception as e:
            logger.warning(f"Qdrant not available, using in-memory storage: {e}")
            self._qdrant_available = False

    def _get_collection_vector_size(self, collection_name: str) -> Optional[int]:
        """Return the configured vector size for a collection, if available."""
        if not self._qdrant_available:
            return None
        try:
            info = self.client.get_collection(collection_name=collection_name)
        except Exception:
            return None

        vectors = getattr(getattr(getattr(info, "config", None), "params", None), "vectors", None)
        # Qdrant may return a VectorParams or a map of vectors.
        if vectors is None:
            return None
        if hasattr(vectors, "size"):
            return getattr(vectors, "size", None)
        if isinstance(vectors, dict):
            # Named vectors case; pick the first
            for v in vectors.values():
                if hasattr(v, "size"):
                    return getattr(v, "size", None)
        return None

    def _select_collection_name(self) -> None:
        """Pick a collection name that matches the current embedding dimension.

        This avoids runtime failures when the embedding model/dimension changes.
        """
        if not self._qdrant_available:
            return

        try:
            collections = self.client.get_collections().collections
            collection_names = {col.name for col in collections}
        except Exception:
            return

        # If a legacy collection exists and matches current dim, keep using it.
        if self.base_collection_name in collection_names:
            legacy_dim = self._get_collection_vector_size(self.base_collection_name)
            if legacy_dim == self.vector_size:
                self.collection_name = self.base_collection_name
                return

        # Otherwise, use a dimension-specific collection.
        self.collection_name = f"{self.base_collection_name}_{self.vector_size}"
    
    def _ensure_collection(self):
        """Ensure the collection exists with proper index for document_id."""
        if not self._qdrant_available:
            return
        
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]

            if self.collection_name in collection_names:
                existing_dim = self._get_collection_vector_size(self.collection_name)
                if existing_dim is not None and existing_dim != self.vector_size:
                    # Safety: never upsert vectors into a wrong-dimension collection.
                    self.collection_name = f"{self.base_collection_name}_{self.vector_size}"
                    logger.warning(
                        "Existing collection dim mismatch. Switching to %s (expected %s, found %s)",
                        self.collection_name,
                        self.vector_size,
                        existing_dim,
                    )

            if self.collection_name not in collection_names:
                # Create collection with vector config
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
                
                # Create payload index for document_id (required for filtering)
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="document_id",
                    field_type=PayloadSchemaType.INTEGER
                )
                logger.info(f"Created payload index for document_id")
            else:
                logger.info(f"Collection {self.collection_name} already exists")
                # Ensure index exists even for existing collections
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="document_id",
                        field_type=PayloadSchemaType.INTEGER
                    )
                    logger.info(f"Created/verified payload index for document_id")
                except Exception as index_e:
                    # Index may already exist, that's fine
                    logger.debug(f"Payload index creation (may already exist): {index_e}")
                
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            self._qdrant_available = False
    
    def store_chunks(self, document_id: int, chunks: List[Dict]) -> List[str]:
        """Store document chunks in vector database."""
        if not chunks:
            return []

        vector_ids = []

        # In-memory fallback
        if not self._qdrant_available:
            for chunk in chunks:
                vector_id = str(uuid.uuid4())
                vector_ids.append(vector_id)
                self.memory_storage[vector_id] = {
                    "document_id": document_id,
                    "chunk_index": chunk.get("index", 0),
                    "content": chunk["content"],
                    "word_count": chunk.get("word_count", 0),
                    "embedding": chunk.get("embedding", [])
                }
            logger.info(f"Stored {len(vector_ids)} chunks in memory for document {document_id}")
            return vector_ids

        # Qdrant storage
        points = []

        for chunk in chunks:
            vector_id = str(uuid.uuid4())
            vector_ids.append(vector_id)

            point = PointStruct(
                id=vector_id,
                vector=chunk.get("embedding", []),
                payload={
                    "document_id": document_id,
                    "chunk_index": chunk.get("index", 0),
                    "content": chunk["content"],
                    "word_count": chunk.get("word_count", 0)
                }
            )
            points.append(point)

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Stored {len(points)} chunks for document {document_id}")
            return vector_ids

        except Exception as e:
            logger.error(f"Failed to store chunks: {e}")
            raise Exception(f"Vector storage failed: {e}")
    
    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        document_id: Optional[int] = None,
        score_threshold: float = 0.7
    ) -> List[Dict]:
        """Search for similar chunks."""

        # In-memory fallback
        if not self._qdrant_available:
            results = []
            for vid, data in self.memory_storage.items():
                if document_id and data["document_id"] != document_id:
                    continue

                # Simple cosine similarity calculation
                embedding = data.get("embedding", [])
                if not embedding or not query_embedding:
                    continue

                # Calculate cosine similarity
                dot_product = sum(a * b for a, b in zip(embedding, query_embedding))
                norm_a = sum(a * a for a in embedding) ** 0.5
                norm_b = sum(b * b for b in query_embedding) ** 0.5

                if norm_a == 0 or norm_b == 0:
                    continue

                score = dot_product / (norm_a * norm_b)

                if score >= score_threshold:
                    results.append({
                        "id": vid,
                        "score": score,
                        "document_id": data["document_id"],
                        "chunk_index": data["chunk_index"],
                        "content": data["content"],
                        "word_count": data["word_count"]
                    })

            # Sort by score and limit results
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:limit]

            logger.info(f"Found {len(results)} similar chunks in memory")
            return results

        # Qdrant search
        try:
            search_filter = None
            if document_id:
                search_filter = Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold
            )

            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "score": result.score,
                    "document_id": result.payload["document_id"],
                    "chunk_index": result.payload["chunk_index"],
                    "content": result.payload["content"],
                    "word_count": result.payload["word_count"]
                })

            logger.info(f"Found {len(formatted_results)} similar chunks")
            return formatted_results

        except Exception as e:
            logger.error(f"Failed to search vectors: {e}")
            raise Exception(f"Vector search failed: {e}")
    
    def delete_document_chunks(self, document_id: int):
        """Delete all chunks for a document."""

        # In-memory fallback
        if not self._qdrant_available:
            to_delete = [vid for vid, data in self.memory_storage.items()
                        if data["document_id"] == document_id]
            for vid in to_delete:
                del self.memory_storage[vid]
            logger.info(f"Deleted {len(to_delete)} chunks from memory for document {document_id}")
            return

        # Qdrant deletion
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
            logger.info(f"Deleted chunks for document {document_id}")

        except Exception as e:
            logger.error(f"Failed to delete document chunks: {e}")
            raise Exception(f"Vector deletion failed: {e}")

    def get_collection_stats(self) -> Dict:
        """Get collection statistics."""

        # In-memory fallback
        if not self._qdrant_available:
            return {
                "total_points": len(self.memory_storage),
                "vector_size": self.vector_size,
                "distance": "COSINE",
                "mode": "in-memory"
            }

        # Qdrant stats
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "total_points": info.points_count,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance,
                "mode": "qdrant"
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}