"""
dojo/signals.py
---------------
Django signals — side effects triggered by model events.

post_save on User:
  When a new student registers, automatically create:
    - 9 BeltProgress rows (white→master), first one set to 'active'
    - 1 Streak row initialised to 0
    - 1 UserBadge for 'first_correct' once they get their first answer right
      (that one is created in the view, not here)

Signals are connected in DojoConfig.ready() in apps.py.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="dojo.User")
def create_student_profile(sender, instance, created, **kwargs):
    """Auto-create belt progress and streak for new students."""
    if not created:
        return
    if instance.role != "student":
        return

    # Import here to avoid circular imports at module load time
    from dojo.models import BeltProgress, Streak, BELT_ORDER

    # Create 9 BeltProgress rows — first is active, rest locked
    belt_rows = []
    for i, belt_id in enumerate(BELT_ORDER):
        belt_rows.append(BeltProgress(
            user=instance,
            belt_id=belt_id,
            status="active" if i == 0 else "locked",
        ))
    BeltProgress.objects.bulk_create(belt_rows, ignore_conflicts=True)

    # Create streak tracker
    Streak.objects.get_or_create(user=instance)
