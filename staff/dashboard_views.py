from django.utils import timezone
import datetime
from academics.models import ClassTeacher, Term, TimeTableSlot
from attendance.models import Attendance
from core.permissions import IsTeacher
from core.responses import ApiResponse
from exams.models import StudentReportSubjectScore
from rest_framework.views import APIView
from django.db.models.functions import ExtractWeekDay


from django.db.models import Count, Q

from staff.models import StaffProfile
from students.models import Enrollment


class TeacherDasbhoardView(APIView):
    permission_classes = [IsTeacher]
    def get(self, request):
        current_term = Term.objects.filter(is_current = True).first()
        teacher_class = ClassTeacher.objects.filter(teacher = request.user, is_active =True).select_related("klass").first()
        
        context = {
                "attendanceTrend":self._getAttendanceTrend(current_term,teacher_class),
                
                "classAttendance":self._getClassAttendance(request.user, current_term, teacher_class),
                "schedule":self._getTeacherTodaySchedule(request.user, current_term),
                "topPerformers": [
                    { "name": 'Kofi Mensah', "score": '94%', "trend": 'up' },
                    { "name": 'Abena Boateng', "score": '92%', "trend": 'up' },
                    { "name": 'Kwame Addo', "score": '89%', "trend": 'stable' },
                ],
                "strugglingStudents": [
                    { "name": 'Yaw Frimpong', "score": '42%', "trend": 'down' },
                    { "name": 'Esi Ankomah', "score": '45%', "trend": 'stable' },
                    { "name": 'Samuel Owusu', "score": '48%', "trend": 'down' },
                ],
                "tasks": [
                    { "id": 1, "text": 'Submit Form 3B Math Lesson Plan', "category": 'Lesson Plan', "due": 'Today', "completed": False },
                    { "id": 2, "text": 'Mark Mid-term Social Studies scripts', "category": 'Grading', "due": 'Tomorrow', "completed": True },
                    { "id": 3, "text": 'Hall duty - Main Block', "category": 'Duty', "due": 'Friday', "completed": False },
                ],
                "announcements": [
                    { "id": 1, "title": 'Staff Meeting', "msg": 'Emergency meeting in the staff room', "priority": 'high', "time": '10 mins ago' },
                    { "id": 2, "title": 'Science Lab closure', "msg": 'Lab will be closed for maintenance', "priority": 'medium', "time": '2 hours ago' },
                ]
                }
        return ApiResponse.success(data = context, message="Teacher dashboard data")

    def _getAttendanceTrend(self, current_term, teacher_class):
        today =datetime.date.today()
        monday = today - datetime.timedelta(days = today.weekday())
        sunday = monday + datetime.timedelta(days=6)

        term_attendance = Attendance.objects.filter(klass = teacher_class.klass, term = current_term, date__gte = monday, date__lte = sunday).annotate(day_of_week = ExtractWeekDay("date")).values("day_of_week").annotate(
            present_count = Count("id", filter = Q(status = Attendance.Status.PRESENT)),
            absent_count = Count("id", filter = Q(status = Attendance.Status.ABSENT)),
            late_count = Count("id", filter = Q(status = Attendance.Status.LATE))
        ).order_by("day_of_week")

        day_names = ["", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat", "Sun"]

        data_dict = {
            record['day_of_week']: record for record in term_attendance
        }

        results = []
        for day_num in range(1,6):
            if day_num in data_dict:
                record = data_dict[day_num]
                results.append({
                    "day":day_names[day_num],
                    "present": record['present_count'],
                    "absent": record["absent_count"],
                    "late":record["late_count"]
                })
            else:
                results.append({
                    "day":day_names[day_num],
                    "present":0,
                    "absent":0,
                    "late":0
                })

        return results

    def _getClassAttendance(self, user, current_term, teacher_class):
        today = datetime.date.today()
        

        if not teacher_class:
            return None
        
        attendance = Attendance.objects.filter(klass = teacher_class.klass, date = today)
        students_in_class = Enrollment.objects.filter(klass = teacher_class.klass, academic_year = current_term.academic_year, is_active = True).count()
        percentage_marked = (attendance.count() / students_in_class) * 100 if students_in_class > 0 else 0
        return {
            "class_name": teacher_class.klass.name,
            "present": attendance.filter(Q(status = Attendance.Status.PRESENT)).count(),
            "absent": attendance.filter(Q(status = Attendance.Status.ABSENT)).count(),
            "late":attendance.filter(Q(status = Attendance.Status.LATE)).count(),
            "percentage":percentage_marked
        }
    
    def _getTeacherTodaySchedule(self, user, current_term):
        today = timezone.localdate()
        weekday = today.weekday()
        today_weekday = today.strftime("%A")
        print(today_weekday)
        teacher_profile = StaffProfile.objects.filter(user = user).first()
        timetable_slots = TimeTableSlot.objects.filter(
            teacher = teacher_profile,
            day_of_week = today_weekday, term = current_term
        ).select_related("subject","klass")

        current_time = timezone.localtime().time()
        return [
            { "id": slot.id, "subject": slot.subject.name, "class": slot.klass.name, "time": f'{slot.start_time} - {slot.end_time}',"active": slot.start_time <= current_time <= slot.end_time }
            for slot in timetable_slots
        ]