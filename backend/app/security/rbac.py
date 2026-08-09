"""Role-based access control primitives."""

from enum import Enum


class Role(str, Enum):
    USER = "USER"
    MENTOR = "MENTOR"
    CASE_WORKER = "CASE_WORKER"
    ADMIN = "ADMIN"

