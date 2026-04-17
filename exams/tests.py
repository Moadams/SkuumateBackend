from django.urls import reverse
from exams.models import AssessmentType
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

from schools.models import School

User = get_user_model()

class AssessmentTypeTests(APITestCase):
    def setUp(self):
        # create school a with user a
        self.school_a = School.objects.create( name = "school_a", email="school_a@skuumate.com")
        self.user_a = User.objects.create_user(email="user_a@example.com", password = "user_a_password", role = "admin")
        self.user_a.school = self.school_a
        self.user_a.save()

        # create school b with user b
        self.school_b = School.objects.create(name = "school_b", email = "school_b@skuumate.com")
        self.user_b = User.objects.create(email = "user_b@example.com", password = "user_b_password", role = "teacher")
        self.user_b.school = self.school_b
        self.user_b.save()

        self.url = reverse("assessment-types")

    def test_create_assessment_type_success(self):
        self.client.force_authenticate(user = self.user_a)
        data = {
            "name":"Mid terms",
            "max_score":100
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AssessmentType.objects.get().name, "Mid Terms")
        self.assertEqual(AssessmentType.objects.get().school, self.school_a)

    def test_queryset_isolation(self):
        AssessmentType.objects.create(school = self.school_b, name = "Main exams", max_score = 50)

        self.client.force_authenticate(user = self.user_a)
        response = self.client.get(self.url)
        self.assertEqual(response.data['data']['count'], 0)

    def test_duplicate_name_validation(self):
        AssessmentType.objects.create(school = self.school_a, name = "Main", max_score = 50)
        self.client.force_authenticate(self.user_a)
        data = {
            "name":"Main",
            "max_score":100
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code , status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", response.data['errors']['name'][0])