"""Security utilities for webhook signature verification."""
import hmac
import hashlib
from fastapi import HTTPException


def verify_webhook_signature(
    body_bytes: bytes,
    signature: str,
    secret: str,
    signature_header: str = "X-KT-Webhook-Signature"
) -> bool:
    """
    Verify the HMAC-SHA1 signature of the webhook request body.
    
    Args:
        body_bytes: The raw request body bytes
        signature: The signature from the X-KT-Webhook-Signature header
        secret: Webhook secret for HMAC verification
        signature_header: Name of the header containing the signature (for error messages)
        
    Returns:
        True if signature is valid, False otherwise
        
    Raises:
        HTTPException: 403 if signature is missing or invalid
    """
    if not signature:
        raise HTTPException(
            status_code=403,
            detail=f"Missing {signature_header} header"
        )
    
    # Compute expected signature using HMAC-SHA1
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        body_bytes,
        hashlib.sha1
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(
            status_code=403,
            detail="Invalid webhook signature"
        )
    
    return True
