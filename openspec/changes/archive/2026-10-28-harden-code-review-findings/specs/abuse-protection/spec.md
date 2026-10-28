# Spec Delta

## MODIFIED Requirements

### Requirement: Client IP determination

The service SHALL use the direct peer IP by default. It SHALL honor forwarded client-address information only when the immediate peer is configured in `klaro.trusted_proxies`; forwarding headers from every other peer SHALL be ignored. Rate limits and backoff SHALL key a client by its IPv4 address or by the /64 network of its IPv6 address, counting IPv4-mapped IPv6 addresses as IPv4.

#### Scenario: Untrusted forwarding header

- **WHEN** a direct client supplies `X-Forwarded-For` but its peer is not a trusted proxy
- **THEN** rate limiting and backoff use the direct peer IP rather than the spoofed header value

#### Scenario: Trusted reverse proxy

- **WHEN** a request arrives through a configured trusted proxy with a sanitized client-address header
- **THEN** rate limiting and backoff use the forwarded end-client IP consistently

#### Scenario: Rotating IPv6 addresses share one allowance

- **WHEN** a client makes creation attempts from different addresses within the same IPv6 /64
- **THEN** all attempts count against one fixed-window allowance and one recipient backoff, while another /64 is unaffected

### Requirement: Backoff enforcement and reset

During recipient backoff, creation attempts SHALL return `429` with JSON error code `recipient_backoff` and `Retry-After`, without calling Pushover or changing the delay. A successful Pushover acceptance SHALL reset the IP's backoff level. A client SHALL be forgotten, restarting at a 60-second delay, once 3600 further seconds have passed after its block ended.

#### Scenario: Wait elapses and delivery succeeds

- **WHEN** an IP makes a creation attempt after its backoff expires and Pushover accepts the notification
- **THEN** the request proceeds normally and the IP's next recipient rejection starts again at a 60-second delay

#### Scenario: Rate limit and backoff coincide

- **WHEN** both controls reject the same creation attempt with different remaining delays
- **THEN** the service returns one `429` without calling Pushover and sets `Retry-After` to the longer remaining delay

#### Scenario: Idle backoff state is forgotten

- **WHEN** a client's backoff block ended at least 3600 seconds ago without another recipient rejection
- **THEN** its backoff state is removed and its next recipient rejection starts again at a 60-second delay
