import asyncio
import logging
import ssl
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import aiodns
import aiohttp
import certifi
import tenacity
from aiohttp import ClientResponseError
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate
from yarl import URL

from biar.user_agents import get_user_agent

# PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class ProxyConfig(BaseModel):
    """Proxy configuration.

    Attributes:
        host: proxy address.
        headers: additional configuration required by the proxy.
        ssl_cadata: certificate as a string required by some proxies to use SSL.

    """

    host: str
    headers: Optional[Dict[str, Any]] = None
    ssl_cadata: Optional[str] = None


class Response(BaseModel):
    """Attributes from the http request response.

    Attributes:
        url: final url after (possible) redirects.
        status_code: HTTP status code.
        headers: headers in the response.
        json_content: response content as json dict.
        text_content: raw response content as a string.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: URL
    status_code: int
    headers: Dict[str, Any] = Field(default_factory=dict)
    json_content: Dict[str, JsonValue] = Field(default_factory=dict)
    text_content: str = ""


class StructuredResponse(Response):
    """Attributes from the http request response.

    Attributes:
        url: final url after (possible) redirects.
        status_code: HTTP status code.
        headers: headers in the response.
        json_content: response content as json dict.
        text_content: raw response content as a string.
        structured_content: response content as a pydantic model.

    """

    structured_content: Any


class ResponseEvaluationError(Exception):
    """Base Exception for non-OK responses."""


def evaluate_response(
    http_response: Response, acceptable_codes: Optional[List[int]] = None
) -> None:
    """Evaluate a response and raise an exception if it's not OK.

    Args:
        http_response: response object.
        acceptable_codes: list of acceptable status codes.

    Raises:
        ResponseEvaluationError if the response is not OK.

    """
    if http_response.status_code not in (acceptable_codes or [200]):
        raise ResponseEvaluationError(
            f"Error: status={http_response.status_code}, "
            f"Text content (if loaded): {str(http_response.text_content)}"
        )


class Retryer(BaseModel):
    """Retry logic with exponential backoff strategy.

    Attributes:
        attempts: number of attempts.
            `attempts=1` means only one try and no subsequent retry attempts.
        min_delay: number of seconds as the starting delay.
        max_delay: number of seconds as the maximum achieving delay.
        retry_if_exception_in: retry if exception found in this tuple.
            A ResponseEvaluationError is always added dynamically to be retried.

    """

    attempts: int = 1
    min_delay: int = 0
    max_delay: int = 10
    retry_if_exception_in: Tuple[Type[BaseException], ...] = (
        ClientResponseError,
        asyncio.TimeoutError,
    )

    @property
    def retrying_config(self) -> Dict[str, Any]:
        """Configuration for retrying logic.

        Changing arguments at run time reference:
        https://github.com/jd/tenacity#changing-arguments-at-run-time

        Returns:
            kwargs dictionary for tenacity.BaseRetrying.

        """
        return dict(
            stop=tenacity.stop_after_attempt(self.attempts),
            retry=tenacity.retry_if_exception_type(
                exception_types=self.retry_if_exception_in + (ResponseEvaluationError,)
            ),
            wait=tenacity.wait_exponential(min=self.min_delay, max=self.max_delay),
            reraise=True,
            before_sleep=tenacity.before_sleep_log(
                logger=logger, log_level=logging.WARNING  # type: ignore[arg-type]
            ),
        )


class RateLimiter:
    """Limit the number of requests in a given time frame.

    Attributes:
        rate: number of requests allowed in the given time frame.
        time_frame: number of seconds for the time frame.
        limiter: in memory bucket to limit the number of requests.
        identity: identification for the rate-limiting bucket.
            Same identity can be used universally for all endpoints in a given host, if
            the API have a global limit. If the API have different limits for each
            endpoint, different identities can be used as well.

    """

    def __init__(self, rate: int = 10, time_frame: int = 1, identity: str = "default"):
        self.rate = rate
        self.time_frame = time_frame
        self.limiter = Limiter(
            InMemoryBucket(
                rates=[Rate(limit=rate, interval=time_frame * Duration.SECOND.value)]
            ),
            raise_when_fail=False,
            max_delay=Duration.MINUTE.value,
        )
        self.identity = identity


@tenacity.retry
async def _request(
    download_json_content: bool,
    download_text_content: bool,
    rate_limiter: RateLimiter,
    session: aiohttp.ClientSession,
    acceptable_codes: Optional[List[int]] = None,
    **request_kwargs: Any,
) -> Response:
    rate_limiter.limiter.try_acquire(name=rate_limiter.identity)
    async with session.request(**request_kwargs) as response:
        json_content = await response.json() if download_json_content else None
        normalized_json_content = (
            json_content
            if isinstance(json_content, dict)
            else {"content": json_content}
        )
        http_response = Response(
            url=response.url,
            status_code=response.status,
            headers={k: v for k, v in response.headers.items()},
            json_content=normalized_json_content,
            text_content=await response.text() if download_text_content else "",
        )
    evaluate_response(http_response=http_response, acceptable_codes=acceptable_codes)
    return http_response


def get_ssl_context(extra_certificate: Optional[str] = None) -> ssl.SSLContext:
    """Create a ssl context.

    It uses the collection of certificates provided by certifi package. Besides, the
    user can give an additional certificate to be appended to the final collection.

    Args:
        extra_certificate: extra string certificate to be used alongside default ones.

    Returns:
        new ssl context.

    """
    with open(certifi.where()) as f:
        certificate = f.read()
    if extra_certificate:
        certificate = certificate + "\n" + extra_certificate
    return ssl.create_default_context(cadata=certificate)


async def request(
    url: Union[str, URL],
    method: str,
    download_json_content: bool = True,
    download_text_content: bool = False,
    proxy_config: Optional[ProxyConfig] = None,
    rate_limiter: RateLimiter = RateLimiter(),
    retryer: Retryer = Retryer(),
    timeout: int = 300,
    use_random_user_agent: bool = True,
    user_agent_list: Optional[List[str]] = None,
    bearer_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    session: Optional[aiohttp.ClientSession] = None,
    acceptable_codes: Optional[List[int]] = None,
) -> Response:
    """Make a request.

    Args:
        url: url to send request.
        method: any available method in aiohttp.
            E.g. GET, POST, PUT, DELETE.
        download_json_content: if true will await for json content download.
        download_text_content: if true will await for text content download.
        proxy_config: proxy configuration.
        rate_limiter: rate limiting configuration.
        retryer: retry logic configuration.
        timeout: maximum number of seconds for timeout.
            By default, is 300 seconds (5 minutes).
        use_random_user_agent: if true will use a random user agent.
        user_agent_list: list of user agents to be randomly selected.
            By default, it uses a sample from `biar.user_agents` module.
        bearer_token: bearer token to be used in the request.
        headers: headers dictionary to use in request.
        params: parameters dictionary to use in request.
        session: aiohttp session to be used in request.
            If the user wants to use a custom session and handle its lifecycle, it can
            be passed here.
        acceptable_codes: list of acceptable status codes.
            If the response status code is not in this list, an exception will be
            raised. By default, it only accepts 200.

    Returns:
        Structured main attributes from response object.

    """
    logger.debug(f"Request started, {method} method to {url}...")
    proxy_kwargs = (
        {
            "proxy": proxy_config.host,
            "proxy_headers": proxy_config.headers,
            "ssl_context": get_ssl_context(extra_certificate=proxy_config.ssl_cadata),
        }
        if proxy_config
        else {}
    )
    final_headers = {
        **(headers or {}),
        **(
            {"User-Agent": get_user_agent(user_agent_list=user_agent_list)}
            if use_random_user_agent
            else {}
        ),
        **({"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}),
    }
    all_kwargs = {
        "url": url,
        "method": method,
        "headers": final_headers,
        "params": params or {},
        "timeout": timeout,
        **proxy_kwargs,
    }
    new_callable = _request.retry_with(**retryer.retrying_config)  # type: ignore

    async with aiohttp.ClientSession() as new_session:
        response: Response = await new_callable(
            download_json_content=download_json_content,
            download_text_content=download_text_content,
            rate_limiter=rate_limiter,
            session=session or new_session,
            acceptable_codes=acceptable_codes,
            **all_kwargs,
        )

    logger.debug("Request finished!")
    return response


async def request_structured(
    model: Type[BaseModel],
    url: Union[str, URL],
    method: str,
    download_text_content: bool = False,
    proxy_config: Optional[ProxyConfig] = None,
    rate_limiter: RateLimiter = RateLimiter(),
    retryer: Retryer = Retryer(),
    timeout: int = 300,
    use_random_user_agent: bool = True,
    user_agent_list: Optional[List[str]] = None,
    bearer_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    session: Optional[aiohttp.ClientSession] = None,
    acceptable_codes: Optional[List[int]] = None,
) -> StructuredResponse:
    """Make a request and structure the response.

    This method forces the download of json content and the use of a pydantic model to
    structure the response.

    Args:
        model: pydantic model to be used to structure json content.

    Returns:
        Structured json content as a pydantic model.

    """
    response = await request(
        url=url,
        method=method,
        download_json_content=True,
        download_text_content=download_text_content,
        proxy_config=proxy_config,
        rate_limiter=rate_limiter,
        retryer=retryer,
        timeout=timeout,
        use_random_user_agent=use_random_user_agent,
        user_agent_list=user_agent_list,
        bearer_token=bearer_token,
        headers=headers,
        params=params,
        session=session,
        acceptable_codes=acceptable_codes,
    )
    return StructuredResponse(
        url=response.url,
        status_code=response.status_code,
        headers=response.headers,
        json_content=response.json_content,
        text_content=response.text_content,
        structured_content=model(**response.json_content),
    )


async def is_host_reachable(host: str) -> bool:
    """Async check if a host is reachable.

    Args:
        host: url to check if is reachable.

    Returns:
        True if the host is reachable.

    """
    dns_solver = aiodns.DNSResolver()
    try:
        _ = await dns_solver.query(host, qtype="A")
        return True
    except aiodns.error.DNSError:
        return False
