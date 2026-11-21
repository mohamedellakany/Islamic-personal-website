#!/usr/bin/env python
"""Django command line: .venv/bin/python manage.py <command>  (runserver, migrate, createsuperuser, …)"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academy.settings")
    # On your Mac (no secret key, not on Azure): local development mode, like dev.sh.
    # Azure always sets WEBSITE_HOSTNAME and has a real DJANGO_SECRET_KEY, so this never applies there.
    if not os.environ.get("DJANGO_SECRET_KEY") and not os.environ.get("WEBSITE_HOSTNAME"):
        os.environ.setdefault("DJANGO_DEBUG", "1")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
