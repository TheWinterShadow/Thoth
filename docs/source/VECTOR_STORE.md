# Vector Store Module

## Overview

The Vector Store module provides a wrapper around ChromaDB for storing and querying document embeddings with semantic search capabilities. It enables efficient storage, retrieval, and similarity search of documents with associated metadata.

## Installation

ChromaDB is included as a dependency when you install Thoth:

```bash
pip install thoth
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

### Basic Usage

```python
from thoth.ingestion.vector_store import VectorStore

# Initialize the vector store
vector_store = VectorStore(
    persist_directory="./my_vector_db",
    collection_name="my_documents"
)

# Add documents
documents = [
    "Python is a high-level programming language.",
    "JavaScript is widely used for web development.",
    "Machine learning is a subset of artificial intelligence."
]
vector_store.add_documents(documents)

# Search for similar documents
results = vector_store.search_similar(
    query="programming languages",
    n_results=2
)
print(results["documents"])
```

### Adding Documents with Metadata

```python
documents = [
    "Introduction to Python programming",
    "Advanced Python techniques",
    "JavaScript basics for beginners"
]

metadatas = [
    {"language": "python", "level": "beginner", "topic": "intro"},
    {"language": "python", "level": "advanced", "topic": "techniques"},
    {"language": "javascript", "level": "beginner", "topic": "basics"}
]

ids = ["doc_python_1", "doc_python_2", "doc_js_1"]

vector_store.add_documents(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)
```

### Searching with Filters

```python
# Search only within Python documents
results = vector_store.search_similar(
    query="advanced programming concepts",
    n_results=5,
    where={"language": "python"}
)

# Search for beginner-level content
results = vector_store.search_similar(
    query="getting started",
    n_results=3,
    where={"level": "beginner"}
)
```

### Retrieving Documents

```python
# Get all documents
all_docs = vector_store.get_documents()

# Get specific documents by ID
specific_docs = vector_store.get_documents(
    ids=["doc_python_1", "doc_python_2"]
)

# Get documents with metadata filter
python_docs = vector_store.get_documents(
    where={"language": "python"}
)

# Limit the number of results
limited_docs = vector_store.get_documents(limit=10)
```

### Deleting Documents

```python
# Delete by IDs
vector_store.delete_documents(ids=["doc_python_1", "doc_js_1"])

