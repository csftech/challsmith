class DomainError(Exception):
    """Base for service errors; main.py maps them to HTTP responses."""

    status = 500

    def __init__(self, detail="error"):
        super().__init__(detail)
        self.detail = detail


class BadRequest(DomainError):
    status = 400


class Unauthorized(DomainError):
    status = 401

    def __init__(self, detail="unauthorized"):
        super().__init__(detail)


class NotFound(DomainError):
    status = 404


class Conflict(DomainError):
    status = 409


class TooLarge(DomainError):
    status = 413

    def __init__(self, detail="file too large"):
        super().__init__(detail)


class Unprocessable(DomainError):
    status = 422
