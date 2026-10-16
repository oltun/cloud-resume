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

*This is the current live request path. AWS WAF was trialled in front of CloudFront and then removed (see "Security: AWS WAF" below), so it is not part of the path today.*

## What's built so far

**Phase 1: Frontend**
- HTML and CSS CV, previewed locally with VS Code Live Server
- Version-controlled in this repo

**Phase 2: Static hosting and HTTPS**
- Private S3 bucket: Block Public Access on, SSE-S3 encryption, static website hosting off
- CloudFront distribution reading from S3 via Origin Access Control
- HTTP redirected to HTTPS, `index.html` as default root object

**Phase 3: Custom domain and WAF**
- Domain `oltun.dev` registered with Cloudflare Registrar
- Free TLS certificate from AWS Certificate Manager covering `oltun.dev` and `www.oltun.dev`
- Certificate validated with DNS CNAME records in Cloudflare
- Both names attached to the CloudFront distribution as alternate domain names
- DNS records at Cloudflare point the apex and `www` at CloudFront
- AWS WAF trial: SQL injection probe counted in monitor mode, blocked in blocking mode, then decommissioned (see Security section)

## Security so far

- The S3 bucket is private; only this CloudFront distribution can read it (OAC)
- Plain HTTP requests are redirected to HTTPS, and the minimum TLS version is 1.2 (`TLSv1.2_2021` policy)
- The certificate auto-renews as long as its validation records stay in DNS
- MFA enabled on the AWS and Cloudflare accounts
- AWS WAF with SQL injection protection: deployed, tested, then decommissioned for cost (see the Security: AWS WAF section)

## Design decisions and lessons learned

- **Cloudflare DNS instead of Route 53.** Cloudflare Registrar requires Cloudflare's nameservers, so the domain can't use a Route 53 hosted zone without transferring out. The DNS records are "DNS only" so requests go straight to CloudFront and AWS stays the delivery layer.
- **Regions.** My AWS resources live in `eu-north-1`, the Region assigned to my account. CloudFront needs its certificate in `us-east-1`, and the CloudFront domain setup created the ACM certificate there for me.
- **Cost.** Running cost is the domain (about $12/year at renewal). AWS usage for a static CV site is minimal.

## Security: AWS WAF (SQL injection testing)

**Status: deployed, tested, and decommissioned on 16 Oct 2026 to avoid ongoing cost.** The live site at oltun.dev is currently **not** behind a WAF. AWS WAF would cost about $8/month for this static site (see Cost below).

### What I built
I attached a web ACL to the CloudFront distribution using the console's one-click protection. It created three AWS managed rule groups:

- `AWSManagedRulesAmazonIpReputationList`: blocks IPs on Amazon's threat-intelligence lists
- `AWSManagedRulesCommonRuleSet`: general web attacks such as XSS and local file inclusion
- `AWSManagedRulesKnownBadInputsRuleSet`: known exploit patterns

None of those is a dedicated SQL injection group, so I added a fourth by hand: `AWSManagedRulesSQLiRuleSet`.

### How I tested it
I ran the same two requests in two modes: a normal page load, and a classic SQL injection probe (`' OR '1'='1`, URL-encoded) in the query string.

```
curl -s -o /dev/null -w "%{http_code}\n" "https://oltun.dev/"
curl -s -o /dev/null -w "%{http_code}\n" "https://oltun.dev/?id=1%27%20OR%20%271%27%3D%271"
```

| Mode | Normal page | SQL injection probe |
|---|---|---|
| Monitor (Count) | 200 | 200, matched and counted by `SQLi_QUERYARGUMENTS` |
| Blocking | 200 | **403**, blocked by `SQLi_QUERYARGUMENTS` |

Monitor mode:
![Monitor mode: request matched and counted](docs/images/waf-monitor-mode-count.png)
![Terminal: 200 and 200 in monitor mode](docs/images/waf-curl-monitor.png)

Blocking mode:
![Blocking mode: request blocked by the SQLi rule](docs/images/waf-blocking-block.png)
![Terminal: 200 and 403 in blocking mode](docs/images/waf-curl-blocking.png)

All four rule groups, and the full sampled-requests view:
![Rule groups](docs/images/waf-rules-four-groups.png)
![Sampled requests](docs/images/waf-sampled-requests.png)

### What I learned
- **Monitor mode first.** It records what a rule would block without blocking it, which is the safe way to test a WAF before enforcing it.
- **The 403 alone isn't proof.** A private S3 bucket also returns 403 for missing paths, so I confirmed the block from WAF's sampled requests, which name the exact rule.
- **CloudFront manages its one-click web ACL.** My manually added SQL rule group disappeared after I saved the CloudFront security settings (probably because CloudFront re-applied its own configuration), so I re-added it in the WAF console.
- **A WAF is one layer, not a shield.** Within minutes of the WAF going live, automated scanners probed for `/wp-admin/install.php`. The WAF allowed those requests, because they match no attack rule. The site isn't WordPress, so there was nothing there to exploit.
- **Limits of my test.** I tested a single, simple, URL-encoded probe against the query string. I did not test encoding tricks or other injection points, and a static page has no database to inject into. SQL injection protection becomes meaningful in Phase 4, when the visitor-counter API is added.

### Cost
The one-click setup was estimated at $8.01/month at 10,000 requests/month (web ACL plus three rule groups plus request charges), and the extra SQL rule group adds roughly $1/month. WAF is billed hourly and ran for about 30 minutes, so the trial should cost a few cents at most (to be confirmed on the Billing page). I decommissioned it because that monthly cost is hard to justify for a static CV. I disabled the protection in CloudFront, and verified in the WAF console that no web ACL remained.

### Alternatives considered
- **Cloudflare WAF:** free tier, but not open source, and it would put a second CDN in front of CloudFront.
- **Open-source WAF (ModSecurity or Coraza with the OWASP Core Rule Set):** needs a server in the request path, which CloudFront and S3 can't host. It could only be added as a lab or extra EC2 cost, so I haven't deployed it.

## Roadmap

- [x] Frontend (HTML/CSS)
- [x] Private S3 bucket and CloudFront with HTTPS
- [x] Custom domain with TLS certificate
- [x] AWS WAF with SQL injection protection: deployed, tested, decommissioned (see Security section)
- [ ] Visitor counter (API Gateway, Lambda, DynamoDB)
- [ ] CI/CD with GitHub Actions
- [ ] Write-up and blog post