# Roadmap

## Milestone 1: Foundation
- [x] Project scaffold
- [x] Config + db bootstrap
- [x] Health endpoint
- [ ] Lint/test tooling scripts

## Milestone 2: Identity
- [x] User model
- [x] Register/login/logout
- [x] Session/cookie policy

## Milestone 3: Social Graph + Feed
- [x] Follow/unfollow
- [x] Post creation (text/image/video metadata)
- [x] Feed query + pagination

## Milestone 4: Media
- [x] Local media adapter
- [x] GCS media adapter
- [~] Video ingest + HLS packaging pipeline (ingest planning + upload ticket + finalize status APIs + local ffmpeg worker with one-shot/loop modes + systemd service template; robust queue semantics + GCS transcode path pending)
- [x] Playback URL strategy (public/signed)

## Milestone 5: Messaging
- [ ] Realtime channel architecture
- [ ] Direct messages
- [ ] Moderation hooks

## Milestone 6: Local QA
- [ ] Smoke tests for core user journeys
- [ ] Performance baseline
- [ ] Security checks
