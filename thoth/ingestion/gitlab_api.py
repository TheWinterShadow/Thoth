"""GitLab API client with rate limiting, caching, and error handling."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, TypeVar
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Type variable for decorators
F = TypeVar("F", bound=Callable[..., Any])

# Constants
DEFAULT_BASE_URL = "https://gitlab.com/api/v4"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 2
CACHE_DEFAULT_TTL = 300  # 5 minutes
RATE_LIMIT_MARGIN = 10  # Safety margin for rate limit

# Error messages
MSG_AUTH_REQUIRED = "Authentication token required for this operation"
MSG_RATE_LIMIT_EXCEEDED = "Rate limit exceeded. Waiting {wait_time}s"
MSG_REQUEST_FAILED = "Request failed after {attempts} attempts: {error}"
MSG_INVALID_RESPONSE = "Invalid response from GitLab API: {error}"


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""


class GitLabAPIError(Exception):
    """Raised for GitLab API errors."""


class CacheEntry:
    """Represents a cached API response."""

    def __init__(self, data: Any, ttl: int = CACHE_DEFAULT_TTL):
        """Initialize cache entry.

        Args:
            data: Data to cache
            ttl: Time to live in seconds
        """
        self.data = data
        self.expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now(tz=timezone.utc) > self.expires_at


class GitLabAPIClient:
    """GitLab API client with rate limiting, caching, and error handling."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        logger: logging.Logger | None = None,
    ):
        """Initialize GitLab API client.

        Args:
            token: GitLab personal access token
            base_url: Base URL for GitLab API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            backoff_factor: Backoff factor for exponential backoff
            logger: Logger instance
        """
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

        # Initialize session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Set headers
        if self.token:
            self.session.headers.update({"PRIVATE-TOKEN": self.token})

        # Rate limiting tracking
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: datetime | None = None

        # Cache storage
        self._cache: dict[str, CacheEntry] = {}

    def _get_cache_key(self, endpoint: str, params: dict | None = None) -> str:
        """Generate cache key for endpoint and parameters.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Cache key string
        """
        param_str = ""
        if params:
            sorted_params = sorted(params.items())
            param_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        return f"{endpoint}?{param_str}" if param_str else endpoint

    def _get_from_cache(self, cache_key: str) -> Any | None:
        """Get data from cache if available and not expired.

        Args:
            cache_key: Cache key

        Returns:
            Cached data or None
        """
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired():
                self.logger.debug(f"Cache hit: {cache_key}")
                return entry.data
            # Remove expired entry
            del self._cache[cache_key]
            self.logger.debug(f"Cache expired: {cache_key}")
        return None

    def _add_to_cache(self, cache_key: str, data: Any, ttl: int = CACHE_DEFAULT_TTL) -> None:
        """Add data to cache.

        Args:
            cache_key: Cache key
            data: Data to cache
            ttl: Time to live in seconds
        """
        self._cache[cache_key] = CacheEntry(data, ttl)
        self.logger.debug(f"Cached: {cache_key} (TTL: {ttl}s)")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self.logger.info("Cache cleared")

    def _update_rate_limit_info(self, headers: Any) -> None:
        """Update rate limit information from response headers.

        Args:
            headers: Response headers
        """
        if "RateLimit-Remaining" in headers:
            self._rate_limit_remaining = int(headers["RateLimit-Remaining"])
            self.logger.debug(f"Rate limit remaining: {self._rate_limit_remaining}")

        if "RateLimit-Reset" in headers:
            reset_timestamp = int(headers["RateLimit-Reset"])
            self._rate_limit_reset = datetime.fromtimestamp(reset_timestamp, tz=timezone.utc)
            self.logger.debug(f"Rate limit resets at: {self._rate_limit_reset}")

    def _check_rate_limit(self) -> None:
        """Check if we're approaching rate limit and wait if necessary.

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_remaining < RATE_LIMIT_MARGIN
            and self._rate_limit_reset
        ):
            wait_time = (self._rate_limit_reset - datetime.now(tz=timezone.utc)).total_seconds()
            if wait_time > 0:
                self.logger.warning(MSG_RATE_LIMIT_EXCEEDED.format(wait_time=wait_time))
                time.sleep(wait_time + 1)  # Add 1 second buffer
                # Reset rate limit tracking
                self._rate_limit_remaining = None
                self._rate_limit_reset = None

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        data: dict | None = None,
        use_cache: bool = True,
        cache_ttl: int = CACHE_DEFAULT_TTL,
    ) -> Any:
        """Make HTTP request to GitLab API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            use_cache: Whether to use caching for GET requests
            cache_ttl: Cache time to live in seconds

        Returns:
            Response data

        Raises:
            GitLabAPIError: If request fails
            RateLimitError: If rate limit is exceeded
        """
        # Check cache for GET requests
        if method == "GET" and use_cache:
            cache_key = self._get_cache_key(endpoint, params)
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data

        # Check rate limit before making request
        self._check_rate_limit()

        # Construct URL
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            # Make request
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout,
            )

            # Update rate limit info
            self._update_rate_limit_info(response.headers)

            # Handle rate limit response
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                wait_time = int(retry_after)
                self.logger.warning(MSG_RATE_LIMIT_EXCEEDED.format(wait_time=wait_time))
                time.sleep(wait_time)
                # Retry the request
                return self._make_request(method, endpoint, params, data, use_cache, cache_ttl)

            # Raise for HTTP errors
            response.raise_for_status()

            # Parse response
            result = response.json() if response.content else None

            # Cache GET requests
            if method == "GET" and use_cache and result is not None:
                cache_key = self._get_cache_key(endpoint, params)
                self._add_to_cache(cache_key, result, cache_ttl)

            return result

        except requests.exceptions.RequestException as e:
            adapter = self.session.adapters["https://"]
            max_retries = getattr(adapter, "max_retries", None)
            attempts = max_retries.total + 1 if max_retries else 1
            error_msg = MSG_REQUEST_FAILED.format(
                attempts=attempts,
                error=str(e),
            )
            self.logger.exception(error_msg)
            raise GitLabAPIError(error_msg) from e
        except ValueError as e:
            error_msg = MSG_INVALID_RESPONSE.format(error=str(e))
            self.logger.exception(error_msg)
            raise GitLabAPIError(error_msg) from e

    def get(
        self,
        endpoint: str,
        params: dict | None = None,
        use_cache: bool = True,
        cache_ttl: int = CACHE_DEFAULT_TTL,
    ) -> Any:
        """Make GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            use_cache: Whether to use caching
            cache_ttl: Cache time to live in seconds

        Returns:
            Response data
        """
        return self._make_request("GET", endpoint, params, use_cache=use_cache, cache_ttl=cache_ttl)

    def post(self, endpoint: str, data: dict | None = None) -> Any:
        """Make POST request.

        Args:
            endpoint: API endpoint
            data: Request body data

        Returns:
            Response data
        """
        return self._make_request("POST", endpoint, data=data, use_cache=False)

    def put(self, endpoint: str, data: dict | None = None) -> Any:
        """Make PUT request.

        Args:
            endpoint: API endpoint
            data: Request body data

        Returns:
            Response data
        """
        return self._make_request("PUT", endpoint, data=data, use_cache=False)

    def delete(self, endpoint: str) -> Any:
        """Make DELETE request.

        Args:
            endpoint: API endpoint

        Returns:
            Response data
        """
        return self._make_request("DELETE", endpoint, use_cache=False)

    # =========================================================================
    # Project API Methods
    # =========================================================================

    def get_project(self, project_id: str, use_cache: bool = True) -> dict[str, Any]:
        """Get project details.

        Args:
            project_id: Project ID or URL-encoded path
            use_cache: Whether to use caching

        Returns:
            Project data
        """
        endpoint = f"projects/{project_id}"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    def list_projects(
        self,
        params: dict | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """List projects.

        Args:
            params: Query parameters (e.g., {'per_page': 100, 'page': 1})
            use_cache: Whether to use caching

        Returns:
            List of projects
        """
        return self.get("projects", params=params, use_cache=use_cache)  # type: ignore[no-any-return]

    # =========================================================================
    # Repository API Methods
    # =========================================================================

    def get_repository_tree(
        self,
        project_id: str,
        path: str = "",
        ref: str = "main",
        recursive: bool = False,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Get repository tree.

        Args:
            project_id: Project ID or URL-encoded path
            path: Path inside repository
            ref: Branch/tag name
            recursive: Get tree recursively
            use_cache: Whether to use caching

        Returns:
            List of repository tree items
        """
        endpoint = f"projects/{project_id}/repository/tree"
        params = {
            "path": path,
            "ref": ref,
            "recursive": str(recursive).lower(),
        }
        return self.get(endpoint, params=params, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_file(
        self,
        project_id: str,
        file_path: str,
        ref: str = "main",
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get file content from repository.

        Args:
            project_id: Project ID or URL-encoded path
            file_path: Path to file in repository
            ref: Branch/tag name
            use_cache: Whether to use caching

        Returns:
            File data including content
        """
        endpoint = f"projects/{project_id}/repository/files/{quote(file_path, safe='')}"
        params = {"ref": ref}
        return self.get(endpoint, params=params, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_commits(
        self,
        project_id: str,
        ref: str = "main",
        since: str | None = None,
        until: str | None = None,
        path: str | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Get commits for a project.

        Args:
            project_id: Project ID or URL-encoded path
            ref: Branch/tag name
            since: Only commits after this date (ISO 8601 format)
            until: Only commits before this date (ISO 8601 format)
            path: Only commits that include this file path
            use_cache: Whether to use caching

        Returns:
            List of commits
        """
        endpoint = f"projects/{project_id}/repository/commits"
        params = {"ref_name": ref}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if path:
            params["path"] = path
        return self.get(endpoint, params=params, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_commit(
        self,
        project_id: str,
        commit_sha: str,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get a single commit.

        Args:
            project_id: Project ID or URL-encoded path
            commit_sha: Commit SHA
            use_cache: Whether to use caching

        Returns:
            Commit data
        """
        endpoint = f"projects/{project_id}/repository/commits/{commit_sha}"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_commit_diff(
        self,
        project_id: str,
        commit_sha: str,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Get diff of a commit.

        Args:
            project_id: Project ID or URL-encoded path
            commit_sha: Commit SHA
            use_cache: Whether to use caching

        Returns:
            List of diffs
        """
        endpoint = f"projects/{project_id}/repository/commits/{commit_sha}/diff"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    # =========================================================================
    # Branch API Methods
    # =========================================================================

    def list_branches(
        self,
        project_id: str,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """List branches.

        Args:
            project_id: Project ID or URL-encoded path
            use_cache: Whether to use caching

        Returns:
            List of branches
        """
        endpoint = f"projects/{project_id}/repository/branches"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_branch(
        self,
        project_id: str,
        branch: str,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get branch details.

        Args:
            project_id: Project ID or URL-encoded path
            branch: Branch name
            use_cache: Whether to use caching

        Returns:
            Branch data
        """
        endpoint = f"projects/{project_id}/repository/branches/{quote(branch, safe='')}"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    # =========================================================================
    # Merge Request API Methods
    # =========================================================================

    def list_merge_requests(
        self,
        project_id: str,
        state: str = "opened",
        params: dict | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """List merge requests.

        Args:
            project_id: Project ID or URL-encoded path
            state: State filter ('opened', 'closed', 'merged', 'all')
            params: Additional query parameters
            use_cache: Whether to use caching

        Returns:
            List of merge requests
        """
        endpoint = f"projects/{project_id}/merge_requests"
        request_params = {"state": state}
        if params:
            request_params.update(params)
        return self.get(endpoint, params=request_params, use_cache=use_cache)  # type: ignore[no-any-return]

    def get_merge_request(
        self,
        project_id: str,
        mr_iid: int,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get merge request details.

        Args:
            project_id: Project ID or URL-encoded path
            mr_iid: Merge request IID
            use_cache: Whether to use caching

        Returns:
            Merge request data
        """
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    # =========================================================================
    # User API Methods
    # =========================================================================

    def get_current_user(self, use_cache: bool = True) -> dict[str, Any]:
        """Get current authenticated user.

        Args:
            use_cache: Whether to use caching

        Returns:
            User data

        Raises:
            GitLabAPIError: If not authenticated
        """
        if not self.token:
            raise GitLabAPIError(MSG_AUTH_REQUIRED)
        return self.get("user", use_cache=use_cache)  # type: ignore[no-any-return]

    def get_user(self, user_id: int, use_cache: bool = True) -> dict[str, Any]:
        """Get user details.

        Args:
            user_id: User ID
            use_cache: Whether to use caching

        Returns:
            User data
        """
        endpoint = f"users/{user_id}"
        return self.get(endpoint, use_cache=use_cache)  # type: ignore[no-any-return]

    # =========================================================================
    # Rate Limit Info
    # =========================================================================

    def get_rate_limit_info(self) -> dict[str, Any]:
        """Get current rate limit information.

        Returns:
            Dictionary with rate limit info
        """
        return {
            "remaining": self._rate_limit_remaining,
            "reset_at": (self._rate_limit_reset.isoformat() if self._rate_limit_reset else None),
        }
