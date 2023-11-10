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

🤓 while working on different tech companies I found myself using the same stack of Python libraries over and over. In each new project I'd add same requirements and create Python clients sharing a lot of code I've already developed before.

That's why in `biar` I've packed the functionality of some top-notch Python projects:

- **[aiohttp](https://github.com/aio-libs/aiohttp)**: for lightning-fast HTTP requests in async Python.
- **[tenacity](https://github.com/jd/tenacity)**: ensures your code doesn't give up easily, allowing retries for better resilience.
- **[pyrate-limiter](https://github.com/vutran1710/PyrateLimiter)**: manage your application's rate limits effectively.
- **[yarl](https://github.com/aio-libs/yarl)**: simplifies handling and manipulating URLs in async applications.
- **[pydantic](https://github.com/samuelcolvin/pydantic)**: helps validate and manage data structures with ease.
- **[loguru](https://github.com/Delgan/loguru)**: your ultimate logging companion, making logs a breeze.

With `biar`, you get all these awesome tools rolled into one package, all within a unified API. It's the shortcut to handling async requests, retries, rate limits, data validation, URL manipulation, Proxy and logging—all in a straightforward tool.

Give `biar` a spin and see how it streamlines your async request development!

## Examples
TODO

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