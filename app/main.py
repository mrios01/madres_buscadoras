import argparse
import logging
from pathlib import Path

import tornado.httpserver
import tornado.ioloop
import tornado.web

from tornado.ioloop import IOLoop

from app.api.auth import LoginHandler, LogoutHandler, RegisterHandler
from app.api.chat import ChatImageUploadHandler
from app.api.chat import ChatMessagesHandler
from app.api.chat import ChatPageHandler
from app.api.chat import ChatSocketHandler
from app.api.demo import (
    GoogleAuthDemoHandler,
    LoginPageHandler,
    MissingPersonCreatePageHandler,
    MissingProfilesPageHandler,
)
from app.api.feed import FeedHandler
from app.api.health import HealthHandler
from app.api.social import CreatePostHandler, FollowHandler, UnfollowHandler
from app.api.media import (
    MediaFinalizeHandler,
    MediaIngestPlanHandler,
    MediaPlaybackUrlHandler,
    MediaUploadTicketHandler,
)
from app.api.missing_persons import (
    MissingPersonCreateHandler,
    MissingPersonImageProxyHandler,
    MissingPersonImageUploadHandler,
    MissingPersonPrivateDetailHandler,
    MissingPersonPublicDetailHandler,
    MissingPersonsPublicListHandler,
)
from app.api.legal import (
    PrivacyHandler,
    TermsHandler,
    SecurityAgreementHandler,
    SecurityAcknowledgeHandler,
)
from app.core.config import get_settings
from app.core.db import create_client, get_db
from app.services.auth import ensure_auth_indexes
from app.services.chat import AsyncPubSubListener
from app.services.chat import BulletinHub
from app.services.chat import build_pubsub_clients
from app.services.chat import ensure_chat_indexes
from app.services.media import ensure_media_indexes
from app.services.missing_persons import ensure_missing_person_indexes
from app.services.social import ensure_social_indexes


BASE_DIR = Path(__file__).resolve().parent
LOGGER = logging.getLogger("madres_buscadoras.main")


class Application(tornado.web.Application):
    def __init__(self):
        settings = get_settings()
        client = create_client()
        db = get_db(client)
        chat_hub = BulletinHub()

        bulletin_publisher = None
        bulletin_topic_path = None
        pubsub_listener = None

        if settings.bulletin_pubsub_enabled:
            try:
                bulletin_publisher, bulletin_topic_path = build_pubsub_clients(
                    settings
                )
                if (
                    settings.bulletin_project_id
                    and settings.bulletin_subscription_id
                ):
                    pubsub_listener = AsyncPubSubListener(
                        project_id=settings.bulletin_project_id,
                        subscription_id=settings.bulletin_subscription_id,
                        hub=chat_hub,
                        io_loop=IOLoop.current(),
                    )
                    pubsub_listener.start()
            except Exception:
                LOGGER.exception(
                    "Bulletin Pub/Sub bootstrap failed; "
                    "falling back to local fanout"
                )
                bulletin_publisher = None
                bulletin_topic_path = None
                pubsub_listener = None

        handlers = [
            (r"/", LoginPageHandler),
            (r"/login", LoginPageHandler),
            (r"/missing-profiles", MissingProfilesPageHandler),
            (r"/missing-profiles/create", MissingPersonCreatePageHandler),
            (r"/health", HealthHandler),
            (r"/privacy", PrivacyHandler),
            (r"/terms", TermsHandler),
            (r"/security-agreement", SecurityAgreementHandler),
            (r"/pizarra", ChatPageHandler),
            (r"/auth/register", RegisterHandler),
            (r"/auth/login", LoginHandler),
            (r"/auth/logout", LogoutHandler),
            (r"/api/security/acknowledge", SecurityAcknowledgeHandler),
            (r"/chat/messages", ChatMessagesHandler),
            (r"/chat/upload-image", ChatImageUploadHandler),
            (r"/chat/ws", ChatSocketHandler),
            (r"/demo/google-auth", GoogleAuthDemoHandler),
            (r"/social/follow", FollowHandler),
            (r"/social/unfollow", UnfollowHandler),
            (r"/posts", CreatePostHandler),
            (r"/feed", FeedHandler),
            (r"/media/ingest/plan", MediaIngestPlanHandler),
            (r"/media/upload-ticket", MediaUploadTicketHandler),
            (r"/media/ingest/finalize", MediaFinalizeHandler),
            (r"/media/playback-url", MediaPlaybackUrlHandler),
            (r"/missing-persons", MissingPersonsPublicListHandler),
            (r"/missing-persons/create", MissingPersonCreateHandler),
            (
                r"/missing-persons/upload-image",
                MissingPersonImageUploadHandler,
            ),
            (
                r"/missing-persons/image-proxy",
                MissingPersonImageProxyHandler,
            ),
            (r"/missing-persons/([^/]+)", MissingPersonPublicDetailHandler),
            (
                r"/missing-persons/private/([^/]+)",
                MissingPersonPrivateDetailHandler,
            ),
        ]

        super().__init__(
            handlers,
            debug=settings.debug,
            db=db,
            chat_hub=chat_hub,
            bulletin_publisher=bulletin_publisher,
            bulletin_topic_path=bulletin_topic_path,
            bulletin_pubsub_listener=pubsub_listener,
            cookie_secret=settings.cookie_secret,
            template_path=str(BASE_DIR / "templates"),
            static_path=str(BASE_DIR / "static"),
        )

        IOLoop.current().spawn_callback(ensure_auth_indexes, db)
        IOLoop.current().spawn_callback(ensure_social_indexes, db)
        IOLoop.current().spawn_callback(ensure_media_indexes, db)
        IOLoop.current().spawn_callback(ensure_missing_person_indexes, db)
        IOLoop.current().spawn_callback(ensure_chat_indexes, db)


def main():
    import os as _os
    parser = argparse.ArgumentParser()
    # Cloud Run injects PORT; fall back to APP_PORT for local dev.
    _default_port = int(_os.environ.get("PORT", get_settings().app_port))
    parser.add_argument("--port", type=int, default=_default_port)
    args = parser.parse_args()

    app = Application()
    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    server.listen(args.port)
    print(f"marzlive_upgrade running on http://localhost:{args.port}")
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
