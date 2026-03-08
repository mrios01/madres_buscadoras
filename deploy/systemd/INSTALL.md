# systemd setup (VM)

## 1) Copy project to VM

Expected layout in VM:

- `/opt/marzlive_upgrade`
- `/opt/marzlive_upgrade/.venv`
- `/opt/marzlive_upgrade/.env`

## 2) Create service user

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin marzlive || true
```

## 3) Prepare permissions

```bash
sudo mkdir -p /opt/marzlive_upgrade/data/media
sudo chown -R marzlive:marzlive /opt/marzlive_upgrade
```

## 4) Install service file

```bash
sudo cp deploy/systemd/marzlive-media-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## 5) Enable and start

```bash
sudo systemctl enable --now marzlive-media-worker.service
```

## 6) Verify

```bash
systemctl status marzlive-media-worker.service
journalctl -u marzlive-media-worker.service -f
```

## Optional tuning

Edit override:

```bash
sudo systemctl edit marzlive-media-worker.service
```

Example override values:

```ini
[Service]
Environment=MEDIA_WORKER_BACKEND=local
Environment=MEDIA_WORKER_INTERVAL_SECONDS=3
```

Then reload + restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart marzlive-media-worker.service
```
