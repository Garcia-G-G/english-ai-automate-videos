"""Reels publishers for Meta: Instagram (Instagram Login API) and a Facebook Page.

    publisher = get_publisher("instagram")
    result = publisher.publish("output/approved/quiz/x.mp4", caption, ["AprendeInglés"])
    result.success, result.upload_id, result.url   # remote id and permalink

Credentials come only from the environment: FB_PAGE_ID and FB_PAGE_TOKEN, for
both (Instagram publishes through the Page, STEP 72). Both classes are uploader.BaseUploader backends, so
UploadManager and the idempotency guard drive them like any other platform.
"""
from .common import MetaError, RateLimited, ReelSpecError, TokenExpired, validate_reel
from .meta_facebook import FacebookReelsPublisher
from .meta_instagram import InstagramReelsPublisher

PUBLISHERS = {"instagram": InstagramReelsPublisher, "facebook": FacebookReelsPublisher}


def get_publisher(platform: str):
    return PUBLISHERS[platform]()


__all__ = ["PUBLISHERS", "get_publisher", "validate_reel", "MetaError", "RateLimited",
           "ReelSpecError", "TokenExpired", "InstagramReelsPublisher", "FacebookReelsPublisher"]
