import httpx

from cli.client import StashClient


def test_wiki_search_encodes_flat_query_params_and_authentication():
    def handle(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/me/vfs/wiki-search"
        assert dict(request.url.params) == {
            "query": "fan hub & seal",
            "scope": "shared",
            "limit": "7",
        }
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["X-Stash-Scope"] == "workspace-id"
        return httpx.Response(200, json={"results": [], "has_more": False})

    with StashClient("https://example.test", api_key="test-key", scope="workspace-id") as client:
        client._http.close()
        client._http = httpx.Client(
            base_url="https://example.test", transport=httpx.MockTransport(handle)
        )
        assert client.search_wiki("fan hub & seal", "shared", 7) == {
            "results": [],
            "has_more": False,
        }
