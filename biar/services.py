import asyncio
import ssl
from typing import Any, List, Optional, Type, Union

import aiodns
import aiohttp
import certifi
import tenacity
from loguru import logger
from pydantic import BaseModel
from yarl import URL

from biar import (
    RateLimiter,
    RequestConfig,
    Response,
    ResponseEvaluationError,
    StructuredResponse,
)
from biar.user_agents import get_user_agent


def evaluate_response(
    status_code: int,
    acceptable_codes: Optional[List[int]] = None,
    text_content: str = "",
) -> None:
    """Evaluate a response and raise an exception if it's not OK.

    Args:
        status_code: status code from the response.
        acceptable_codes: list of acceptable status codes.

    Raises:
        ResponseEvaluationError if the response is not OK.

    """
    if status_code not in (acceptable_codes or [200]):
        raise ResponseEvaluationError(
            f"Error: status={status_code}, " f"Text content (if loaded): {text_content}"
        )


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
        text_content = await response.text() if download_text_content else ""
        evaluate_response(
            status_code=response.status,
            acceptable_codes=acceptable_codes,
            text_content=text_content,
        )
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
            text_content=text_content,
        )
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
    config: RequestConfig = RequestConfig(),
) -> Response:
    """Make a request.

    Args:
        url: url to send request.
        config: request configuration.

    Returns:
        Response object from the request.

    """
    logger.debug(f"Request started, {config.method} method to {url}...")
    proxy_kwargs = (
        {
            "proxy": config.proxy_config.host,
            "proxy_headers": config.proxy_config.headers,
            "ssl_context": get_ssl_context(
                extra_certificate=config.proxy_config.ssl_cadata
            ),
        }
        if config.proxy_config
        else {}
    )
    final_headers = {
        **(config.headers or {}),
        **(
            {"User-Agent": get_user_agent(user_agent_list=config.user_agent_list)}
            if config.use_random_user_agent
            else {}
        ),
        **(
            {"Authorization": f"Bearer {config.bearer_token}"}
            if config.bearer_token
            else {}
        ),
    }
    all_kwargs = {
        "url": url,
        "method": config.method,
        "headers": final_headers,
        "params": config.params or {},
        "timeout": config.timeout,
        **proxy_kwargs,
    }
    new_callable = _request.retry_with(**config.retryer.retrying_config)  # type: ignore

    async with aiohttp.ClientSession() as new_session:
        response: Response = await new_callable(
            download_json_content=config.download_json_content,
            download_text_content=config.download_text_content,
            rate_limiter=config.rate_limiter,
            session=config.session or new_session,
            acceptable_codes=config.acceptable_codes,
            **all_kwargs,
        )

    logger.debug("Request finished!")
    return response


async def request_structured(
    model: Type[BaseModel],
    url: Union[str, URL],
    config: RequestConfig = RequestConfig(),
) -> StructuredResponse:
    """Make a request and structure the response.

    This function forces the download of the json content to be deserialized as a
    pydantic model.

    Args:
        model: pydantic model to be used to structure the response.
        url: url to send request.
        config: request configuration.

    Returns:
        Structured response from the request, with with data deserialized as a pydantic
        model.

    """
    new_config = config.model_copy(update=dict(download_json_content=True))
    response = await request(
        url=url,
        config=new_config,
    )
    return StructuredResponse(
        url=response.url,
        status_code=response.status_code,
        headers=response.headers,
        json_content=response.json_content,
        text_content=response.text_content,
        structured_content=model(**response.json_content),
    )


async def request_structured_many(
    model: Type[BaseModel],
    urls: List[Union[str, URL]],
    config: RequestConfig = RequestConfig(),
) -> List[StructuredResponse]:
    """Make many requests and structure the responses.

    Args:
        model: pydantic model to be used to structure the response.
        urls: list of urls to send requests.
        config: request configuration.

    Other args are the same as `biar.request_structured`.

    Returns:
        List of structured data as pydantic models.

    """
    results: List[StructuredResponse] = await asyncio.gather(
        *[request_structured(model=model, url=url, config=config) for url in urls]
    )
    return results


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
