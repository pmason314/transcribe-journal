# Production Deployment Guide

## Setup Instructions

### 1. Install and enable the systemd service
```bash
# Copy service file to systemd
sudo cp /home/peter/transcribe/transcribe.service /etc/systemd/system/

# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable transcribe

# Start the service
sudo systemctl start transcribe
```

### 2. Manage the service
```bash
# Check status
sudo systemctl status transcribe

# View logs
tail -f /home/peter/transcribe/logs/server.log
tail -f /home/peter/transcribe/logs/error.log

# Or use journalctl
sudo journalctl -u transcribe -f

# Restart service
sudo systemctl restart transcribe

# Stop service
sudo systemctl stop transcribe

# Disable autostart on boot
sudo systemctl disable transcribe
```

### 3. Update the application
```bash
# After making code changes
sudo systemctl restart transcribe
```

## Configuration

Environment variables can be set in the service file or create a `.env` file:

- `PORT` - Server port (default: 8000)
- `HOST` - Bind address (default: 0.0.0.0)
- `MODEL_PATH` - Path to model (default: models/granite-speech-4.1-2b)


## Monitoring

### Check if service is running
```bash
sudo systemctl is-active transcribe
```

### Monitor resource usage
```bash
# CPU and memory usage
ps aux | grep python | grep server.py

# Or using systemd
systemctl status transcribe
```

### Test the API
```bash
# Health check
curl http://localhost:8000/health

# Transcribe audio
curl -X POST "http://localhost:8000/transcribe" -F "audio=@test.wav"
```

## Firewall

Port 8000 is already configured:
```bash
sudo ufw status
```

If you need to change the port, update both the service file and firewall:
```bash
sudo ufw allow NEW_PORT/tcp
sudo ufw delete allow 8000/tcp
```

## Troubleshooting

### Service won't start
1. Check logs: `sudo journalctl -u transcribe -n 50`
2. Verify paths in service file are correct
3. Ensure virtual environment exists: `ls /home/peter/transcribe/.venv`
4. Check permissions: `ls -la /home/peter/transcribe`

### Model loading issues
- Ensure model files exist in `models/granite-speech-4.1-2b/`
- Check available memory (model requires ~5GB RAM)

### Connection refused
- Verify service is running: `sudo systemctl status transcribe`
- Check firewall: `sudo ufw status`
- Test locally first: `curl http://localhost:8000/`
