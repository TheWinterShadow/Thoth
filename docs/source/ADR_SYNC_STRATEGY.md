# ADR: Incremental Sync Strategy

## Status
Accepted

## Context
The Thoth ingestion pipeline needs to efficiently synchronize with the GitLab handbook repository. A full re-ingestion on every update is inefficient and time-consuming. We need a strategy to detect and apply only incremental changes.

## Decision
We will implement a commit-based incremental synchronization strategy that:

1. **Tracks the last processed commit** using metadata storage
2. **Detects changes** by comparing the current commit with the last processed commit
3. **Applies incremental updates** by handling added, modified, and deleted files differently

### Architecture Components

#### 1. Metadata Storage
- Store the last processed commit SHA in `repo_metadata.json`
- Track processed files in `pipeline_state.json`
- Enable resume capability after interruptions

#### 2. Change Detection
The `HandbookRepoManager` class provides:
- `get_current_commit()` - Get the current repository commit SHA
- `get_changed_files(since_commit)` - Get files changed since a specific commit
- Uses Git diff to identify modifications efficiently

#### 3. Incremental Update Logic
The `IngestionPipeline` handles three types of changes:

**Added Files:**
- Process new markdown files through the full pipeline
- Generate chunks, embeddings, and store in vector database

**Modified Files:**
- Delete old document chunks from vector store (by file path metadata)
- Re-process file through chunking and embedding
- Insert updated chunks into vector store

**Deleted Files:**
- Remove all document chunks associated with the file from vector store
- Update pipeline state to remove from processed files list

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Start Incremental Sync                    │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Load Pipeline State   │
                    │ - last_commit         │
                    │ - processed_files     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Update Repository     │
                    │ (git pull)            │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Get Current Commit    │
                    │ (HEAD SHA)            │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Detect Changed Files  │
                    │ git diff --name-only  │
                    │ last_commit..HEAD     │
                    └───────────┬───────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Deleted  │    │ Modified │    │  Added   │
        │  Files   │    │  Files   │    │  Files   │
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │               │               │
             ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Delete   │    │ Delete   │    │ Process  │
        │ from     │    │ Old      │    │ File     │
        │ Vector   │    │ Chunks   │    │ -> Chunk │
        │ Store    │    └────┬─────┘    │ -> Embed │
        └────┬─────┘         │          └────┬─────┘
             │               ▼               │
             │          ┌──────────┐         │
             │          │ Process  │         │
             │          │ File     │         │
             │          │ -> Chunk │         │
             │          │ -> Embed │         │
             │          └────┬─────┘         │
             │               │               │
             └───────────────┼───────────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │ Update Pipeline State  │
                │ - last_commit          │
                │ - processed_files      │
                │ - statistics           │
                └────────────┬───────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │ Save State & Metadata  │
                └────────────────────────┘
```

### Implementation Details

#### File Status Detection
Using Git's capabilities to classify files:
```python
# Get all changed files
changed_files = repo.git.diff("--name-only", since_commit, "HEAD")

# Detect deleted files (in old commit but not in current)
all_files_old = {f for f in old_tree}
all_files_new = {f for f in new_tree}
deleted = all_files_old - all_files_new
added = all_files_new - all_files_old
modified = changed_files - added - deleted
```

#### Vector Store Updates
- Use file path metadata to query and delete specific document chunks
- ChromaDB `delete()` with `where` clause: `{"file_path": "/path/to/file.md"}`
- Ensures complete removal of outdated content

#### State Management
- Atomic updates to pipeline state after each batch
- Resume capability if interrupted during sync
- Track both successful and failed file operations

## Consequences

### Positive
- **Performance**: Only processes changed files, significantly faster than full re-ingestion
- **Efficiency**: Reduces embedding API calls and vector store operations
- **Scalability**: Handles large repositories with minimal overhead
- **Resume Capability**: Can continue after interruptions
- **Accuracy**: Ensures vector store reflects current repository state

### Negative
- **Complexity**: More complex than full re-ingestion
- **State Management**: Requires careful tracking of processed files
- **Edge Cases**: Must handle merge conflicts, force pushes, etc.

### Mitigation Strategies
- Comprehensive error handling and logging
- State validation on pipeline start
- Option to force full re-ingestion if state becomes inconsistent
- Regular backups of vector store and state files

## Alternatives Considered

### 1. Timestamp-Based Detection
**Rejected**: File modification timestamps are not reliable in Git repositories and can be affected by checkout operations.

### 2. Full Re-Ingestion Every Time
**Rejected**: Too slow and inefficient for frequent updates, especially with large repositories.

### 3. Event-Based Webhooks
**Considered for Future**: GitLab webhooks could trigger immediate syncs, but requires infrastructure and doesn't help with initial sync or manual updates.

## Implementation Notes

### Error Handling
- If Git operations fail, fall back to full re-ingestion
- Log all errors with context for debugging
- Continue processing other files if one fails

### Performance Optimizations
- Batch vector store deletions for modified files
- Parallel processing of independent files (future enhancement)
- Incremental state saves to enable resume

### Testing Considerations
- Unit tests for each change type (add, modify, delete)
- Integration tests for full sync workflow
- Edge cases: empty diffs, large changesets, conflicting states

## References
- [GitPython Documentation](https://gitpython.readthedocs.io/)
- [ChromaDB Delete Operations](https://docs.trychroma.com/reference/Collection#delete)
- [Git Diff Command](https://git-scm.com/docs/git-diff)
