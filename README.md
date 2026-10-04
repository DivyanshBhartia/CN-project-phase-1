# CN Project Phase 1 — Divyansh

A four-Mac networking lab that demonstrates private DNS, HTTPS termination, load balancing, HTTP cache validation, and failure recovery. Clients resolve `app.divyansh.test` or `api.divyansh.test`, connect to an NGINX edge, and receive JSON from one of two Python backends.

See the [architecture document](01_architecture/architecture_doc.md) for topology, request flow, configuration decisions, and limitations.

## Lab services

| Machine | Role | Recorded address | Service |
| --- | --- | --- | --- |
| Mac 1 | Private DNS and client checks | `10.7.17.71` | dnsmasq, UDP/TCP 53 |
| Mac 2 | HTTPS edge and load balancer | `10.7.17.165` | NGINX, TCP 443 |
| Mac 3 | Backend A | `10.7.5.3` | Python HTTP server, TCP 3001 |
| Mac 4 | Backend B, client checks, packet capture | `10.7.11.219` | Python HTTP server, TCP 3002 |

These are recorded lab addresses, not fixed requirements. Recheck addresses and connectivity before each run. Both DNS names point to Mac 2 and serve the same endpoints.

## Repository layout

```text
01_architecture/
  architecture_doc.md       Topology, protocol flow, behavior, and evidence map
02_config/
  dnsmasq-project.conf       Private DNS records and listener addresses
  nginx.conf                HTTPS listener, upstreams, TLS paths, and logs
  cert.cnf                  Certificate subject and SAN configuration
  team-cert.pem             Public self-signed lab certificate
03_backend_code/
  server.py                 Shared implementation for backends A and B
04_evidence/
  Mac1/                     DNS, client checks, and failure screenshots
  Mac2/                     Edge checks, screenshots, and NGINX logs
  Mac3/                     Backend A and cache/failover screenshots
  Mac4/                     Backend B, client checks, and protocol capture
README.md
```

## Prerequisites

- Four mutually reachable Macs on the lab network, with the required ports accessible.
- Python 3 on Mac 3 and Mac 4. The backend uses only the standard library; no package installation is needed.
- dnsmasq on Mac 1 and NGINX with TLS support on Mac 2.
- OpenSSL for creating a fresh certificate/key pair, plus `curl` and `dig` for checks.
- Wireshark for inspecting the supplied capture or collecting new evidence.
- Administrative access where required to bind ports 53 and 443 and configure the macOS resolver.

There is no automated deployment or dependency installer in this repository.

## Run the lab

Run commands from the repository root on the specified machine. Keep backend and DNS foreground terminals open.

### 1. Confirm network values

Record each machine's active IPv4 address and verify peer connectivity. If addresses differ from the table:

- Update `listen-address` in `02_config/dnsmasq-project.conf` for Mac 1.
- Update both `host-record` addresses to Mac 2's address.
- Update both upstream addresses in `02_config/nginx.conf` for Mac 3 and Mac 4.
- Use the updated addresses in the checks below.

### 2. Start the backends

On Mac 3:

```sh
BACKEND=A PORT=3001 python3 03_backend_code/server.py
```

On Mac 4:

```sh
BACKEND=B PORT=3002 python3 03_backend_code/server.py
```

From Mac 2, confirm that both upstreams respond before starting NGINX:

```sh
curl --max-time 5 http://10.7.5.3:3001/api/status
curl --max-time 5 http://10.7.11.219:3002/api/status
```

Expect `{"backend": "A", "status": "ok"}` and the equivalent response for B.

### 3. Prepare TLS and NGINX on Mac 2

`nginx.conf` currently contains absolute paths under `/Users/vanshjain/Desktop/CN-project-phase-1`. Replace its certificate, key, access log, and error log paths with absolute paths for your checkout. Create the log directory if needed:

```sh
mkdir -p 04_evidence/Mac2/logs
```

The private key `02_config/team-key.pem` is intentionally ignored by Git and is not supplied. If the original matching key is unavailable, generate a fresh pair on Mac 2. The following command replaces the public certificate as well; save the existing certificate first if you need to retain it:

```sh
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 30 \
  -keyout 02_config/team-key.pem \
  -out 02_config/team-cert.pem \
  -config 02_config/cert.cnf
chmod 600 02_config/team-key.pem
```

Copy only the resulting public `team-cert.pem` to client checkouts. Never distribute the private key. The checked-in certificate is self-signed and valid from 2 October to 1 November 2026 (UTC); a regenerated certificate has new validity dates.

Validate and start NGINX using the edited configuration:

```sh
sudo nginx -t -c "$PWD/02_config/nginx.conf"
sudo nginx -c "$PWD/02_config/nginx.conf"
```

Ensure an existing NGINX instance is not already occupying port 443. This configuration has no port 80 listener or HTTP-to-HTTPS redirect.

### 4. Start DNS on Mac 1

