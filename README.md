# Secure Cloud Resume

My CV as a static website on AWS, live at **https://oltun.dev**.

## Live

- https://oltun.dev
- https://www.oltun.dev

## Architecture

```
Visitor
  |  HTTPS (TLS 1.2+)
  v
Cloudflare DNS (records set to "DNS only", traffic is not proxied)
  |
  v
Amazon CloudFront --- ACM certificate (us-east-1, DNS-validated, auto-renewing)
  |  Origin Access Control (signed requests)
  v
Private S3 bucket (eu-north-1, Block Public Access on)
```

## What's built so far

**Phase 1: Frontend**
- HTML and CSS CV, previewed locally with VS Code Live Server
- Version-controlled in this repo

**Phase 2: Static hosting and HTTPS**
- Private S3 bucket: Block Public Access on, SSE-S3 encryption, static website hosting off
- CloudFront distribution reading from S3 via Origin Access Control
- HTTP redirected to HTTPS, `index.html` as default root object

**Phase 3: Custom domain (in progress)**
- Domain `oltun.dev` registered with Cloudflare Registrar
- Free TLS certificate from AWS Certificate Manager covering `oltun.dev` and `www.oltun.dev`
- Certificate validated with DNS CNAME records in Cloudflare
- Both names attached to the CloudFront distribution as alternate domain names
- DNS records at Cloudflare point the apex and `www` at CloudFront

## Security so far

- The S3 bucket is private; only this CloudFront distribution can read it (OAC)
- Plain HTTP requests are redirected to HTTPS, and the minimum TLS version is 1.2 (`TLSv1.2_2021` policy)
- The certificate auto-renews as long as its validation records stay in DNS
- MFA enabled on the AWS and Cloudflare accounts
- WAF with SQL injection protection: planned (see roadmap)

## Design decisions and lessons learned

- **Cloudflare DNS instead of Route 53.** Cloudflare Registrar requires Cloudflare's nameservers, so the domain can't use a Route 53 hosted zone without transferring out. The DNS records are "DNS only" so requests go straight to CloudFront and AWS stays the delivery layer.
- **Regions.** My AWS resources live in `eu-north-1`, the Region assigned to my account. CloudFront needs its certificate in `us-east-1`, and the CloudFront domain setup created the ACM certificate there for me.
- **Cost.** Running cost is the domain (about $12/year at renewal). AWS usage for a static CV site is minimal.

## Roadmap

- [x] Frontend (HTML/CSS)
- [x] Private S3 bucket and CloudFront with HTTPS
- [x] Custom domain with TLS certificate
- [ ] AWS WAF with SQL injection protection
- [ ] Visitor counter (API Gateway, Lambda, DynamoDB)
- [ ] CI/CD with GitHub Actions
- [ ] Write-up and blog post