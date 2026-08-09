"""Audit logging placeholder."""


class AuditLogger:
    """Simple placeholder logger for future audit events."""

    def log(self, action: str, resource_type: str, resource_id: str | None = None) -> dict[str, str | None]:
        return {
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": "placeholder",
        }

