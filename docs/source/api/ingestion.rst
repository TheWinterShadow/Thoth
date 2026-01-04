Ingestion Module
================

The ingestion module handles repository cloning, tracking, and management for the GitLab handbook.

Overview
--------

The ingestion module provides tools for managing Git repositories, with a focus on the GitLab handbook.
It includes features for cloning repositories with retry logic, tracking commit history, managing metadata,
and detecting file changes between commits.

Key Features
~~~~~~~~~~~~

* **Clone repositories** with automatic retry logic for reliability
* **Track commit history** to monitor repository changes
* **Save and load metadata** for persistent repository state
* **Detect changed files** between any two commits
* **Force re-cloning** when repository updates are needed

Example Usage
~~~~~~~~~~~~~

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

Module Contents
---------------

Repository Manager
~~~~~~~~~~~~~~~~~~

.. automodule:: thoth.ingestion.repo_manager
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

