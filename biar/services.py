import asyncio
import datetime
import ssl
from typing import Any, Callable, Dict, List, Optional, Type, Union

import aiodns
import aiohttp
import certifi
import tenacity
from loguru import logger
from pydantic import BaseModel
from yarl import URL

from biar import (
    ContentCallbackError,
    Payload,
    PollConfig,
    PollError,
    RateLimiter,
    RequestConfig,
    Response,
    ResponseEvaluationError,
    StructuredResponse,
)
from biar.user_agents import get_user_agent


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


async def _request_base(
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
        if response.status not in (acceptable_codes or [200]):
            formated_text_content = text_content.replace("{", "{{").replace("}", "}}")
            raise ResponseEvaluationError(
                f"Error: status={response.status}, "
                f"Text content (if loaded): {formated_text_content}"
            )

        json_content = (
            await response.json(content_type=None) if download_json_content else None
        )
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


@tenacity.retry
async def _request(
    download_json_content: bool,
    download_text_content: bool,
    rate_limiter: RateLimiter,
    session: aiohttp.ClientSession,
    acceptable_codes: Optional[List[int]] = None,
    **request_kwargs: Any,
) -> Response:
    return await _request_base(
        download_json_content=download_json_content,
        download_text_content=download_text_content,
        rate_limiter=rate_limiter,
        session=session,
        acceptable_codes=acceptable_codes,
        **request_kwargs,
    )


def _build_kwargs(
    url: Union[str, URL],
    config: RequestConfig,
    payload: Optional[Payload] = None,
) -> Dict[str, Any]:
    headers = {
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
        **(
            {"Content-Type": payload.content_type}
            if payload and payload.content_type
            else {}
        ),
    }
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
    return {
        "url": url,
        "method": config.method,
        "headers": headers,
        "params": config.params or None,
        "timeout": config.timeout,
        "data": payload.any_content if payload and payload.any_content else None,
        "json": (
            payload.structured_content.model_dump(mode="json")
            if payload and payload.structured_content
            else None
        ),
        **proxy_kwargs,
    }


async def request(
    url: Union[str, URL],
    config: RequestConfig = RequestConfig(),
    payload: Optional[Payload] = None,
) -> Response:
    """Make a request.

    Args:
        url: url to send request.
        config: request configuration.
        payload: payload definition for the request.

    Returns:
        Response object from the request.

    """
    logger.debug(f"Request started, {config.method} method to {url}...")
    new_callable = _request.retry_with(**config.retryer.retrying_config)  # type: ignore

    async with aiohttp.ClientSession() as new_session:
        response: Response = await new_callable(
            download_json_content=config.download_json_content,
            download_text_content=config.download_text_content,
            rate_limiter=config.rate_limiter,
            session=config.session or new_session,
            acceptable_codes=config.acceptable_codes,
            **_build_kwargs(url=url, config=config, payload=payload),
        )

    logger.debug("Request finished!")
    return response


def _normalize_payloads(
    urls: List[Union[str, URL]],
    payloads: Optional[List[Payload]] = None,
) -> Optional[List[Payload]]:
    payloads = payloads or []
    if payloads and len(urls) != len(payloads):
        raise ValueError(
            f"Number of urls ({len(urls)}) and payloads ({len(payloads or [])}) "
            f"must be the same."
        )
    return payloads


async def request_many(
    urls: List[Union[str, URL]],
    config: RequestConfig = RequestConfig(),
    payloads: Optional[List[Payload]] = None,
) -> List[Response]:
    """Make many requests.

    Args:
        urls: list of urls to send requests.
        config: request configuration.
        payloads: list of payload definitions for the requests.

    Returns:
        List of response objects from the requests.

    """
    payloads = _normalize_payloads(urls=urls, payloads=payloads)
    coroutines = (
        [
            request(
                url=url,
                config=config,
                payload=payload,
            )
            for url, payload in zip(urls, payloads)
        ]
        if payloads
        else [
            request(
                url=url,
                config=config,
            )
            for url in urls
        ]
    )

    results: List[Response] = await asyncio.gather(*coroutines)
    return results


@tenacity.retry
async def _request_structured(
    model: Type[BaseModel],
    retry_based_on_content_callback: Optional[Callable[[StructuredResponse], bool]],
    download_json_content: bool,
    download_text_content: bool,
    rate_limiter: RateLimiter,
    session: aiohttp.ClientSession,
    acceptable_codes: Optional[List[int]] = None,
    **request_kwargs: Any,
) -> StructuredResponse:
    response = await _request_base(
        download_json_content=download_json_content,
        download_text_content=download_text_content,
        rate_limiter=rate_limiter,
        session=session,
        acceptable_codes=acceptable_codes,
        **request_kwargs,
    )
    structured_response = StructuredResponse(
        url=response.url,
        status_code=response.status_code,
        headers=response.headers,
        json_content=response.json_content,
        text_content=response.text_content,
        structured_content=model(**response.json_content),
    )
    if retry_based_on_content_callback and retry_based_on_content_callback(
        structured_response.structured_content
    ):
        raise ContentCallbackError("Structured content retry callback returned True")
    return structured_response


async def request_structured(
    model: Type[BaseModel],
    url: Union[str, URL],
    config: RequestConfig = RequestConfig(),
    payload: Optional[Payload] = None,
) -> StructuredResponse:
    """Make a request and structure the response.

    This function forces the download of the json content to be deserialized as a
    pydantic model.

    Args:
        model: pydantic model to be used to structure the response content.
        url: url to send request.
        config: request configuration.
        payload: payload definition for the request.

    Returns:
        Structured response content deserialized as a pydantic model.

    """
    new_config = config.model_copy(update=dict(download_json_content=True))
    logger.debug(f"Request started, {new_config.method} method to {url}...")

    rc = new_config.retryer.retrying_config
    new_callable = _request_structured.retry_with(**rc)  # type: ignore

    async with aiohttp.ClientSession() as new_session:
        structured_response: StructuredResponse = await new_callable(
            model=model,
            retry_based_on_content_callback=(
                new_config.retryer.retry_based_on_content_callback
            ),
            download_json_content=new_config.download_json_content,
            download_text_content=new_config.download_text_content,
            rate_limiter=new_config.rate_limiter,
            session=new_config.session or new_session,
            acceptable_codes=new_config.acceptable_codes,
            **_build_kwargs(url=url, config=new_config, payload=payload),
        )

    logger.debug("Request finished!")
    return structured_response


async def request_structured_many(
    model: Type[BaseModel],
    urls: List[Union[str, URL]],
    config: RequestConfig = RequestConfig(),
    payloads: Optional[List[Payload]] = None,
) -> List[StructuredResponse]:
    """Make many requests and structure the responses.

    Args:
        model: pydantic model to be used to structure the response.
        urls: list of urls to send requests.
        config: request configuration.
        payloads: list of payloads as structured pydantic models.

    Returns:
        List of structured response content deserialized as a pydantic model.

    """
    payloads = _normalize_payloads(urls=urls, payloads=payloads)
    coroutines = (
        [
            request_structured(
                model=model,
                url=url,
                config=config,
                payload=payload,
            )
            for url, payload in zip(urls, payloads)
        ]
        if payloads
        else [
            request_structured(
                model=model,
                url=url,
                config=config,
            )
            for url in urls
        ]
    )

    results: List[StructuredResponse] = await asyncio.gather(*coroutines)
    return results


async def poll(
    model: Type[BaseModel],
    poll_config: PollConfig,
    url: Union[str, URL],
    config: RequestConfig = RequestConfig(),
) -> StructuredResponse:
    """Poll a url until a condition is met.

    Args:
        url: url to be polled.
        config: request configuration.
        model: pydantic model to be used to structure the response.
        poll_config: poll configuration.

    Returns:
        Structured response.

    """
    logger.debug(f"Polling {url}...")
    start_time = datetime.datetime.utcnow()
    elapsed_time = datetime.timedelta(seconds=0)
    while elapsed_time.total_seconds() < poll_config.timeout:
        response = await request_structured(model=model, url=url, config=config)
        if poll_config.success_condition(response.structured_content):
            logger.debug("Condition met, polling finished!")
            return response
        await asyncio.sleep(poll_config.interval)
        elapsed_time = datetime.datetime.utcnow() - start_time
        logger.debug(f"Condition not met yet. Elapsed time: {elapsed_time} seconds...")
    raise PollError("Timeout reached")
