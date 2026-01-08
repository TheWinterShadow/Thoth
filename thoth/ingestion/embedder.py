"""Embedder module for generating document embeddings.

This module provides the Embedder class for generating embeddings from text chunks
using sentence-transformers models with batch processing support.
"""

import logging
from typing import Any

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """Generate embeddings from text using sentence-transformers.

    Supports batch processing with progress tracking for efficient embedding generation.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
        batch_size: int = 32,
    ):
        """Initialize the Embedder with a sentence-transformers model.

        Args:
            model_name: Name of the sentence-transformers model to use.
                Default is 'all-MiniLM-L6-v2' for a good balance of speed and quality.
                Other options: 'all-mpnet-base-v2' (higher quality, slower).
            device: Device to use for inference ('cuda', 'cpu', or None for auto-detect).
            batch_size: Number of texts to process in each batch (default: 32).
        """
        self.model_name = model_name
        self.batch_size = batch_size

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)
        logger.info(f"Model loaded successfully on device: {self.model.device}")

    def embed(
        self,
        texts: list[str],
        show_progress: bool = False,
        normalize: bool = True,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            show_progress: Whether to show a progress bar during batch processing.
            normalize: Whether to normalize embeddings to unit length (default: True).
                Normalized embeddings work better with cosine similarity.

        Returns:
            List of embedding vectors, where each vector is a list of floats.

        Raises:
            ValueError: If texts list is empty or contains empty/whitespace-only strings.
        """
        if not texts:
            msg = "Cannot generate embeddings for empty text list"
            raise ValueError(msg)

        invalid_indices = [i for i, text in enumerate(texts) if not isinstance(text, str) or not text.strip()]
        if invalid_indices:
            msg = (
                "Cannot generate embeddings for empty or whitespace-only texts; "
                f"invalid entries at indices: {invalid_indices}"
            )
            raise ValueError(msg)
        logger.info(f"Generating embeddings for {len(texts)} texts with batch_size={self.batch_size}")

        # Generate embeddings with batch processing
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )

        # Convert numpy arrays to lists for JSON serialization
        embeddings_list: list[list[float]] = embeddings.tolist()

        logger.info(f"Generated {len(embeddings_list)} embeddings of dimension {len(embeddings_list[0])}")

        return embeddings_list

    def embed_single(self, text: str, normalize: bool = True) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed.
            normalize: Whether to normalize embedding to unit length (default: True).

        Returns:
            Embedding vector as a list of floats.

        Raises:
            ValueError: If text is empty.
        """
        if not text:
            msg = "Cannot generate embedding for empty text"
            raise ValueError(msg)

        embeddings = self.embed([text], show_progress=False, normalize=normalize)
        return embeddings[0]

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model.

        Returns:
            Integer dimension of the embedding vectors.
        """
        return self.model.get_sentence_embedding_dimension()  # type: ignore[return-value]

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model.

        Returns:
            Dictionary containing model metadata:
                - model_name: Name of the model
                - embedding_dimension: Dimension of embeddings
                - max_seq_length: Maximum sequence length the model can handle
                - device: Device the model is running on
                - batch_size: Configured batch size for processing
        """
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.get_embedding_dimension(),
            "max_seq_length": self.model.max_seq_length,
            "device": str(self.model.device),
            "batch_size": self.batch_size,
        }
