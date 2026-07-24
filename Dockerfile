FROM ghcr.io/Rohitkumarthongar/frappe

LABEL org.opencontainers.image.source=https://github.com/Rohitkumarthongar/Whats-app-erpnext
LABEL maintainer="Rohit Kumar Soni <rohitkumarsoni713@gmail.com>"
RUN bench get-app https://github.com/Rohitkumarthongar/Whats-app-erpnext.git --skip-assets
