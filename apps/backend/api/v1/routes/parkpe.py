"""ParkPe /api/v1 routes.

Callers: apps/parkpe/js/hub.js via packages/sdk-client
(X-App-Context: parkpe, role customer from packages/contracts).
parkpe_only rejects a payswap context with 403 before domain runs.
"""

from api.v1.deps import parkpe_only
from api.v1.routes.support import post_mutation
from core.actions import bind_action
from domain.parkpe.sessions import initiate_session
from domain.parkpe.vehicles import add_vehicle, list_customer_sessions, list_vehicles, remove_vehicle
from rest_framework.response import Response
from rest_framework.views import APIView
from schemas.serializers import SessionInitiateSerializer, VehicleAddSerializer


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
            action="parkpe.session.initiate",
        )


@parkpe_only
class SessionsListView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        return Response({"sessions": list_customer_sessions(request.user.user_id)}, status=200)


@parkpe_only
class VehiclesView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        return Response({"vehicles": list_vehicles(request.user.user_id)}, status=200)

    def post(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        serializer = VehicleAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        out = add_vehicle(
            request.user.user_id,
            registration=d["registration"],
            make_model=d.get("make_model", ""),
            color=d.get("color", ""),
            fastag_linked=d.get("fastag_linked", False),
        )
        return Response(out, status=201)

    def delete(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        vehicle_id = str(request.query_params.get("vehicle_id") or "").strip()
        return Response(remove_vehicle(request.user.user_id, vehicle_id), status=200)
