from fcm_django.models import FCMDevice

def send_fcm_notification(user, title, message):
    if user.fcm_token:
        device = FCMDevice.objects.create(registration_id=user.fcm_token, type="android")
        device.send_message(title=title, body=message)
