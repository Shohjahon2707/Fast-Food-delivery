from django.utils.cache import add_never_cache_headers


class PrivatePagesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(
            ("/users/", "/couriers/", "/admin/", "/operations/", "/kitchen/")
        ):
            add_never_cache_headers(response)
        response["Referrer-Policy"] = "same-origin"
        return response
