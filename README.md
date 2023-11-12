# biar
_batteries-included async requests tool for python_

![Python Version](https://img.shields.io/badge/python-3.11-brightgreen.svg)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![flake8](https://img.shields.io/badge/code%20quality-flake8-blue)](https://github.com/PyCQA/flake8)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![pytest coverage: 100%](https://img.shields.io/badge/pytest%20coverage-100%25-green)](https://github.com/pytest-dev/pytest)

### Build status
| Test                                                                                                                                                  | Release                                                                                                                                                        |
|-------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [![Test](https://github.com/rafaelleinio/biar/actions/workflows/test.yml/badge.svg)](https://github.com/rafaelleinio/biar/actions/workflows/test.yml) | [![Release](https://github.com/rafaelleinio/biar/actions/workflows/release.yml/badge.svg)](https://github.com/rafaelleinio/biar/actions/workflows/release.yml) |

### Package
| Source   | Downloads                                                | Page                                   | Installation Command |
|----------|----------------------------------------------------------|----------------------------------------|----------------------|
| **PyPi** | ![PyPI - Downloads](https://img.shields.io/pypi/dm/biar) | [Link](https://pypi.org/project/biar/) | `pip install biar`   |


## Introduction
Welcome to `biar`! 👋

Think of it as your all-in-one solution for smoother async requests development.

🤓 while working on different tech companies I found myself using the same stack of 
Python libraries over and over. In each new project I'd add same requirements and create
Python clients sharing a lot of code I've already developed before.

That's why in `biar` I've packed the functionality of some top-notch Python projects:

- **[aiohttp](https://github.com/aio-libs/aiohttp)**: for lightning-fast HTTP requests in async Python.
- **[tenacity](https://github.com/jd/tenacity)**: ensures your code doesn't give up easily, allowing retries for 
better resilience.
- **[pyrate-limiter](https://github.com/vutran1710/PyrateLimiter)**: manage your application's rate limits effectively.
- **[yarl](https://github.com/aio-libs/yarl)**: simplifies handling and manipulating URLs.
- **[pydantic](https://github.com/samuelcolvin/pydantic)**: helps validate and manage data structures with ease.
- **[loguru](https://github.com/Delgan/loguru)**: your ultimate logging companion, making logs a breeze.

With `biar`, you get all these awesome tools rolled into one package, all within a 
unified API. It's the shortcut to handling async requests, retries, rate limits, data 
validation, URL manipulation, Proxy and logging—all in a straightforward tool.

Give `biar` a spin and see how it streamlines your async request development!

## Examples

Imagine a scenario where you need to make several requests to an API. But not only that,
you also need to handle rate limits, retries, and logging. Check the test scenario
below:

```python
import asyncio

from aioresponses import aioresponses
from pydantic import BaseModel
from yarl import URL

BASE_URL = URL("https://api.com/v1/entity/")


class MyModel(BaseModel):
    id_entity: str
    feature: int


async def main():
    with aioresponses() as mock_server:
        # Set up mock responses using aioresponses
        request_urls = []
        for i in range(10):
            url = BASE_URL / str(i)

            # 500 error on first request for each url
            mock_server.get(url=url, status=500)

            # 200 success
            response_json = {"id_entity": str(i), "feature": 123}
            mock_server.get(url=url, payload=response_json, status=200)
            request_urls.append(url)

        # act
        results = await make_requests(request_urls=request_urls)
        print(f"Structured content:\n{results}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

```

Without `biar`, you probably would implement the `make_requests` function like this:


```python
from typing import List

import aiohttp
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate
from tenacity import retry, stop_after_attempt, wait_exponential
from yarl import URL


async def fetch_data(
    session: aiohttp.ClientSession, url: URL, limiter: Limiter
) -> MyModel:
    limiter.try_acquire(name="my_api")
    async with session.get(url) as response:
        if response.status == 500:
            raise Exception("Server Error")
        response_json = await response.json()
        return MyModel(**response_json)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=0, max=10))
async def fetch_with_retry(
    session: aiohttp.ClientSession, url: URL, limiter: Limiter
) -> MyModel:
    return await fetch_data(session=session, url=url, limiter=limiter)


async def make_requests(request_urls: List[URL]) -> List[MyModel]:
    limiter = Limiter(
        InMemoryBucket(rates=[Rate(5, Duration.SECOND)]),
        raise_when_fail=False,
        max_delay=Duration.MINUTE.value,
    )
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in request_urls:
            task = fetch_with_retry(session=session, url=url, limiter=limiter)
            tasks.append(task)
        results = await asyncio.gather(*tasks)
        return results
```

Using the right tools is not terrible right? But depend on importing several things and
knowing how to use these libraries. However, this is obviously not the only way to do 
it. Without a standard way to handle these requests, you'll probably end up with a lot 
of boilerplate code, and different developers will implement it in different ways.

With `biar`, you can implement the same `make_requests` function like this:

```python
from typing import List

from yarl import URL
import biar

async def make_requests(request_urls: List[URL]) -> List[MyModel]:
    responses = await biar.request_structured_many(
        model=MyModel,
        urls=request_urls,
        config=biar.model.RequestConfig(
            method="GET",
            retryer=biar.model.Retryer(attempts=5),
            rate_limiter=biar.model.RateLimiter(rate=5, identity="my_api"),
            download_text_content=True,
        )
    )
    return [response.structured_content for response in responses]
```

Easy, right? ✨🍰

Here's the output:

```
2023-11-12 02:10:45.084 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/0...
2023-11-12 02:10:45.088 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:45.088 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/1...
2023-11-12 02:10:45.089 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:45.089 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/2...
2023-11-12 02:10:45.089 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:45.089 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/3...
2023-11-12 02:10:45.090 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:45.090 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/4...
2023-11-12 02:10:45.090 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:45.090 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/5...
2023-11-12 02:10:46.142 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:46.142 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/6...
2023-11-12 02:10:46.144 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:46.144 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/7...
2023-11-12 02:10:46.145 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:46.145 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/8...
2023-11-12 02:10:46.146 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:46.147 | DEBUG    | biar.services:request:111 - Request started, GET method to https://api.com/v1/entity/9...
2023-11-12 02:10:46.147 | DEBUG    | tenacity.before_sleep:log_it:65 - Retrying biar.services._request in 1.0 seconds as it raised ResponseEvaluationError: Error: status=500, Text content (if loaded): Server Error.
2023-11-12 02:10:47.189 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:47.189 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:47.189 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:47.189 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:47.189 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:48.242 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:48.242 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:48.242 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:48.243 | DEBUG    | biar.services:request:156 - Request finished!
2023-11-12 02:10:48.243 | DEBUG    | biar.services:request:156 - Request finished!
Structured content:
[MyModel(id_entity='0', feature=123), MyModel(id_entity='1', feature=123), MyModel(id_entity='2', feature=123), MyModel(id_entity='3', feature=123), MyModel(id_entity='4', feature=123), MyModel(id_entity='5', feature=123), MyModel(id_entity='6', feature=123), MyModel(id_entity='7', feature=123), MyModel(id_entity='8', feature=123), MyModel(id_entity='9', feature=123)]

```

Check more examples in the unit tests [here](https://github.com/rafaelleinio/biar/blob/main/tests/unit/biar/test_services.py).

## Development
After creating your virtual environment:

#### Install dependencies

```bash
make requirements
```

#### Code Style and Quality
Apply code style (black and isort)
```bash
make apply-style
```

Run all checks (flake8 and mypy)
```
make checks
```

#### Testing and Coverage
```bash
make tests
```
