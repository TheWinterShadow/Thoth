Ingestion Module
================

The ingestion module handles repository management, document chunking, and vector storage for the GitLab handbook.

Overview
--------

The ingestion module provides tools for managing Git repositories, processing markdown documents,
and storing document embeddings in a vector database. It includes features for cloning repositories,
tracking commit history, chunking markdown files, and semantic search capabilities.

Key Features
~~~~~~~~~~~~

* **Clone repositories** with automatic retry logic for reliability
* **Track commit history** to monitor repository changes
* **Save and load metadata** for persistent repository state
* **Detect changed files** between any two commits
* **Chunk markdown documents** intelligently based on headings and token limits
* **Store embeddings** in ChromaDB for semantic search
* **Search documents** using natural language queries
* **CRUD operations** for managing document vectors

Example Usage
~~~~~~~~~~~~~

Repository Management
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from pathlib import Path
   from thoth.ingestion.repo_manager import HandbookRepoManager

   # Initialize the repository manager
   manager = HandbookRepoManager(
       repo_url="https://gitlab.com/gitlab-com/content-sites/handbook.git",
       clone_path=Path.home() / ".thoth" / "handbook"
   )

   # Clone the repository
   repo_path = manager.clone_handbook()

   # Get current commit
   commit_sha = manager.get_current_commit()

   # Save metadata
   manager.save_metadata(commit_sha)

   # Update repository
   manager.update_repository()

   # Get changed files since last commit
   metadata = manager.load_metadata()
   if metadata:
       changed_files = manager.get_changed_files(metadata["commit_sha"])

Vector Store
^^^^^^^^^^^^

.. code-block:: python

   from thoth.ingestion.vector_store import VectorStore

   # Initialize vector store
   vector_store = VectorStore(
       persist_directory="./chroma_db",
       collection_name="handbook_docs"
   )

   # Add documents
   documents = [
       "Python is a programming language.",
       "JavaScript is used for web development."
   ]
   metadatas = [
       {"language": "python", "type": "definition"},
       {"language": "javascript", "type": "definition"}
   ]
   vector_store.add_documents(documents, metadatas=metadatas)

   # Search for similar documents
   results = vector_store.search_similar(
       query="programming languages",
       n_results=5
   )

   # Search with metadata filter
   python_docs = vector_store.search_similar(
       query="programming",
       where={"language": "python"}
   )

   # Delete documents
   vector_store.delete_documents(ids=["doc_1", "doc_2"])

Module Contents
---------------

Repository Manager
~~~~~~~~~~~~~~~~~~

.. automodule:: thoth.ingestion.repo_manager
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Markdown Chunker
~~~~~~~~~~~~~~~~

.. automodule:: thoth.ingestion.chunker
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Vector Store
~~~~~~~~~~~~

.. automodule:: thoth.ingestion.vector_store
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Package Contents
~~~~~~~~~~~~~~~~

.. automodule:: thoth.ingestion
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

