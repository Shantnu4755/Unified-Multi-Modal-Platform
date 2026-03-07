from typing import List, Dict, Any
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, model: str | None = None):
        self.model = model or settings.ollama_model
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.max_tokens = 1000
        self.temperature = 0.1
        self._client = httpx.Client(timeout=60.0)

    def _fallback_answer(self, question: str, context_chunks: List[Dict]) -> str:
        """Return a clean message when LLM is unavailable."""
        return (
            "AI Model Unavailable. "
            "Please ensure Ollama is running and the required models are installed: "
            "ollama pull llama3.2:1b && ollama pull nomic-embed-text. "
            f"Question: {question}. "
            f"Context chunks retrieved: {len(context_chunks)}."
        )

    def _ollama_chat(self, messages: List[Dict[str, str]]) -> str:
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content") or ""

    def generate_answer(self, question: str, context_chunks: List[Dict]) -> str:
        """Generate answer using retrieved context."""
        try:
            context = self._build_context(context_chunks)
            prompt = self._create_prompt(question, context)

            answer = self._ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": """You are a helpful AI assistant that answers questions based on provided document context.

Rules:
1. Only use information from the provided context
2. If the context doesn't contain enough information, say so
3. Be concise but comprehensive
4. Cite specific parts of the context when possible
5. If asked about something not in the context, politely decline""",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            logger.info("Generated answer of %s characters", len(answer))
            return answer

        except Exception as e:
            logger.error("Failed to generate answer: %s", e)
            logger.warning("Using fallback answer due to Ollama failure")
            return self._fallback_answer(question=question, context_chunks=context_chunks)

    def chat(self, message: str) -> str:
        """General chat (no RAG)."""
        try:
            return self._ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful AI assistant.",
                    },
                    {"role": "user", "content": message},
                ]
            )
        except Exception as e:
            logger.error("Failed to chat: %s", e)
            return "AI Model Unavailable. Please ensure Ollama is running and llama3.2:1b is available."
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """Build context string from retrieved chunks."""
        if not chunks:
            return "No relevant context found."
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(f"[Context {i}]")
            context_parts.append(chunk["content"])
            context_parts.append("")  # Empty line separator
        
        return "\n".join(context_parts)
    
    def _create_prompt(self, question: str, context: str) -> str:
        """Create the prompt for the LLM."""
        return f"""Based on the following context, please answer the question.

Context:
{context}

Question: {question}

Answer:"""
    
    def summarize_document(self, text: str, max_length: int = 200) -> str:
        """Generate a summary of document text."""
        try:
            summary = self._ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a helpful assistant that creates concise summaries. Keep summaries under {max_length} words.",
                    },
                    {"role": "user", "content": f"Please provide a concise summary of the following text:\n\n{text}"},
                ]
            )

            if summary:
                return summary
            return "Summary generation failed."

        except Exception as e:
            logger.error("Failed to generate summary: %s", e)
            # Return a clean formatted extract instead of raw text
            if not text:
                return "No content available for summary."
            
            # Clean up the text - remove page markers and extra whitespace
            cleaned = text.replace("--- Page", "\n Page")
            cleaned = cleaned.replace("\n\n", "\n")
            
            # Take first meaningful portion
            preview = cleaned[:max_length * 5]
            return (
                "AI Summary Unavailable. "
                "The model could not generate a summary right now. "
                "Preview of document content: "
                f"{preview} "
                "(Tip: ensure Ollama is running and llama3.2:1b is available.)"
            )