class ResponseEvaluationError(Exception):
    """Base Exception for non-OK responses."""


class PollError(Exception):
    """Base Exception for poll errors."""


class ContentCallbackError(Exception):
    """Base Exception for content callback errors."""
