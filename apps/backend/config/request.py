"""Give each Django request a request_id for core/actions.py.

api/v1/routes/support.py reads that context when it logs a money write.
packages/sdk-client sends X-Request-Id from apps/parkpe/js/hub.js and
apps/payswap/js/hub.js when it has a safe value. A value that is not a
short token is replaced so it cannot carry a cookie or a line break.
"""

from __future__ import annotations

from core.actions import bind_action, request_id_from, reset_action


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request_id_from(request.headers.get("X-Request-Id"))
        request.request_id = request_id
        reset_action()
        bind_action(request_id=request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_action()
        response["X-Request-Id"] = request_id
        return response
