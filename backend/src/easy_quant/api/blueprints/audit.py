from flask import Blueprint

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_admin
from easy_quant.api.responses import success

blueprint = Blueprint("audit", __name__, url_prefix="/api/v1/admin/audit-events")


@blueprint.get("")
@require_admin
def list_audit_events():
    return success(get_container().state.audit_events)
