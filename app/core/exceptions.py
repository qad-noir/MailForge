class LeadSenderError(Exception):
    """Base domain error."""


class NotFoundError(LeadSenderError):
    pass


class ConflictError(LeadSenderError):
    pass


class ValidationError(LeadSenderError):
    pass


class InvalidStateError(ConflictError):
    pass

