FROM python:3.12 as dependencies

## requirements
RUN pip install --upgrade pip
COPY requirements.dev.txt .
RUN pip install -r requirements.dev.txt
COPY requirements.txt .
RUN pip install -r requirements.txt

WORKDIR /biar
COPY . /biar

## setup package
FROM dependencies as biar

RUN pip install /biar/.
RUN python -c "import biar"