# Delete by metadata filter
vector_store.delete_documents(where={"level": "beginner"})
```

## API Reference

### VectorStore Class

#### `__init__(persist_directory: str = "./chroma_db", collection_name: str = "thoth_documents")`

Initialize a new VectorStore instance.

**Parameters:**
- `persist_directory` (str): Directory path for ChromaDB persistence. Defaults to "./chroma_db"
- `collection_name` (str): Name of the ChromaDB collection. Defaults to "thoth_documents"

**Example:**
```python
vector_store = VectorStore(
    persist_directory="./data/embeddings",
    collection_name="handbook_chunks"
)
```

---

#### `add_documents(documents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> None`

Add documents to the vector store.

**Parameters:**
- `documents` (List[str]): List of document texts to add
- `metadatas` (Optional[List[Dict[str, Any]]]): Optional list of metadata dictionaries for each document
- `ids` (Optional[List[str]]): Optional list of unique IDs. If not provided, IDs will be auto-generated

**Raises:**
- `ValueError`: If list lengths don't match

**Example:**
```python
vector_store.add_documents(
    documents=["Doc 1", "Doc 2"],
    metadatas=[{"type": "tutorial"}, {"type": "reference"}],
    ids=["tutorial_1", "reference_1"]
)
```

---

#### `search_similar(query: str, n_results: int = 5, where: Optional[Dict[str, Any]] = None, where_document: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

Search for similar documents using semantic similarity.

**Parameters:**
- `query` (str): Query text to search for
- `n_results` (int): Number of results to return. Defaults to 5
- `where` (Optional[Dict[str, Any]]): Optional metadata filter conditions
- `where_document` (Optional[Dict[str, Any]]): Optional document content filter conditions

**Returns:**
- Dict containing:
  - `ids`: List of document IDs
  - `documents`: List of document texts
  - `metadatas`: List of metadata dicts
  - `distances`: List of distance scores (lower is more similar)

**Example:**
```python
results = vector_store.search_similar(
    query="Python functions",
    n_results=3,
    where={"language": "python", "level": "intermediate"}
)
```

---

#### `delete_documents(ids: Optional[List[str]] = None, where: Optional[Dict[str, Any]] = None) -> None`

Delete documents from the vector store.

**Parameters:**
- `ids` (Optional[List[str]]): Optional list of document IDs to delete
- `where` (Optional[Dict[str, Any]]): Optional metadata filter for documents to delete

**Raises:**
- `ValueError`: If neither ids nor where is provided

**Example:**
```python
# Delete by IDs
vector_store.delete_documents(ids=["doc_1", "doc_2"])

# Delete by metadata
vector_store.delete_documents(where={"status": "archived"})
```

---

#### `get_documents(ids: Optional[List[str]] = None, where: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> Dict[str, Any]`

Retrieve documents from the vector store.

**Parameters:**
- `ids` (Optional[List[str]]): Optional list of document IDs to retrieve
- `where` (Optional[Dict[str, Any]]): Optional metadata filter
- `limit` (Optional[int]): Optional maximum number of documents to return

**Returns:**
- Dict containing:
  - `ids`: List of document IDs
  - `documents`: List of document texts
  - `metadatas`: List of metadata dicts

**Example:**
```python
# Get specific documents
docs = vector_store.get_documents(ids=["doc_1", "doc_2"])

# Get filtered documents
python_docs = vector_store.get_documents(
    where={"language": "python"},
    limit=10
)
```

---

#### `get_document_count() -> int`

Get the total number of documents in the collection.

**Returns:**
- int: Number of documents in the collection

**Example:**
```python
count = vector_store.get_document_count()
print(f"Total documents: {count}")
```

---

#### `reset() -> None`

Reset the collection by deleting all documents.

**Warning:** This operation cannot be undone.

**Example:**
```python
vector_store.reset()  # Deletes all documents
```

## Advanced Usage

### Persistence

Data is automatically persisted to disk when you add, update, or delete documents. The data persists across different VectorStore instances as long as they use the same `persist_directory` and `collection_name`:

```python
# First session
store1 = VectorStore(persist_directory="./db", collection_name="docs")
store1.add_documents(["Document 1", "Document 2"])

# Later session (data persists)
store2 = VectorStore(persist_directory="./db", collection_name="docs")
count = store2.get_document_count()  # Returns 2
```

### Metadata Filtering

ChromaDB supports various metadata filter operations:

```python
# Exact match
results = vector_store.search_similar(
    query="tutorial",
    where={"level": "beginner"}
)

# Multiple conditions (AND)
results = vector_store.search_similar(
    query="tutorial",
    where={"language": "python", "level": "beginner"}
)
```

### Working with Large Document Sets

When working with large numbers of documents, consider:

1. **Batch Processing**: Add documents in batches for better performance
2. **Unique IDs**: Use meaningful, unique IDs for easier management
3. **Metadata**: Use rich metadata for better filtering and organization
4. **Limits**: Use the `limit` parameter to control result sizes

```python
# Batch processing example
def add_documents_in_batches(docs, batch_size=100):
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        vector_store.add_documents(batch)
        print(f"Added batch {i // batch_size + 1}")
```

## Integration with Other Modules

The Vector Store module is designed to work seamlessly with other Thoth modules:

### With Chunker

```python
from thoth.ingestion.chunker import MarkdownChunker
from thoth.ingestion.vector_store import VectorStore

# Initialize components
chunker = MarkdownChunker()
vector_store = VectorStore()

# Process and store document chunks
with open("handbook.md", "r") as f:
    content = f.read()

chunks = chunker.chunk(content)

# Add chunks with metadata
documents = [chunk.content for chunk in chunks]
metadatas = [
    {
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "heading": chunk.heading,
        "level": chunk.level
    }
    for chunk in chunks
]

vector_store.add_documents(documents, metadatas=metadatas)
```

### With Repository Manager

```python
from thoth.ingestion.repo_manager import HandbookRepoManager
from thoth.ingestion.vector_store import VectorStore

# Initialize components
repo_manager = HandbookRepoManager()
vector_store = VectorStore()

# Clone and process repository
repo_path = repo_manager.clone_handbook()

# Process files and add to vector store
# (Implementation details depend on your workflow)
```

## Testing

The module includes comprehensive unit tests using `unittest.TestCase`. To run the tests:

```bash
# Run all vector store tests
python -m unittest tests.ingestion.test_vector_store

# Run with verbose output
python -m unittest tests.ingestion.test_vector_store -v

# Run specific test
python -m unittest tests.ingestion.test_vector_store.TestVectorStore.test_add_documents
```

## Performance Considerations

- **Embedding Model**: ChromaDB uses the default `all-MiniLM-L6-v2` embedding model, which provides a good balance of speed and accuracy
- **Batch Operations**: For large datasets, add documents in batches to improve performance
- **Distance Metric**: The collection uses cosine similarity by default
- **Persistence**: Data is written to disk automatically; no manual save is required

## Troubleshooting

### Common Issues

**Issue**: "Collection already exists" error

**Solution**: Use `get_or_create_collection()` (already used internally) or reset the collection:
```python
vector_store.reset()
```

**Issue**: Memory usage is high with large document sets

**Solution**: Consider:
- Splitting documents into smaller chunks
- Using metadata filters to limit query scope
- Periodically clearing unused documents

**Issue**: Search results are not relevant

**Solution**:
- Refine your query text to be more specific
- Use metadata filters to narrow the search space
- Adjust `n_results` to see more or fewer results
- Consider the quality and content of stored documents

## See Also

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Chunker Module](./chunker.md)
- [Repository Manager Module](./repo_manager.md)
- [Architecture Guide](../ARCHITECTURE.md)
