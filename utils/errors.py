"""Shared exception types for the ZENFILE conversion layer."""


class ConversionError(Exception):
    """Raised when a requested conversion cannot be completed safely."""


class UnsupportedFormatError(ConversionError):
    """Raised when a file format or conversion pair is unsupported."""


class DependencyUnavailableError(ConversionError):
    """Raised when a required optional library or external tool is absent."""


class SecurityValidationError(ConversionError, ValueError):
    """Raised when an input violates a security or resource limit."""
