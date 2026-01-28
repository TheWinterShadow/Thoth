"""Tests for the Embedder class."""

import pytest

from thoth.shared.embedder import Embedder


class TestEmbedder:
    """Test suite for the Embedder class."""

    @pytest.fixture
    def embedder(self):
        """Create an Embedder instance with default settings."""
        return Embedder(model_name="all-MiniLM-L6-v2", device="cpu")

    def test_embedder_initialization(self, embedder):
        """Test that Embedder initializes correctly."""
        assert embedder.model_name == "all-MiniLM-L6-v2"
        assert embedder.batch_size == 32
        assert embedder.model is not None

    def test_embed_single_text(self, embedder):
        """Test embedding a single text."""
        text = "This is a test sentence."
        embedding = embedder.embed_single(text)

        assert isinstance(embedding, list)
        assert len(embedding) == embedder.get_embedding_dimension()
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_multiple_texts(self, embedder):
        """Test embedding multiple texts in batch."""
        texts = [
            "First test sentence.",
            "Second test sentence.",
            "Third test sentence.",
        ]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == len(texts)
        assert all(len(emb) == embedder.get_embedding_dimension() for emb in embeddings)
        assert all(isinstance(x, float) for emb in embeddings for x in emb)

    def test_embed_empty_list_raises_error(self, embedder):
        """Test that embedding an empty list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot generate embeddings for empty text list"):
            embedder.embed([])

    def test_embed_single_empty_text_raises_error(self, embedder):
        """Test that embedding empty text raises ValueError."""
        with pytest.raises(ValueError, match="Cannot generate embedding for empty text"):
            embedder.embed_single("")

    def test_get_embedding_dimension(self, embedder):
        """Test getting embedding dimension."""
        dimension = embedder.get_embedding_dimension()
        assert isinstance(dimension, int)
        assert dimension > 0
        # all-MiniLM-L6-v2 has 384 dimensions
        assert dimension == 384

    def test_get_model_info(self, embedder):
        """Test getting model information."""
        info = embedder.get_model_info()

        assert info["model_name"] == "all-MiniLM-L6-v2"
        assert info["embedding_dimension"] == 384
        assert "device" in info
        assert info["batch_size"] == 32
        assert "max_seq_length" in info

    def test_embeddings_are_normalized(self, embedder):
        """Test that embeddings are normalized to unit length by default."""
        text = "Test sentence for normalization."
        embedding = embedder.embed_single(text, normalize=True)

        # Calculate L2 norm (should be close to 1.0 for normalized vectors)
        norm = sum(x**2 for x in embedding) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    def test_batch_processing(self, embedder):
        """Test batch processing with custom batch size."""
        # Create embedder with small batch size
        small_batch_embedder = Embedder(model_name="all-MiniLM-L6-v2", device="cpu", batch_size=2)

        texts = ["Text 1", "Text 2", "Text 3", "Text 4", "Text 5"]
        embeddings = small_batch_embedder.embed(texts)

        assert len(embeddings) == len(texts)
        assert all(len(emb) == small_batch_embedder.get_embedding_dimension() for emb in embeddings)

    def test_semantic_similarity(self, embedder):
        """Test that semantically similar texts have similar embeddings."""
        text1 = "The cat sits on the mat."
        text2 = "A cat is sitting on a mat."
        text3 = "The weather is nice today."

        emb1 = embedder.embed_single(text1)
        emb2 = embedder.embed_single(text2)
        emb3 = embedder.embed_single(text3)

        # Calculate cosine similarity (dot product for normalized vectors)
        def cosine_similarity(a, b):
            return sum(x * y for x, y in zip(a, b, strict=True))

        sim_1_2 = cosine_similarity(emb1, emb2)
        sim_1_3 = cosine_similarity(emb1, emb3)

        # Similar sentences should have higher similarity than dissimilar ones
        assert sim_1_2 > sim_1_3
        assert sim_1_2 > 0.5  # Should be fairly similar

    def test_embedder_basic_initialization(self):
        """Test initialization without using the embedder fixture."""
        embedder = Embedder(model_name="all-MiniLM-L6-v2", device="cpu")
        text = "Test embedding with explicitly created embedder."
        embedding = embedder.embed_single(text)

        assert isinstance(embedding, list)
        assert len(embedding) == embedder.get_embedding_dimension()
