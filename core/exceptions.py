from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_payload = {
            "success": False,
            "message": "An error occurred.",
            "errors": response.data,
            "status_code": response.status_code,
        }

        # Try to pull a clean top-level message
        if isinstance(response.data, dict):
            non_field = response.data.get("errors") or response.data.get("detail")
            if non_field:
                if isinstance(non_field, list):
                    error_payload["message"] = str(non_field[0])
                else:
                    error_payload["message"] = str(non_field)

        response.data = error_payload

    return response