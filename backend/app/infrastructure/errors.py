from __future__ import annotations


class ErrorCode:
    NOT_IMPLEMENTED = "FURSAH_NOT_IMPLEMENTED"
    REQUEST_VALIDATION = "FURSAH_REQUEST_VALIDATION_ERROR"
    OPPORTUNITY_NOT_FOUND = "FURSAH_OPPORTUNITY_NOT_FOUND"
    DATA = "FURSAH_DATA_ERROR"
    TOOL = "FURSAH_TOOL_ERROR"
    MODEL = "FURSAH_MODEL_ERROR"
    INVALID_MODEL_OUTPUT = "FURSAH_INVALID_MODEL_OUTPUT"
    VALIDATION = "FURSAH_VALIDATION_ERROR"
    INTERNAL = "FURSAH_INTERNAL_ERROR"


class FursahError(Exception):
    public_code = ErrorCode.INTERNAL
    http_status = 503
    public_message = "The request could not be completed right now."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.public_message)


class DataAccessError(FursahError):
    public_code = ErrorCode.DATA
    public_message = "The opportunity data could not be accessed right now."


class ToolExecutionError(FursahError):
    public_code = ErrorCode.TOOL
    public_message = "A required application tool could not complete."


class ModelExecutionError(FursahError):
    public_code = ErrorCode.MODEL
    public_message = "The configured model could not complete the request."


class InvalidModelOutputError(FursahError):
    public_code = ErrorCode.INVALID_MODEL_OUTPUT
    public_message = "The model returned an invalid structured result."


class EvidenceValidationError(FursahError):
    public_code = ErrorCode.VALIDATION
    public_message = "The proposed result could not be validated against the available evidence."


class WorkflowBudgetExceededError(FursahError):
    public_code = ErrorCode.INTERNAL
    public_message = "The workflow stopped before a safe result could be produced."


class RecordNotFound(FursahError):
    public_code = ErrorCode.OPPORTUNITY_NOT_FOUND
    http_status = 404
    public_message = "The requested opportunity was not found."