```sh
sudo dnsmasq --test --conf-file="$PWD/02_config/dnsmasq-project.conf"
sudo dnsmasq --no-daemon --conf-file="$PWD/02_config/dnsmasq-project.conf"
```

Check that another DNS service is not occupying port 53. This configuration serves the lab zone and has no upstream resolver configured.

On a client, confirm both records explicitly:

```sh
dig @10.7.17.71 app.divyansh.test A
dig @10.7.17.71 api.divyansh.test A
```

Expect `10.7.17.165` with a configured TTL of 60 seconds. For normal hostname requests, configure the client to resolve `divyansh.test` through Mac 1. On macOS, a scoped `/etc/resolver/divyansh.test` file containing `nameserver 10.7.17.71` preserves the resolver used for other domains. Record any previous resolver configuration and restore it after the lab. `dig @...` tests Mac 1 directly; it does not prove that applications use the configured system resolver.

### 5. Verify HTTPS and balancing

On a client with the matching public certificate:

```sh
curl --max-time 10 --cacert 02_config/team-cert.pem \
  -i https://app.divyansh.test/api/status

for i in 1 2 3 4 5 6; do
  curl --max-time 10 --cacert 02_config/team-cert.pem \
    -sS -D - https://app.divyansh.test/api/status
  printf '\n'
done
```

Expect HTTP 200 and responses from both A and B, identifiable by JSON and `X-Backend`. Do not treat exact alternation as a requirement when other requests are running.

To isolate HTTPS from DNS setup, use this diagnostic request:

```sh
curl --max-time 10 --cacert 02_config/team-cert.pem \
  --resolve app.divyansh.test:443:10.7.17.165 \
  -i https://app.divyansh.test/api/status
```

`--resolve` bypasses DNS while retaining hostname and certificate validation. It is not DNS evidence. The documented checks use certificate validation rather than `curl -k`.

## Endpoints and cache check

| Path | GET response | Cache behavior |
| --- | --- | --- |
| `/` | Backend identity and `status: ok` | `Cache-Control: no-store` |
| `/api/status` | Backend identity and `status: ok` | `Cache-Control: no-store` |
| `/cache` | `{"message": "shared cache content v1"}` | `public, max-age=60`; ETag `"team-cache-v1"` |
| Other paths | HTTP 404 with `{"error": "not found"}` | `no-store` |

GET and HEAD are implemented. HEAD returns headers without a body. Query strings do not change route selection.

```sh
curl --max-time 10 --cacert 02_config/team-cert.pem \
  -i https://app.divyansh.test/cache
curl --max-time 10 --cacert 02_config/team-cert.pem \
  -i -H 'If-None-Match: "team-cache-v1"' \
  https://app.divyansh.test/cache
```

The first request returns HTTP 200 with cache headers. The second returns HTTP 304 with no body. Both backends share the same cache representation and ETag. NGINX has no configured response cache; these commands demonstrate backend conditional requests, not a NGINX cache hit. curl does not automatically cache responses between these invocations.

## Failure checks and troubleshooting

Perform one failure at a time and restore service before the next check.

| Check | Expected observation | Recovery |
| --- | --- | --- |
| Wrong DNS server | Lookup fails or receives an unrelated answer | Restore the client resolver to Mac 1 |
| Wrong lab A record | Hostname points away from the edge | Restore both records to Mac 2; account for DNS caching |
| Backend A stopped | NGINX serves B after a qualifying failure/retry | Restart A; allow the five-second failure window to expire and send new requests |
| Both backends stopped | HTTPS reaches NGINX, but requests fail; connection-refusal evidence shows HTTP 502 | Restart both backends and repeat status checks |
| Wrong destination port | Connection refused or timed out, depending on listener/firewall behavior | Use port 443 |

For a backend stop, use Ctrl-C in its foreground terminal, then restart with its original command. Inspect [NGINX access logs](04_evidence/Mac2/logs/access.log) and [error logs](04_evidence/Mac2/logs/error.log) to distinguish upstream failures from DNS or TLS failures. Timeouts can produce HTTP 504; do not assume every upstream failure produces 502.

If HTTPS fails before returning an HTTP status, first check name resolution, port 443 reachability, certificate dates, and whether the client has the certificate matching Mac 2's key.

## Evidence

Existing artifacts are grouped by machine under [04_evidence](04_evidence/). The [architecture evidence map](01_architecture/architecture_doc.md#evidence-map) links representative screenshots, logs, and the [Mac 4 protocol capture](04_evidence/Mac4/Mac4-protocol-flow.pcap).

Capture fresh evidence after changing addresses, certificates, or configuration. Saved artifacts document earlier lab runs; their presence does not establish that services are running now.

## Scope and reference

This is an educational LAN deployment. It has no database, authentication, production deployment automation, or redundant DNS/edge nodes. TLS protects the client-to-edge connection; backend traffic uses plaintext HTTP within the LAN.
