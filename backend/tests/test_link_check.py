import httpx

from backend.tasks import link_check


async def test_probe_never_requests_a_private_address():
    calls = []

    async def handler(request):
        calls.append(request.url)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await link_check._probe(client, "http://127.0.0.1/admin")

    assert verdict is None
    assert calls == []


async def test_probe_does_not_follow_a_redirect_to_metadata():
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await link_check._probe(client, "http://93.184.216.34/start")

    assert verdict is None
    assert calls == ["http://93.184.216.34/start"]
