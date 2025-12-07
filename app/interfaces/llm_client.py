"""
This module defines the abstract interface (Protocol) for LLM client operations.

The use of a Protocol enforces a strict contract for any concrete LLM client
implementation. This enables dependency injection, improves testability, and
maintains loose coupling between the business logic and external AI providers.

Any service interacting with an LLM must implement this protocol to ensure
consistent behavior across different model backends.
"""

from typing import Protocol, Dict, Any
from app.schemas.viva import VivaStartRequest


class LLMClient(Protocol):
    """
    Protocol defining the contract for LLM client operations.

    All LLM provider implementations (e.g., OpenAI, Anthropic, Local LLMs)
    must adhere to this protocol. It ensures that the application layer
    interacts with a predictable and uniform interface regardless of the
    underlying LLM engine.

    This abstraction also facilitates:
        - Mocking during unit tests
        - Hot-swapping LLM providers with zero business logic changes
        - Cleaner architecture via inversion of control
    """

    async def create_ephemeral_token(self, request: VivaStartRequest) -> dict:
        """
        Generate a secure, short-lived token enabling ephemeral access to the LLM.

        This token is typically used for client-side authenticated LLM sessions,
        ensuring that sensitive credentials remain server-side. The token may
        also include session metadata required for model initialization.

        Args:
            request (VivaStartRequest):
                The start-session request containing user/session parameters
                required to provision the token.

        Returns:
            dict:
                A structured payload containing:
                    - The generated ephemeral token
                    - Session-scoped configuration or additional metadata

        Notes:
            - Implementations should ensure token cryptographic integrity.
            - Tokens must enforce strict TTL (time-to-live) for security.
            - Exceptions should be raised for invalid or incomplete request payloads.
        """
        ...

    def generate_system_instruction(self, request: VivaStartRequest) -> str:
        """
        Construct and return the system instruction (system prompt) for the LLM.

        System instructions define the behavioral baseline for the AI model—
        including tone, persona, constraints, and task-specific guidelines.
        This method encapsulates the logic required to dynamically build such
        instructions based on incoming request parameters.

        Args:
            request (VivaStartRequest):
                The viva session request holding contextual information
                required to shape the system instruction.

        Returns:
            str:
                A fully composed system instruction string that the LLM will
                use as its foundation for the conversation or task.

        Best Practices for Implementations:
            - Keep system prompts deterministic where possible.
            - Avoid leaking sensitive user data into the instruction layer.
            - Ensure instructions adhere to compliance and safety guidelines.

        """
        ...
