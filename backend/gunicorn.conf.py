"""Single-instance limits are coordinated inside one threaded worker."""

import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"
workers = 1
worker_class = "gthread"
threads = 4
worker_connections = 16
backlog = 16
timeout = 30  # Worker liveness only; computation has its own kill deadline.
graceful_timeout = 15
keepalive = 2
limit_request_line = 2048
limit_request_fields = 32
limit_request_field_size = 4096
max_requests = 1000
accesslog = None  # Do not log user payloads, query strings, or receipts.
errorlog = "-"
forwarded_allow_ips = "*"  # Hosted port is behind Render's trusted ingress.
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
control_socket_disable = True
