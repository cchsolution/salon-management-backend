from django.core.cache import cache
from rest_framework import serializers, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.notifications.models import InAppNotification

def get_user_notification_version(user_id):
    return cache.get(f"notif_ver_{user_id}", 1)

def invalidate_user_notification_cache(user_id):
    try:
        ver = cache.get(f"notif_ver_{user_id}", 1)
        cache.set(f"notif_ver_{user_id}", ver + 1, timeout=86400)
    except Exception:
        pass

class InAppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InAppNotification
        fields = ['id', 'user', 'title', 'message', 'notification_type', 'is_read', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']


class InAppNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = InAppNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return InAppNotification.objects.none()
        return InAppNotification.objects.filter(user=user)

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        ver = get_user_notification_version(user_id)
        qstr = request.META.get('QUERY_STRING', '')
        ckey = f"notif_list_{user_id}_v{ver}_{qstr}"
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=60)
        return res

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        user_id = request.user.id
        ver = get_user_notification_version(user_id)
        ukey = f"notif_unread_{user_id}_v{ver}"
        cached = cache.get(ukey)
        if cached is not None:
            return Response({'unread_count': cached})
        count = InAppNotification.objects.filter(user=request.user, is_read=False).count()
        cache.set(ukey, count, timeout=60)
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        invalidate_user_notification_cache(request.user.id)
        return Response(InAppNotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        InAppNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        invalidate_user_notification_cache(request.user.id)
        return Response({'message': 'All notifications marked as read.'})
