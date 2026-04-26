#!/bin/bash

apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

gunicorn --bind=0.0.0.0 --timeout 600 wsgi:app