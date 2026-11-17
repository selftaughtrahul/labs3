from django.conf import settings
from django.http import JsonResponse


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "environment": settings.ENVIRONMENT_LABEL,
        }
    )
