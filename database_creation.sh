#!/bin/bash

python3 manage.py makemigrations
python3 manage.py migrate --run-syncdb
python3 manage.py createsuperuser
python3 functions.py
python3 manage.py loaddata items_final.json