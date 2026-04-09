import argparse
from pathlib import Path

import tornado.httpserver
import tornado.ioloop
import tornado.web

from tornado.ioloop import IOLoop

from app.api.auth import LoginHandler, LogoutHandler, RegisterHandler
from app.api.demo import (
    GoogleAuthDemoHandler,
    LoginPageHandler,
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
    MissingPersonPrivateDetailHandler,
    MissingPersonPublicDetailHandler,
    MissingPersonsPublicListHandler,
)
from app.core.config import get_settings
from app.core.db import create_client, get_db
from app.services.auth import ensure_auth_indexes
from app.services.media import ensure_media_indexes
from app.services.missing_persons import ensure_missing_person_indexes
from app.services.social import ensure_social_indexes


BASE_DIR = Path(__file__).resolve().parent


class Application(tornado.web.Application):
    def __init__(self):
        settings = get_settings()
        client = create_client()
        db = get_db(client)

        handlers = [
            (r"/", LoginPageHandler),
            (r"/login", LoginPageHandler),
            (r"/missing-profiles", MissingProfilesPageHandler),
            (r"/health", HealthHandler),
            (r"/auth/register", RegisterHandler),
            (r"/auth/login", LoginHandler),
            (r"/auth/logout", LogoutHandler),
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
            cookie_secret=settings.cookie_secret,
            template_path=str(BASE_DIR / "templates"),
            static_path=str(BASE_DIR / "static"),
        )

        IOLoop.current().spawn_callback(ensure_auth_indexes, db)
        IOLoop.current().spawn_callback(ensure_social_indexes, db)
        IOLoop.current().spawn_callback(ensure_media_indexes, db)
        IOLoop.current().spawn_callback(ensure_missing_person_indexes, db)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=get_settings().app_port)
    args = parser.parse_args()

    app = Application()
    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    server.listen(args.port)
    print(f"marzlive_upgrade running on http://localhost:{args.port}")
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
