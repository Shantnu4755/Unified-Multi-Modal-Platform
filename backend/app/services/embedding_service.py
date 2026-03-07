from typing import List, Dict, Any
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model: str | None = None):
        self.model = model or settings.ollama_embedding_model
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.dim = settings.embedding_dim
        self._client = httpx.Client(timeout=60.0)

    def _local_embedding(self, text: str) -> List[float]:
        import hashlib

        hash_val = hashlib.md5(text.encode()).hexdigest()
        embedding = [int(hash_val[i : i + 2], 16) / 255.0 for i in range(0, 32, 2)]
        if len(embedding) < self.dim:
            embedding = embedding * (self.dim // len(embedding) + 1)
        return embedding[: self.dim]

    def _ollama_embedding(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": text,
        }
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        embedding = data.get("embedding")
        if not embedding:
            raise ValueError("Ollama embeddings API returned empty embedding")
        return embedding

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text using Ollama embeddings API."""
        try:
            emb = self._ollama_embedding(text=text)
            if len(emb) != self.dim:
                if len(emb) > self.dim:
                    return emb[: self.dim]
                emb = emb + [0.0] * (self.dim - len(emb))
            return emb
        except Exception as e:
            logger.error("Failed to get embedding via Ollama: %s", e)
            logger.warning("Using local embedding fallback due to embedding failure.")
            return self._local_embedding(text=text)

    def get_embeddings_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """Get embeddings for multiple texts in batches."""
        if not texts:
            return []

        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            try:
                for text in batch:
                    embedding = self.get_embedding(text)
                    embeddings.append(embedding)

                logger.info(f"Generated embeddings for batch {i//batch_size + 1}, texts {i+1}-{min(i+batch_size, len(texts))}")

            except Exception as e:
                logger.error(f"Failed to get embeddings for batch {i//batch_size + 1}: {e}")
                raise Exception(f"Batch embedding generation failed: {e}")

        return embeddings

    def embed_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """Add embeddings to document chunks."""
        if not chunks:
            return []

        texts = [chunk["content"] for chunk in chunks]
        embeddings = self.get_embeddings_batch(texts)

        # Add embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        logger.info(f"Added embeddings to {len(chunks)} chunks")
        return chunks