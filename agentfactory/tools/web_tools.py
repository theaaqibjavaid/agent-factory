"""
Web Tools — Search, fetch, and scrape web content.

These tools integrate with search APIs (Tavily, DuckDuckGo) and
HTTP clients for web research.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from agentfactory.base_tools import tool, SafetyLevel

logger = logging.getLogger(__name__)


@tool("web_search", category="web", tags=["web", "search"])
def web_search(query: str, num_results: int = 5, api_key: Optional[str] = None) -> str:
    """
    Search the web using Tavily (primary) or DuckDuckGo (fallback).

    Args:
        query: Search query string
        num_results: Number of results to return (max 10)
        api_key: Tavily API key (defaults to env var)

    Returns:
        Formatted search results
    """
    tavily_key = api_key or os.getenv("TAVILY_API_KEY")

    if tavily_key:
        return _tavily_search(query, num_results, tavily_key)
    else:
        return _duckduckgo_search(query, num_results)


@tool("web_fetch", category="web", tags=["web", "fetch"])
def web_fetch(url: str, max_length: int = 50000, summarize: bool = True) -> str:
    """
    Fetch and read a web page.

    Args:
        url: URL to fetch
        max_length: Maximum content length to return
        summarize: Whether to summarize long content

    Returns:
        Page content (optionally summarized)
    """
    try:
        import requests

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AgentFactory/1.0; +https://github.com/aaqarchitect/agentfactory)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        content = response.text

        # Strip HTML tags if any
        import re
        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > max_length:
            if summarize and _has_llm_access():
                return _summarize_text(text[:max_length], url)
            else:
                text = text[:max_length] + "\n... [truncated]"

        return f"URL: {url}\n\n{text}"

    except requests.exceptions.RequestException as e:
        return f"Error fetching {url}: {str(e)}"


@tool("web_scrape_links", category="web", tags=["web", "scrape"])
def web_scrape_links(url: str, max_links: int = 20) -> str:
    """
    Extract all links from a web page.

    Args:
        url: URL to scrape
        max_links: Maximum number of links to return

    Returns:
        List of found URLs
    """
    try:
        import requests
        from urllib.parse import urljoin, urlparse

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        import re
        # Find all href attributes
        href_pattern = r'href=["\']([^"\']+)["\']'
        matches = re.findall(href_pattern, response.text)

        # Convert relative URLs to absolute
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        links = []
        seen = set()
        for href in matches[:max_links]:
            absolute = urljoin(base, href)
            if absolute not in seen and not absolute.startswith("javascript:"):
                seen.add(absolute)
                links.append(absolute)

        return f"Found {len(links)} links on {url}:\n" + "\n".join(links)

    except Exception as e:
        return f"Error scraping links from {url}: {str(e)}"


def _tavily_search(query: str, num_results: int, api_key: str) -> str:
    """Search using Tavily API."""
    try:
        import requests

        response = requests.post(
            "https://api.tavily.ai/search",
            json={
                "api_key": api_key,
                "query": query,
                "num_results": num_results,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return f"No results found for: {query}"

        formatted = []
        formatted.append(f"Search results for: {query}\n")
        formatted.append(f"Tavily response time: {data.get('response_time', 'N/A')}s\n")

        for i, r in enumerate(results, 1):
            formatted.append(
                f"{i}. {r.get('title', 'Untitled')}\n"
                f"   URL: {r.get('url', 'No URL')}\n"
                f"   {r.get('content', '')[:300]}\n"
            )

        return "\n".join(formatted)

    except Exception as e:
        return f"Tavily search error: {str(e)}. Falling back to DuckDuckGo.\n" + _duckduckgo_search(query, num_results)


def _duckduckgo_search(query: str, num_results: int) -> str:
    """Search using DuckDuckGo (no API key required)."""
    try:
        from duckduckgo_search import DDGS

        formatted = []
        formatted.append(f"Search results for: {query}\n")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

            for i, r in enumerate(results, 1):
                formatted.append(
                    f"{i}. {r.get('title', 'Untitled')}\n"
                    f"   URL: {r.get('href', 'No URL')}\n"
                    f"   {r.get('body', '')[:300]}\n"
                )

        return "\n".join(formatted)

    except ImportError:
        return (
            "Web search requires either:\n"
            "  - Tavily: Set TAVILY_API_KEY environment variable, or\n"
            "  - DuckDuckGo: pip install duckduckgo-search\n"
            f"\nQuery was: {query}"
        )
    except Exception as e:
        return f"Search error: {str(e)}"


def _has_llm_access() -> bool:
    """Check if LLM API keys are available."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def _summarize_text(text: str, url: str) -> str:
    """Use an LLM to summarize text (fallback to truncation)."""
    try:
        from agentfactory.llm_manager import FailoverLLMManager

        manager = FailoverLLMManager()
        prompt = f"Summarize this web page content concisely (max 500 words):\n\n{text[:8000]}"
        summary = manager.generate_text([{"role": "user", "content": prompt}], max_tokens=1000)

        return f"URL: {url}\n\nSummary:\n{summary}"

    except Exception:
        return f"URL: {url}\n\n{text[:5000]}... [truncated]"
