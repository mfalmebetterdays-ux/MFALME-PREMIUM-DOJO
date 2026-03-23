"""
dojo/management/commands/seed.py
---------------------------------
Custom Django management command to seed the database with:
  - A superuser / admin account
  - Demo tutors across Kenyan counties
  - Optional demo students with belt progress

Usage:
    python manage.py seed
    python manage.py seed --with-students 50
    python manage.py seed --reset          (wipes and re-seeds)
"""

import random
from django.core.management.base import BaseCommand
from django.db import transaction
from dojo.models import (
    User, BeltProgress, Streak, BELT_ORDER,
)


FIRST_NAMES = [
    "Amara","Kofi","Zara","David","Fatima","James","Aisha","Samuel",
    "Grace","Mohammed","Priya","Boniface","Agnes","Caroline","Kevin",
    "Diana","Ali","Joyce","Peter","Sarah","John","Mary","Paul","Ruth",
]
LAST_NAMES = [
    "Osei","Mensah","Ahmed","Kamau","Hassan","Njoroge","Mwangi",
    "Odhiambo","Wanjiku","Ali","Patel","Kimani","Korir","Maina",
    "Otieno","Waweru","Ndungu","Karanja","Mutua","Achieng",
]
COUNTIES = [
    "Nairobi","Mombasa","Kisumu","Nakuru","Kiambu",
    "Thika","Eldoret","Machakos","Meru","Kisii",
]
SCHOOLS = [
    "Aga Khan Academy","Brookhouse School","Hillcrest School",
    "Peponi School","Braeburn School","Light Academy",
    "St. Mary's School","Riara School","Oshwal Academy",
    "St. Austin's Academy","Alliance Girls","Nairobi School",
]
TUTOR_SPECS = ["primary","junior","senior","all"]


class Command(BaseCommand):
    help = "Seed the database with an admin user, demo tutors, and optional students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-students",
            type=int,
            default=0,
            metavar="N",
            help="Number of demo students to create (default: 0)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all non-superuser accounts before seeding",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting non-superuser accounts…")
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.WARNING("  Deleted all non-superuser users."))

        with transaction.atomic():
            self._create_admin()
            self._create_tutors()
            n = options["with_students"]
            if n:
                self._create_students(n)

        self.stdout.write(self.style.SUCCESS("\nSeed complete ✓"))

    # ── ADMIN ──────────────────────────────────────────────────────────────

    def _create_admin(self):
        email = "admin@timesdojo.com"
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"  Admin already exists: {email}")
            return
        User.objects.create_superuser(
            username=email,
            email=email,
            password="dojo2025",
            first_name="Admin",
            last_name="User",
            role="admin",
            county="Nairobi",
            school="TimesTable Dojo HQ",
        )
        self.stdout.write(self.style.SUCCESS(
            f"  Created admin: {email} / dojo2025"
        ))

    # ── TUTORS ─────────────────────────────────────────────────────────────

    def _create_tutors(self):
        tutors = [
            ("Peter",    "Karanja",  "primary", "Nairobi",  "Nairobi School"),
            ("Grace",    "Achieng",  "all",     "Mombasa",  "Aga Khan Academy"),
            ("Samuel",   "Mwita",    "senior",  "Nairobi",  "Alliance Girls"),
            ("Joyce",    "Ndungu",   "junior",  "Kiambu",   "Brookhouse School"),
            ("Ali",      "Hassan",   "primary", "Mombasa",  "Hillcrest School"),
            ("Diana",    "Waweru",   "all",     "Nairobi",  "Peponi School"),
            ("Kevin",    "Otieno",   "junior",  "Kisumu",   "Braeburn School"),
            ("James",    "Mutua",    "senior",  "Machakos", "Light Academy"),
            ("Priya",    "Patel",    "all",     "Nairobi",  "Riara School"),
            ("Agnes",    "Korir",    "primary", "Eldoret",  "St. Mary's School"),
            ("Caroline", "Maina",    "junior",  "Thika",    "Oshwal Academy"),
        ]
        created = 0
        for first, last, spec, county, school in tutors:
            email = f"{first.lower()}.{last.lower()}@tutors.dojo.co.ke"
            if User.objects.filter(email=email).exists():
                continue
            User.objects.create_user(
                username=email,
                email=email,
                password="tutor1234",
                first_name=first,
                last_name=last,
                role="tutor",
                county=county,
                school=school,
                spec=spec,
                is_paid=True,   # "verified"
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(
            f"  Created {created} tutors (password: tutor1234)"
        ))

    # ── STUDENTS ───────────────────────────────────────────────────────────

    def _create_students(self, n):
        created = 0
        for i in range(n):
            first  = random.choice(FIRST_NAMES)
            last   = random.choice(LAST_NAMES)
            county = random.choice(COUNTIES)
            school = random.choice(SCHOOLS)
            email  = f"{first.lower()}{last.lower()}{i}@students.dojo.co.ke"

            if User.objects.filter(email=email).exists():
                continue

            user = User.objects.create_user(
                username=email,
                email=email,
                password="student1234",
                first_name=first,
                last_name=last,
                role="student",
                county=county,
                school=school,
                is_paid=random.random() > 0.3,
            )
            # Signal creates BeltProgress rows, but we also randomly advance them
            belts_passed = random.randint(0, 4)
            for j, belt_id in enumerate(BELT_ORDER):
                bp = BeltProgress.objects.get(user=user, belt_id=belt_id)
                if j < belts_passed:
                    bp.status = "passed"
                    bp.passed = True
                    bp.attempts = random.randint(1, 3)
                    bp.best_acc = round(random.uniform(0.72, 0.99), 2)
                    bp.levels_done = [2, 5, 10, 11]  # simplified
                    bp.save()
                elif j == belts_passed:
                    bp.status = "active"
                    bp.save()
                    break

            # Random streak
            streak = Streak.objects.get(user=user)
            streak.count = random.randint(0, 30)
            streak.save()

            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Created {created} demo students (password: student1234)"
        ))
