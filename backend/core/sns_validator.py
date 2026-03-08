"""
AWS SNS message signature verification and subscription confirmation.

SNS signs every message with an X.509 certificate. Verification:
  1. Ensure SigningCertURL points to an amazonaws.com host.
  2. Download and cache the certificate.
  3. Build the canonical signing string for the message type.
  4. Verify the signature using the certificate's public key.

References:
  https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
"""
import base64
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

_cert_cache: Dict[str, x509.Certificate] = {}

# Fields used to build the signature string, by message type
_NOTIFICATION_FIELDS = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
_SUBSCRIPTION_FIELDS = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]


def _validate_cert_url(url: str) -> bool:
    """Ensure the certificate URL is from AWS."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.hostname or ""
    return host.endswith(".amazonaws.com")


async def _fetch_certificate(url: str) -> x509.Certificate:
    """Download and cache an SNS signing certificate."""
    if url in _cert_cache:
        return _cert_cache[url]

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()

    cert = x509.load_pem_x509_certificate(resp.content)
    _cert_cache[url] = cert
    return cert


def _build_signing_string(message: Dict[str, Any], msg_type: str) -> bytes:
    """Build the canonical string-to-sign for an SNS message."""
    if msg_type == "Notification":
        fields = _NOTIFICATION_FIELDS
    else:
        fields = _SUBSCRIPTION_FIELDS

    parts: list[str] = []
    for field in fields:
        value = message.get(field)
        if value is not None:
            parts.append(field)
            parts.append(str(value))

    return ("\n".join(parts) + "\n").encode("utf-8")


async def verify_sns_message(message: Dict[str, Any]) -> bool:
    """Verify the signature of an SNS message.

    Returns True if valid, False otherwise. Does not raise.
    """
    try:
        cert_url = message.get("SigningCertURL") or message.get("SigningCertUrl", "")
        if not _validate_cert_url(cert_url):
            logger.warning("SNS cert URL rejected: %s", cert_url)
            return False

        signature_b64 = message.get("Signature", "")
        signature = base64.b64decode(signature_b64)

        msg_type = message.get("Type", "")
        signing_string = _build_signing_string(message, msg_type)

        cert = await _fetch_certificate(cert_url)
        public_key = cert.public_key()

        if not isinstance(public_key, rsa.RSAPublicKey):
            logger.warning("SNS certificate does not use RSA key")
            return False

        sig_version = message.get("SignatureVersion", "1")
        if sig_version == "2":
            hash_algo = hashes.SHA256()
        else:
            hash_algo = hashes.SHA1()

        public_key.verify(signature, signing_string, padding.PKCS1v15(), hash_algo)
        return True

    except Exception:
        logger.exception("SNS signature verification failed")
        return False


async def confirm_subscription(message: Dict[str, Any]) -> bool:
    """Auto-confirm an SNS SubscriptionConfirmation by GETting the SubscribeURL."""
    subscribe_url = message.get("SubscribeURL", "")
    if not subscribe_url:
        logger.warning("No SubscribeURL in subscription confirmation message")
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(subscribe_url, timeout=10)
            resp.raise_for_status()
        logger.info("SNS subscription confirmed: %s", message.get("TopicArn", ""))
        return True
    except Exception:
        logger.exception("Failed to confirm SNS subscription")
        return False


def parse_sns_notification(message: Dict[str, Any]) -> Dict[str, Any]:
    """Extract useful fields from an SNS Notification wrapping a CloudWatch alarm.

    Returns a dict with the parsed alarm data and metadata.
    """
    import json

    raw_message = message.get("Message", "")

    try:
        alarm_data = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        alarm_data = {"raw": raw_message}

    return {
        "message_id": message.get("MessageId"),
        "topic_arn": message.get("TopicArn"),
        "subject": message.get("Subject"),
        "timestamp": message.get("Timestamp"),
        "alarm_data": alarm_data,
    }


def format_alarm_prompt(parsed: Dict[str, Any]) -> str:
    """Format a parsed SNS notification into a prompt for the agent."""
    import json

    alarm = parsed.get("alarm_data", {})
    subject = parsed.get("subject") or "Unknown"
    topic = parsed.get("topic_arn") or "Unknown"
    timestamp = parsed.get("timestamp") or "Unknown"

    alarm_name = alarm.get("AlarmName", subject)
    description = alarm.get("AlarmDescription", "N/A")
    old_state = alarm.get("OldStateValue", "N/A")
    new_state = alarm.get("NewStateValue", "N/A")
    reason = alarm.get("NewStateReason", "N/A")
    region = alarm.get("Region", "N/A")
    account = alarm.get("AWSAccountId", "N/A")

    return f"""## AWS CloudWatch Alarm Notification

**Alarm:** {alarm_name}
**Description:** {description}
**State Change:** {old_state} → {new_state}
**Reason:** {reason}
**Timestamp:** {timestamp}
**Region:** {region}
**Account:** {account}
**SNS Topic:** {topic}

### Raw Alarm Data
```json
{json.dumps(alarm, indent=2, default=str)}
```

Please analyze this incident and provide:
1. Likely root causes
2. Impact assessment
3. Recommended remediation steps
4. Preventive measures for the future"""
