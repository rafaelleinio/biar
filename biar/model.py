import asyncio
from functools import cached_property
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

import aiohttp
import tenacity
from aiohttp import ClientResponseError
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, JsonValue, computed_field
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate
from yarl import URL

from biar import ResponseEvaluationError


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
                logger=logger, log_level="DEBUG"  # type: ignore[arg-type]
            ),
        )


class RateLimiter(BaseModel):
    """Limit the number of requests in a given time frame.

    Attributes:
        rate: number of requests allowed in the given time frame.
        time_frame: number of seconds for the time frame.
        identity: identification for the rate-limiting bucket.
            Same identity can be used universally for all endpoints in a given host, if
            the API have a global limit. If the API have different limits for each
            endpoint, different identities can be used as well.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rate: int = 10
    time_frame: int = 1
    identity: str = "default"

    @computed_field  # type: ignore[misc]
    @cached_property
    def limiter(self) -> Limiter:
        """In memory bucket to limit the number of requests."""
        return Limiter(
            InMemoryBucket(
                rates=[
                    Rate(
                        limit=self.rate,
                        interval=self.time_frame * Duration.SECOND.value,
                    )
                ]
            ),
            raise_when_fail=False,
            max_delay=Duration.MINUTE.value,
        )


class RequestConfig(BaseModel):
    """Base configuration for a request.

    Attributes:
        method: http method to be used.
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

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    download_json_content: bool = True
    download_text_content: bool = True
    proxy_config: Optional[ProxyConfig] = None
    rate_limiter: RateLimiter = RateLimiter()
    retryer: Retryer = Retryer()
    timeout: int = 300
    use_random_user_agent: bool = True
    user_agent_list: Optional[List[str]] = None
    bearer_token: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    session: Optional[aiohttp.ClientSession] = None
    acceptable_codes: Optional[List[int]] = None
