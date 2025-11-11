import re
from typing import Dict
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.security import validate_password_strength, generate_secure_password


router = APIRouter()


class PasswordRequirementsResponse(BaseModel):
    """Response model for password requirements."""

    min_length: int = Field(..., description="Minimum password length")
    max_length: int = Field(..., description="Maximum password length")
    requires_lowercase: bool = Field(
        ..., description="Requires at least one lowercase letter"
    )
    requires_uppercase: bool = Field(
        ..., description="Requires at least one uppercase letter"
    )
    requires_digit: bool = Field(..., description="Requires at least one digit")
    requires_special: bool = Field(
        ..., description="Requires at least one special character"
    )
    allowed_special_chars: str = Field(
        ..., description="List of allowed special characters"
    )
    forbidden_patterns: list[str] = Field(
        ..., description="List of forbidden common patterns"
    )
    description: str = Field(
        ..., description="Human-readable description of requirements"
    )


class PasswordValidationRequest(BaseModel):
    """Request model for password validation."""

    password: str = Field(..., description="Password to validate")


class PasswordValidationResponse(BaseModel):
    """Response model for password validation."""

    is_valid: bool = Field(..., description="Whether password meets requirements")
    error_message: str = Field("", description="Error message if validation fails")
    strength_score: int = Field(..., description="Password strength score (0-100)")
    requirements_met: Dict[str, bool] = Field(
        ..., description="Which requirements are met"
    )


class GeneratedPasswordResponse(BaseModel):
    """Response model for generated password."""

    password: str = Field(..., description="Generated secure password")
    strength_score: int = Field(..., description="Strength score of generated password")
    meets_requirements: bool = Field(
        ..., description="Whether password meets all requirements"
    )


@router.get(
    "/password/requirements",
    response_model=PasswordRequirementsResponse,
    summary="Get password requirements",
    description="Get the current password requirements for user accounts.",
)
async def get_password_requirements() -> PasswordRequirementsResponse:
    """
    Get password requirements for the application.

    Returns current password policy including:
    - Length requirements
    - Character type requirements
    - Forbidden patterns
    - Special character list
    """
    return PasswordRequirementsResponse(
        min_length=8,
        max_length=128,
        requires_lowercase=True,
        requires_uppercase=True,
        requires_digit=True,
        requires_special=True,
        allowed_special_chars='!@#$%^&*(),.?":{}|<>',
        forbidden_patterns=["password", "12345678", "qwerty123", "password123"],
        description=(
            "Password must be 8-128 characters long and contain at least one "
            "lowercase letter, one uppercase letter, one number, and one special character."
        ),
    )


@router.post(
    "/password/validate",
    response_model=PasswordValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate password strength",
    description="Validate a password against the current security requirements.",
)
async def validate_password(
    request: PasswordValidationRequest,
) -> PasswordValidationResponse:
    """
    Validate a password against security requirements.

    Checks if the provided password meets all security requirements
    and returns detailed feedback on which requirements are met.

    Args:
        request: Password validation request containing the password to check

    Returns:
        Validation result with detailed requirement analysis
    """
    password = request.password
    is_valid, error_message = validate_password_strength(password)

    # Check individual requirements for detailed feedback
    requirements_met = {
        "min_length": len(password) >= 8,
        "max_length": len(password) <= 128,
        "has_lowercase": bool(re.search(r"[a-z]", password)),
        "has_uppercase": bool(re.search(r"[A-Z]", password)),
        "has_digit": bool(re.search(r"\d", password)),
        "has_special": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
        "not_common": password.lower()
        not in ["password", "12345678", "qwerty123", "password123"],
    }

    # Calculate strength score (0-100)
    score = 0
    if requirements_met["min_length"]:
        score += 20
    if requirements_met["has_lowercase"]:
        score += 15
    if requirements_met["has_uppercase"]:
        score += 15
    if requirements_met["has_digit"]:
        score += 15
    if requirements_met["has_special"]:
        score += 15
    if requirements_met["not_common"]:
        score += 10
    if len(password) >= 12:  # Bonus for longer passwords
        score += 10

    return PasswordValidationResponse(
        is_valid=is_valid,
        error_message=error_message,
        strength_score=min(score, 100),
        requirements_met=requirements_met,
    )


@router.post(
    "/password/generate",
    response_model=GeneratedPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate secure password",
    description="Generate a cryptographically secure password that meets all requirements.",
)
async def generate_password(length: int = 12) -> GeneratedPasswordResponse:
    """
    Generate a secure password that meets all requirements.

    Args:
        length: Desired password length (minimum 8, default 12)

    Returns:
        Generated password with strength analysis
    """
    if length < 8:
        length = 8
    elif length > 128:
        length = 128

    password = generate_secure_password(length)

    # Validate the generated password (should always pass)
    is_valid, _ = validate_password_strength(password)

    return GeneratedPasswordResponse(
        password=password,
        strength_score=100,  # Generated passwords always meet all requirements
        meets_requirements=is_valid,
    )
