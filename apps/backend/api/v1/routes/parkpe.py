"""POST /api/v1/parkpe/sessions/initiate

Caller: apps/parkpe/features/qr-connect through packages/sdk-client
(X-App-Context: parkpe, role customer from packages/contracts).
parkpe_only rejects a payswap context with 403 before the domain runs.
Auth cookie is checked by api/v1/deps.py against GET /api/auth/me.
Body: schemas.SessionInitiateSerializer.
Service: domain/parkpe/sessions.py. Retry: core/idempotency.py.
"""

from api.v1.deps import parkpe_only
from api.v1.routes.support import post_mutation
from domain.parkpe.sessions import initiate_session
from rest_framework.views import APIView
from schemas.serializers import SessionInitiateSerializer


@parkpe_only
class SessionInitiateView(APIView):
    def post(self, request):
        return post_mutation(
            request,
            SessionInitiateSerializer,
            lambda data, user_id: initiate_session(
                user_id=user_id,
                site_code=data["site_code"],
                bay=data["bay"],
                vehicle=data["vehicle"],
            ),
        )
