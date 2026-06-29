import datetime
from typing import Optional

class AuditLog:
    def __init__(
        self,
        id: Optional[int] = None,
        operator: Optional[str] = None,
        action: str = "",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
        details: Optional[str] = None,
        created_at: Optional[datetime.datetime] = None,
        request_params: Optional[str] = None,
        execution_time: Optional[float] = None,
        method: Optional[str] = None
    ):
        self.id = id
        self.operator = operator
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.status = status
        self.details = details
        self.created_at = created_at or datetime.datetime.now()
        self.request_params = request_params
        self.execution_time = execution_time
        self.method = method
