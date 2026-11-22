"""Service errors. main.py maps them to {"detail": ..., "code": ...} responses.

Stable `code` values (the frontend translates by code; keep in sync with its messages):
  generic defaults: bad_request unauthorized not_found conflict too_large unprocessable bad_gateway
  auth:        unauthorized
  challenges:  slug_exists slug_reserved slug_immutable unknown_template invalid_challenge
               invalid_path file_too_large archive_too_large missing_file_name invalid_archive
               orphan_files file_not_found
  publish:     publish_running cleanup_running digest_reference publish_run_not_found
               order_mismatch order_category_split ctfd_order_failed ctfd_unreachable
  cleanup:     confirm_mismatch cleanup_plan_failed cleanup_failed
  sync:        invalid_remote_url invalid_field remote_credentials remote_not_configured
               invalid_sync_request unexpected_archive_path preview_not_found
               decision_required changed_since_preview sync_failed
"""


class DomainError(Exception):
    """Base for service errors; main.py maps them to HTTP responses."""

    status = 500
    code = "error"

    def __init__(self, detail="error", code: str | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class BadRequest(DomainError):
    status = 400
    code = "bad_request"


class Unauthorized(DomainError):
    status = 401
    code = "unauthorized"

    def __init__(self, detail="unauthorized", code: str | None = None):
        super().__init__(detail, code)


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Conflict(DomainError):
    status = 409
    code = "conflict"


class TooLarge(DomainError):
    status = 413
    code = "too_large"

    def __init__(self, detail="file too large", code: str | None = None):
        super().__init__(detail, code)


class Unprocessable(DomainError):
    status = 422
    code = "unprocessable"


class BadGateway(DomainError):
    status = 502
    code = "bad_gateway"
