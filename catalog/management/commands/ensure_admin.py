"""Create the admin login (or reset its password) from ADMIN_USERNAME / ADMIN_PASSWORD.

Runs on every Azure start; does nothing when those settings are not present.
Set them with:  bash deploy/azure_admin.sh
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the admin user from ADMIN_USERNAME / ADMIN_PASSWORD"

    def handle(self, *args, **opts):
        username, password = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
        if not (username and password):
            return
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        if created or not user.check_password(password) or not user.is_superuser:
            user.set_password(password)
            user.is_staff = user.is_superuser = user.is_active = True
            user.save()
            self.stdout.write(f"Admin user {username!r} {'created' if created else 'updated'}.")
