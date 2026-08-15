"""Errors that carry a message meant for the person using the app."""


class PipelineError(Exception):
    """A failure we understand well enough to explain to the user.

    Anything that escapes as a plain Exception is a bug and gets reported as a
    generic "internal" error instead, so never put internal detail in `message`.
    """

    def __init__(self, code: str, message: str, http_status: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
