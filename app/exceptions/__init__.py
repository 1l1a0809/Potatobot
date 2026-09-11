"""Custom exceptions for Potatobot."""


class BotException(Exception):
    """Base exception for bot errors."""
    pass


class CooldownError(BotException):
    """Raised when user is on cooldown."""

    def __init__(self, remaining: int):
        self.remaining = remaining
        super().__init__(f"Cooldown: {remaining}s remaining")


class ValidationError(BotException):
    """Raised when input validation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DatabaseError(BotException):
    """Raised when database operation fails."""
    pass


class UserNotFoundError(BotException):
    """Raised when user doesn't exist."""
    pass