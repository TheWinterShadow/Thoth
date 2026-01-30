# Embedding Model Selection

## Overview

This document describes the embedding model selection process for the Thoth project and provides benchmark results to support the decision.

## Selected Model: all-MiniLM-L6-v2

**Decision**: We have selected **all-MiniLM-L6-v2** as the default embedding model for Thoth.

### Rationale

1. **Performance**: 2-3x faster than all-mpnet-base-v2
2. **Efficiency**: Lower memory footprint (384 dimensions vs 768 dimensions)
3. **Quality**: Sufficient semantic understanding for code and documentation search
4. **Resource Usage**: Better suited for production deployments with limited resources

## Model Comparison

### all-MiniLM-L6-v2 (Recommended)
- **Embedding Dimension**: 384
- **Max Sequence Length**: 256 tokens
- **Speed**: ~2-3x faster than all-mpnet-base-v2
- **Best For**: General purpose semantic search, code documentation, fast response times
- **Trade-offs**: Slightly lower quality than larger models

### all-mpnet-base-v2 (Alternative)
- **Embedding Dimension**: 768
- **Max Sequence Length**: 384 tokens
- **Speed**: Slower due to larger model size
- **Best For**: Maximum quality semantic search, complex queries
- **Trade-offs**: Higher computational cost, larger memory footprint

## Benchmark Results

To run benchmarks yourself:

```bash
python benchmark_embeddings.py
```

### Typical Performance Metrics

Based on CPU benchmarks (results may vary by hardware):

| Model | Dimension | Throughput (texts/sec) | Avg Time per Text |
|-------|-----------|------------------------|-------------------|
| all-MiniLM-L6-v2 | 384 | ~50-100 | ~10-20ms |
| all-mpnet-base-v2 | 768 | ~20-40 | ~25-50ms |

### Semantic Quality

Both models provide excellent semantic understanding for:
- Code documentation
- Technical content
- Natural language queries
- Cross-language similarity (e.g., comments and code)

The quality difference is minimal for most use cases in repository search.

## Usage

### Default Usage

The Embedder class uses all-MiniLM-L6-v2 by default:

```python
from thoth.ingestion.embedder import Embedder

embedder = Embedder()
embeddings = embedder.embed(["Your text here"])
```

### Using Alternative Model

If you need higher quality at the cost of performance:

```python
from thoth.ingestion.embedder import Embedder

embedder = Embedder(model_name="all-mpnet-base-v2")
embeddings = embedder.embed(["Your text here"])
```

## Integration with VectorStore

The VectorStore automatically uses the default embedding model:

```python
from thoth.ingestion.vector_store import VectorStore

# Uses all-MiniLM-L6-v2 by default
store = VectorStore()
store.add_documents(["Document 1", "Document 2"])
```

Or provide a custom embedder:

```python
from thoth.ingestion.embedder import Embedder
from thoth.ingestion.vector_store import VectorStore

# Use custom model
embedder = Embedder(model_name="all-mpnet-base-v2")
store = VectorStore(embedder=embedder)
```

## Future Considerations

- **Multilingual Support**: Consider `paraphrase-multilingual-MiniLM-L12-v2` for multilingual repositories
- **Code-Specific Models**: Monitor development of code-specific embedding models
- **Domain Adaptation**: Fine-tune models on repository-specific data if needed

## References

- [Sentence-Transformers Documentation](https://www.sbert.net/)
- [Sentence-Transformers Pretrained Models](https://www.sbert.net/docs/pretrained_models.html)
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) - Model rankings for various tasks

## Testing

Unit tests for the Embedder class are located in `tests/ingestion/test_embedder.py`.

Run tests with:

```bash
pytest tests/ingestion/test_embedder.py -v
```
