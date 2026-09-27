from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group, Permission, User
from django.db.models.signals import post_migrate
from .models import UserProfile


ROLE_ADMIN_GROUP = "Quản trị viên và giảng viên"


@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        # Tự động tạo UserProfile trống khi một User mới được tạo từ Admin
        UserProfile.objects.create(user=instance)
    else:
        # Đảm bảo profile được lưu khi user cập nhật
        if hasattr(instance, 'userprofile'):
            instance.userprofile.save()


@receiver(post_save, sender=UserProfile)
def synchronize_profile_permissions(sender, instance, **kwargs):
    user = instance.user
    has_admin_access = instance.role in ("admin", "lecturer")
    group, created = Group.objects.get_or_create(name=ROLE_ADMIN_GROUP)
    if created:
        group.permissions.set(Permission.objects.all())

    if has_admin_access:
        group.user_set.add(user)
    else:
        group.user_set.remove(user)

    is_staff = has_admin_access or user.is_superuser
    if user.is_staff != is_staff:
        User.objects.filter(pk=user.pk).update(is_staff=is_staff)
        user.is_staff = is_staff


@receiver(post_migrate)
def configure_role_permissions(sender, **kwargs):
    if sender.label != "firstApp":
        return

    group, _ = Group.objects.get_or_create(name=ROLE_ADMIN_GROUP)
    group.permissions.set(Permission.objects.all())

    privileged_profiles = UserProfile.objects.filter(role__in=("admin", "lecturer"))
    privileged_user_ids = list(privileged_profiles.values_list("user_id", flat=True))
    group.user_set.add(*privileged_user_ids)
    User.objects.filter(pk__in=privileged_user_ids, is_staff=False).update(is_staff=True)