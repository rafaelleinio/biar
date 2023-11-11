import datetime
import ssl
from asyncio import AbstractEventLoop, gather
from unittest.mock import AsyncMock, patch

import aiodns
import pytest
from aiohttp.http_exceptions import HttpProcessingError
from aioresponses import aioresponses
from pydantic import BaseModel
from yarl import URL

import biar

BASE_URL = "https://api.com/v1"


@pytest.fixture
def mock_server() -> aioresponses:
    with aioresponses() as m:
        yield m


class TestRequest:
    @pytest.mark.asyncio
    async def test_request_structured(self, mock_server: aioresponses):
        # arrange
        class MyModel(BaseModel):
            key: str

        response_headers = {"Content-Type": "application/json"}
        response_json_content = {"key": "value"}
        mock_server.get(
            url=BASE_URL, headers=response_headers, payload=response_json_content
        )
        target_response = biar.StructuredResponse(
            url=URL(BASE_URL),
            status_code=200,
            headers=response_headers,
            json_content=response_json_content,
            structured_content=MyModel(key="value"),
        )

        # act
        output_response = await biar.request_structured(
            model=MyModel,
            url=BASE_URL,
            method="GET",
        )

        # assert
        assert target_response == output_response

    @pytest.mark.asyncio
    async def test_request_retry_success(self, mock_server: aioresponses):
        # arrange
        mock_server.get(url=BASE_URL, status=500)
        mock_server.get(url=BASE_URL, status=200)

        # act
        start_ts = datetime.datetime.utcnow()
        output_response = await biar.request(
            url=BASE_URL,
            method="GET",
            download_json_content=False,
            retryer=biar.Retryer(
                attempts=2,
                min_delay=1,
                max_delay=1,
            ),
        )
        end_ts = datetime.datetime.utcnow()
        elapsed_time = (end_ts - start_ts).total_seconds()

        # assert
        assert output_response.status_code == 200
        assert 1 < elapsed_time < 2

    @pytest.mark.asyncio
    async def test_request_retry_exception(self, mock_server: aioresponses):
        # arrange
        mock_server.get(url=BASE_URL, status=500)
        mock_server.get(url=BASE_URL, exception=HttpProcessingError())
        mock_server.get(url=BASE_URL, exception=HttpProcessingError())
        retrier = biar.Retryer(attempts=2, max_delay=0)

        # act and assert
        with pytest.raises(HttpProcessingError):
            _ = await biar.request(
                url=BASE_URL,
                method="GET",
                retryer=retrier,
            )

    @pytest.mark.asyncio
    async def test_request_retry_status_fail(self, mock_server: aioresponses):
        # arrange
        mock_server.get(url=BASE_URL, status=500)
        mock_server.get(url=BASE_URL, status=500)
        mock_server.get(url=BASE_URL, status=500)
        retrier = biar.Retryer(attempts=2, max_delay=0)

        # act and assert
        with pytest.raises(biar.ResponseEvaluationError):
            _ = await biar.request(
                url=BASE_URL,
                method="GET",
                retryer=retrier,
            )

    def test_request_rate_limit(
        self, event_loop: AbstractEventLoop, mock_server: aioresponses
    ):
        # arrange
        mock_server.get(url=BASE_URL, status=200)
        mock_server.get(url=BASE_URL, status=200)
        mock_server.get(url=BASE_URL, status=200)
        rate_limiter = biar.RateLimiter(rate=2, time_frame=1, identity="api")
        async_requests = [
            biar.request(url=BASE_URL, method="GET", rate_limiter=rate_limiter),
            biar.request(url=BASE_URL, method="GET", rate_limiter=rate_limiter),
            biar.request(url=BASE_URL, method="GET", rate_limiter=rate_limiter),
        ]

        # act
        start_ts = datetime.datetime.utcnow()
        _ = event_loop.run_until_complete(gather(*async_requests))
        end_ts = datetime.datetime.utcnow()
        elapsed_time = (end_ts - start_ts).total_seconds()

        # assert
        assert 1 < elapsed_time < 2


def test_get_ssl_context():
    # arrange
    extra_certificate = """
-----BEGIN CERTIFICATE-----
MIICVDCCAdugAwIBAgIQZ3SdjXfYO2rbIvT/WeK/zjAKBggqhkjOPQQDAzBsMQsw
CQYDVQQGEwJHUjE3MDUGA1UECgwuSGVsbGVuaWMgQWNhZGVtaWMgYW5kIFJlc2Vh
cmNoIEluc3RpdHV0aW9ucyBDQTEkMCIGA1UEAwwbSEFSSUNBIFRMUyBFQ0MgUm9v
dCBDQSAyMDIxMB4XDTIxMDIxOTExMDExMFoXDTQ1MDIxMzExMDEwOVowbDELMAkG
A1UEBhMCR1IxNzA1BgNVBAoMLkhlbGxlbmljIEFjYWRlbWljIGFuZCBSZXNlYXJj
aCBJbnN0aXR1dGlvbnMgQ0ExJDAiBgNVBAMMG0hBUklDQSBUTFMgRUNDIFJvb3Qg
Q0EgMjAyMTB2MBAGByqGSM49AgEGBSuBBAAiA2IABDgI/rGgltJ6rK9JOtDA4MM7
KKrxcm1lAEeIhPyaJmuqS7psBAqIXhfyVYf8MLA04jRYVxqEU+kw2anylnTDUR9Y
STHMmE5gEYd103KUkE+bECUqqHgtvpBBWJAVcqeht6NCMEAwDwYDVR0TAQH/BAUw
AwEB/zAdBgNVHQ4EFgQUyRtTgRL+BNUW0aq8mm+3oJUZbsowDgYDVR0PAQH/BAQD
AgGGMAoGCCqGSM49BAMDA2cAMGQCMBHervjcToiwqfAircJRQO9gcS3ujwLEXQNw
SaSS6sUUiHCm0w2wqsosQJz76YJumgIwK0eaB8bRwoF8yguWGEEbo/QwCZ61IygN
nxS2PFOiTAZpffpskcYqSUXm7LcT4Tps
-----END CERTIFICATE-----
"""
    # act
    ssl_context = biar.get_ssl_context(extra_certificate=extra_certificate)

    # assert
    isinstance(ssl_context, ssl.SSLContext)


class TestIsHostReachableService:
    @pytest.mark.asyncio
    async def test_is_host_reachable(self):
        # act
        with patch("aiodns.DNSResolver.query", new=AsyncMock()) as mock:
            output = await biar.is_host_reachable(host="google.com")

        # assert
        assert output is True
        mock.assert_called_once_with("google.com", qtype="A")

    @pytest.mark.asyncio
    async def test_is_host_reachable_error(self):
        # arrange
        async def side_effect(*args, **kwargs):
            raise aiodns.error.DNSError

        # act
        with patch("aiodns.DNSResolver.query", side_effect=side_effect) as mock:
            output = await biar.is_host_reachable(host="google.com")

        # assert
        assert output is False
        assert "google.com" in mock.mock_calls[0].args
