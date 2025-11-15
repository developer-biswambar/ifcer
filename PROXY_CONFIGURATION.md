# Corporate Proxy Configuration Guide

This guide explains how to configure mTLS authentication when using corporate proxies.

## The Problem

When deploying to AWS with a corporate proxy that performs SSL inspection:
- **On-premise**: Direct connection to InfoCert works fine
- **AWS**: Connection goes through corporate proxy, causing SSL verification errors

## Solution Overview

Use the proxy's CA certificate for SSL verification while still sending the InfoCert client certificate for mTLS authentication.

## Configuration

### For AWS (with Corporate Proxy)

```bash
# 1. Upload the proxy's CA certificate to S3
aws s3 cp corporate_proxy_ca.pem s3://your-bucket/certs/corporate_proxy_ca.pem

# 2. Configure environment variables
SSL_VERIFY_ENABLED=true
VENDOR_MTLS_P12_S3_KEY=certs/infocert_client.p12
VENDOR_MTLS_P12_PASSWORD=your_p12_password
VENDOR_MTLS_CA_S3_KEY=certs/corporate_proxy_ca.pem  # Proxy's CA certificate
```

### For Local Development (no Proxy)

```bash
# Don't set VENDOR_MTLS_CA_S3_KEY - uses P12's CA automatically
SSL_VERIFY_ENABLED=true
VENDOR_MTLS_P12_S3_KEY=certs/infocert_client.p12
VENDOR_MTLS_P12_PASSWORD=your_p12_password
# VENDOR_MTLS_CA_S3_KEY not set - uses CA from P12 file
```

### For Explicit Proxy Configuration

If your AWS environment requires explicit proxy settings:

```bash
SSL_VERIFY_ENABLED=true
HTTPS_PROXY=http://your-corporate-proxy.company.com:8080
NO_PROXY=localhost,127.0.0.1,.company.internal
VENDOR_MTLS_CA_S3_KEY=certs/corporate_proxy_ca.pem
```

## How It Works

### Connection Flow with Proxy

```
Your App                    Corporate Proxy              InfoCert API
   |                              |                            |
   |--[TLS Handshake]------------>|                            |
   |  Verify: Proxy's CA cert     |                            |
   |  Send: InfoCert client cert  |                            |
   |                              |                            |
   |                              |--[Forward mTLS]----------->|
   |                              |  InfoCert client cert      |
   |                              |                            |
   |                              |<---[Authenticated]---------|
   |<------[Response]-------------|<---------------------------|
```

**Key Points:**
1. Your app verifies the **proxy's** certificate (using proxy's CA)
2. Your app sends **InfoCert's** client certificate (for mTLS)
3. The proxy forwards your client cert to InfoCert
4. InfoCert authenticates your client certificate

## Logging

The application will log which CA is being used:

### With Custom Proxy CA:
```
[MTLS P12] Custom CA specified, loading from S3: certs/corporate_proxy_ca.pem
[MTLS P12] ✓ Using custom CA from S3 (1234 bytes)
[MTLS P12] This CA will be used for SSL verification (e.g., corporate proxy)
[SSL] Using custom CA bundle: /tmp/custom_ca_xxx.pem
```

### Without Custom CA (Local):
```
[MTLS P12] ✓ Found 1 CA certificate(s) in P12 file:
[MTLS P12]   CA 1: CN=InfoCert Production CA,O=InfoCert
[MTLS P12] ✓ Using CA certificates from P12 file (no custom CA specified)
[SSL] Using custom CA bundle: /tmp/ca_bundle_xxx.pem
```

## Troubleshooting

### Error: "certificate verify failed: self signed certificate in certificate chain"
- **Cause**: Using InfoCert's CA but connecting through a proxy
- **Solution**: Set `VENDOR_MTLS_CA_S3_KEY` to the proxy's CA certificate

### Error: "unauthorized" from InfoCert API
- **Cause**: Client certificate not being forwarded by proxy, or SSL verification disabled
- **Solution**:
  1. Ensure `SSL_VERIFY_ENABLED=true`
  2. Verify proxy is configured to forward client certificates
  3. Check with network team that proxy supports mTLS passthrough

### Error: Custom CA not found in S3
- **Cause**: CA certificate file doesn't exist in S3
- **Solution**: Upload the proxy's CA certificate to S3 first

## Getting the Proxy's CA Certificate

Contact your IT/Network team and ask for:
- "The CA certificate used by the corporate proxy for SSL inspection"
- Should be in PEM format (text file starting with `-----BEGIN CERTIFICATE-----`)

If you receive a .cer or .crt file, convert to PEM:
```bash
openssl x509 -inform DER -in proxy.cer -out corporate_proxy_ca.pem
```

## Verification

After deployment, check the logs to confirm:
1. The correct CA is being loaded
2. SSL verification is enabled
3. Client certificate is configured
4. InfoCert API calls succeed

Example successful log output:
```
[MTLS P12] ✓ Using custom CA from S3 (1234 bytes)
[SSL] Using custom CA bundle: /tmp/custom_ca_xxx.pem
[MTLS SESSION] SSL verify: /tmp/custom_ca_xxx.pem
[MTLS SESSION] Client cert tuple configured: True
[API CALL] Received HTTP 200 for example.pdf
```
