
from django.db.utils import IntegrityError

from .models import User


class AccountService:
    def create_account(self, user_data, school):
        if user_data.get("email") is None and user_data.get("phone") is None:
            raise ValueError("Provide either email or phone.")

        try:
            user = User.objects.create_user(
                email=user_data.get("email", self.generate_email(user_data.get("first_name"), user_data.get("last_name"))),
                phone=user_data.get("phone") or "",
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name"),
                role=user_data.get("role", User.Role.STAFF),
                must_change_password=user_data.get("must_change_password", True),
                school=school,
            )
            return user
        except IntegrityError as e:
            message = "A user with this email already exists." if "email" in str(e).lower() else f"Failed to create user: {str(e)}"
            raise ValueError(message)

            return user
        except Exception as e:
            raise ValueError(f"Failed to create user: {str(e)}")

    def generate_email(self, first_name, last_name):
        generated_email = f"{first_name.lower()[0]}.{last_name.lower()}@skuumate.com"
        return generated_email
