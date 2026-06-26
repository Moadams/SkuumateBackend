import logging

logger = logging.getLogger(__name__)


class SMSService:
    """Send SMS through the configured provider."""

    @staticmethod
    def send(provider, to_phone, message):
        """
        Send an SMS using the given provider configuration.

        Args:
            provider: NotificationProvider instance (channel=sms)
            to_phone: str recipient phone number
            message: str SMS content

        Returns:
            (success: bool, message: str)
        """
        provider_type = provider.provider_type
        config = provider.config

        try:
            if provider_type == "twilio":
                return SMSService._send_via_twilio(config, to_phone, message)
            elif provider_type == "africas_talking":
                return SMSService._send_via_africas_talking(config, to_phone, message)
            else:
                return False, f"Unsupported SMS provider: {provider_type}"
        except Exception as e:
            logger.exception("SMS send failed via %s: %s", provider_type, e)
            return False, str(e)

    @staticmethod
    def _send_via_twilio(config, to_phone, message):
        account_sid = config.get("account_sid", "")
        auth_token = config.get("auth_token", "")
        from_number = config.get("from_number", "")

        if not account_sid or not auth_token or not from_number:
            return False, "Twilio credentials not fully configured"

        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=message,
                from_=from_number,
                to=to_phone,
            )
            return True, "Sent via Twilio"
        except ImportError:
            return False, "twilio package not installed"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _send_via_africas_talking(config, to_phone, message):
        api_key = config.get("api_key", "")
        username = config.get("username", "")
        from_number = config.get("from_number", "")

        if not api_key or not username:
            return False, "Africa's Talking credentials not configured"

        try:
            import africastalking
            africastalking.initialize(username=username, api_key=api_key)
            sms = africastalking.SMS
            response = sms.send(message, [to_phone], from_=from_number or None)
            if response.get("SMSMessageData", {}).get("Recipients", []):
                return True, "Sent via Africa's Talking"
            return False, str(response)
        except ImportError:
            return False, "africastalking package not installed"
        except Exception as e:
            return False, str(e)
