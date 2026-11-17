from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Project user. Login stays on username; these fields are extra profile data."""

    phone_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    bio = models.TextField(blank=True)
