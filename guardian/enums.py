from django.db import models


class GuardianStudentRelationship(models.TextChoices):
    MOTHER = "mother"
    FATHER = "father"
    SISTER = "sister"
    BROTHER = "brother"
    GRANDPARENT = "grandparent"
    OTHER = "other"

class GuardianGender(models.TextChoices):
    MALE = "male"
    FEMALE = "female"
